from dataclasses import dataclass
from functools import lru_cache
import logging
import math
import re
import sqlite3
import time
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.schemas.retrieval import RetrievedArticle, RetrievalFilters
from backend.app.schemas.source import SourceReference
from database.models.ArticleData import Article


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
VALID_RETRIEVAL_MODES = {"hybrid", "vector", "bm25"}
VALID_FUSION_METHODS = {"rrf", "weighted"}


@dataclass
class RetrievalCandidate:
    article: Article
    retrieval_source: str
    vector_score: float | None = None
    bm25_score: float | None = None
    vector_rank: int | None = None
    bm25_rank: int | None = None
    fusion_score: float = 0.0
    reranker_score: float | None = None


class RetrievalService:
    def __init__(
        self,
        db: Session,
        retrieval_mode: str | None = None,
        fusion_method: str | None = None,
        vector_top_k: int | None = None,
        bm25_top_k: int | None = None,
        final_top_k: int | None = None,
    ):
        self.db = db
        self.retrieval_mode = _normalize_choice(
            retrieval_mode or settings.RAG_RETRIEVAL_MODE,
            VALID_RETRIEVAL_MODES,
            default="hybrid",
        )
        self.fusion_method = _normalize_choice(
            fusion_method or settings.RAG_FUSION_METHOD,
            VALID_FUSION_METHODS,
            default="rrf",
        )
        self.vector_top_k = max(1, vector_top_k or settings.RAG_VECTOR_TOP_K)
        self.bm25_top_k = max(1, bm25_top_k or settings.RAG_BM25_TOP_K)
        self.final_top_k = max(1, final_top_k or settings.RAG_FINAL_TOP_K)
        self.bm25_index_status = "not_used"
        if self.retrieval_mode in {"hybrid", "bm25"}:
            self.bm25_index_status = check_bm25_index_status(self.db)

    def retrieve(
        self,
        query_embedding: list[float] | None,
        filters: RetrievalFilters,
        top_k: int | None = None,
        sort_by: str = "relevance",
        query_text: str | None = None,
    ) -> list[RetrievedArticle]:
        return search_articles(
            db=self.db,
            query_embedding=query_embedding,
            filters=filters,
            top_k=top_k or self.final_top_k,
            candidate_k=settings.RAG_CANDIDATE_K,
            sort_by=sort_by,
            query_text=query_text,
            retrieval_mode=self.retrieval_mode,
            fusion_method=self.fusion_method,
            vector_top_k=self.vector_top_k,
            bm25_top_k=self.bm25_top_k,
            bm25_index_status=self.bm25_index_status,
        )


def search_articles(
    db: Session,
    query_embedding: list[float] | None,
    filters: RetrievalFilters,
    top_k: int = 5,
    candidate_k: int = 25,
    sort_by: str = "relevance",
    query_text: str | None = None,
    retrieval_mode: str | None = None,
    fusion_method: str | None = None,
    vector_top_k: int | None = None,
    bm25_top_k: int | None = None,
    bm25_index_status: str | None = None,
) -> list[RetrievedArticle]:
    top_k = max(1, top_k)
    candidate_k = max(top_k, candidate_k)
    retrieval_mode = _normalize_choice(retrieval_mode or settings.RAG_RETRIEVAL_MODE, VALID_RETRIEVAL_MODES, "hybrid")
    fusion_method = _normalize_choice(fusion_method or settings.RAG_FUSION_METHOD, VALID_FUSION_METHODS, "rrf")
    vector_top_k = max(top_k, vector_top_k or settings.RAG_VECTOR_TOP_K or candidate_k)
    bm25_top_k = max(top_k, bm25_top_k or settings.RAG_BM25_TOP_K or candidate_k)

    if sort_by == "publish_date_desc":
        articles = _latest_articles(db, filters, limit=candidate_k)
        ranked = _deduplicate_preserving_order(articles)
        return _format_results(ranked[:top_k])

    if filters.article_ids and len(filters.article_ids) <= 5:
        articles = _direct_lookup_articles(db, filters)
        ranked = _deduplicate_and_rerank([(article, None) for article in articles])
        return _format_results(ranked[:top_k])

    start = time.perf_counter()
    vector_candidates: list[RetrievalCandidate] = []
    bm25_candidates: list[RetrievalCandidate] = []

    if retrieval_mode in {"hybrid", "vector"} and query_embedding is not None:
        vector_candidates = VectorRetriever(db).search(query_embedding, filters, limit=vector_top_k)

    if retrieval_mode in {"hybrid", "bm25"} and query_text:
        bm25_candidates = BM25Retriever(db, index_status=bm25_index_status).search(query_text, filters, limit=bm25_top_k)

    if retrieval_mode == "hybrid" and not bm25_candidates and vector_candidates:
        logger.warning("BM25 candidates unavailable; falling back to vector-only retrieval.")

    if retrieval_mode == "bm25" and not bm25_candidates:
        return []

    if not vector_candidates and not bm25_candidates:
        return []

    fused = HybridRetriever(fusion_method=fusion_method).fuse(vector_candidates, bm25_candidates)
    reranker_failed = False
    if query_text:
        reranked, reranker_failed = CrossEncoderReranker().rerank(query_text, fused)
        if reranked:
            fused = reranked
    if settings.RAG_DEBUG_RETRIEVAL:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            (
                "retrieval_debug query=%r mode=%s fusion=%s reranker_enabled=%s "
                "reranker_failed=%s vector_ids=%s bm25_ids=%s reranked_ids=%s final_ids=%s latency_ms=%.2f"
            ),
            query_text,
            retrieval_mode,
            fusion_method,
            settings.RAG_RERANKER_ENABLED,
            reranker_failed,
            [candidate.article.id for candidate in vector_candidates],
            [candidate.article.id for candidate in bm25_candidates],
            [candidate.article.id for candidate in fused[:top_k]],
            [candidate.article.id for candidate in fused[:top_k]],
            elapsed_ms,
        )
    return _format_candidate_results(fused[:top_k])


class VectorRetriever:
    def __init__(self, db: Session):
        self.db = db

    def search(
        self,
        query_embedding: list[float],
        filters: RetrievalFilters,
        limit: int,
    ) -> list[RetrievalCandidate]:
        distance = Article.embedding.cosine_distance(query_embedding).label("distance")
        query = self.db.query(Article, distance).filter(Article.embedding.isnot(None))
        query = _apply_filters(query, filters)
        candidates: list[RetrievalCandidate] = []
        for rank, (article, raw_distance) in enumerate(query.order_by(distance.asc()).limit(limit).all(), start=1):
            similarity = max(0.0, 1.0 - float(raw_distance))
            candidates.append(
                RetrievalCandidate(
                    article=article,
                    retrieval_source="vector",
                    vector_score=similarity,
                    vector_rank=rank,
                    fusion_score=similarity,
                )
            )
        return candidates


class BM25Retriever:
    def __init__(self, db: Session, index_path: str | Path | None = None, index_status: str | None = None):
        self.db = db
        self.index_path = _resolve_project_path(index_path or settings.RAG_BM25_INDEX_PATH)
        self.index_status = index_status or check_bm25_index_status(db, self.index_path)

    def search(self, query_text: str, filters: RetrievalFilters, limit: int) -> list[RetrievalCandidate]:
        if not self.index_path.exists():
            logger.warning("BM25 index not found at %s", self.index_path)
            return []

        fts_query = _sanitize_fts_query(query_text)
        if not fts_query:
            return []

        try:
            rows = self._search_index(fts_query, filters, limit=max(limit * 4, limit))
        except sqlite3.Error:
            logger.exception("BM25 index query failed")
            return []

        article_ids = [row["article_id"] for row in rows]
        if not article_ids:
            return []

        article_query = self.db.query(Article).filter(Article.id.in_(article_ids))
        article_query = _apply_filters(article_query, filters)
        articles = {article.id: article for article in article_query.all()}

        candidates: list[RetrievalCandidate] = []
        for rank, row in enumerate(rows, start=1):
            article = articles.get(row["article_id"])
            if article is None:
                continue
            candidates.append(
                RetrievalCandidate(
                    article=article,
                    retrieval_source="bm25",
                    bm25_score=row["bm25_score"],
                    bm25_rank=rank,
                    fusion_score=row["bm25_score"],
                )
            )
        return candidates[:limit]

    def _search_index(self, fts_query: str, filters: RetrievalFilters, limit: int) -> list[dict]:
        clauses = ["articles_fts MATCH ?"]
        params: list[object] = [fts_query]

        if filters.article_ids:
            placeholders = ", ".join("?" for _ in filters.article_ids)
            clauses.append(f"article_id IN ({placeholders})")
            params.extend(filters.article_ids)
        if filters.source:
            clauses.append("source = ?")
            params.append(filters.source)
        if filters.cluster_id is not None:
            clauses.append("cluster_id = ?")
            params.append(str(filters.cluster_id))
        if filters.primary_category:
            clauses.append("primary_category = ?")
            params.append(filters.primary_category)
        if filters.categories_any:
            category_clauses = []
            for category in filters.categories_any:
                category_clauses.append("categories LIKE ?")
                params.append(f"%{category}%")
            clauses.append(f"({' OR '.join(category_clauses)})")
        if filters.venue:
            clauses.append("venue LIKE ?")
            params.append(f"%{filters.venue}%")
        if filters.doi:
            clauses.append("doi LIKE ?")
            params.append(f"%{filters.doi}%")
        if filters.publish_date_from:
            clauses.append("publish_date >= ?")
            params.append(_date_start(filters.publish_date_from).date().isoformat())
        if filters.publish_date_to:
            clauses.append("publish_date <= ?")
            params.append(_date_end(filters.publish_date_to).date().isoformat())

        sql = f"""
            SELECT
                CAST(article_id AS INTEGER) AS article_id,
                -bm25(articles_fts, 3.0, 1.0) AS bm25_score
            FROM articles_fts
            WHERE {' AND '.join(clauses)}
            ORDER BY bm25(articles_fts, 3.0, 1.0) ASC
            LIMIT ?
        """
        params.append(limit)
        with sqlite3.connect(self.index_path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(sql, params).fetchall()]


class HybridRetriever:
    def __init__(self, fusion_method: str = "rrf"):
        self.fusion_method = _normalize_choice(fusion_method, VALID_FUSION_METHODS, "rrf")

    def fuse(
        self,
        vector_candidates: list[RetrievalCandidate],
        bm25_candidates: list[RetrievalCandidate],
    ) -> list[RetrievalCandidate]:
        if self.fusion_method == "weighted":
            return _weighted_score_fusion(vector_candidates, bm25_candidates)
        return _reciprocal_rank_fusion(vector_candidates, bm25_candidates, rrf_k=settings.RAG_RRF_K)


class CrossEncoderReranker:
    def __init__(self):
        self.enabled = settings.RAG_RERANKER_ENABLED
        self.top_n = max(1, settings.RAG_RERANKER_TOP_N)

    def rerank(self, query_text: str, candidates: list[RetrievalCandidate]) -> tuple[list[RetrievalCandidate], bool]:
        if not self.enabled or not query_text or not candidates:
            return candidates, False

        candidates_to_rerank = candidates[: self.top_n]
        try:
            model = get_reranker_model()
            pairs = [(query_text, _reranker_document_text(candidate.article)) for candidate in candidates_to_rerank]
            scores = model.predict(pairs)
        except Exception:
            logger.exception("RAG reranker failed; falling back to fused retrieval ranking.")
            return candidates, True

        for candidate, score in zip(candidates_to_rerank, scores, strict=False):
            candidate.reranker_score = float(score)

        reranked = sorted(
            candidates_to_rerank,
            key=lambda candidate: (
                candidate.reranker_score if candidate.reranker_score is not None else float("-inf"),
                candidate.fusion_score,
            ),
            reverse=True,
        )
        reranked.extend(candidates[self.top_n :])
        return reranked, False


@lru_cache(maxsize=1)
def get_reranker_model():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(settings.RAG_RERANKER_MODEL_NAME)


def _normalize_choice(value: str, allowed: set[str], default: str) -> str:
    normalized = (value or default).strip().lower()
    if normalized not in allowed:
        logger.warning("Unsupported retrieval setting %r; using %s", value, default)
        return default
    return normalized


def _resolve_project_path(path: str | Path) -> Path:
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    return PROJECT_ROOT / resolved


def check_bm25_index_status(db: Session, index_path: str | Path | None = None) -> str:
    resolved_path = _resolve_project_path(index_path or settings.RAG_BM25_INDEX_PATH)
    if not resolved_path.exists():
        return "missing"

    try:
        index_fingerprint = _read_bm25_index_fingerprint(resolved_path)
    except Exception:
        logger.exception("BM25 index health check failed")
        return "unknown"

    if not index_fingerprint:
        return "unknown"

    try:
        db_fingerprint = _source_db_fingerprint(db)
    except Exception:
        logger.exception("BM25 database fingerprint check failed")
        return "unknown"

    if not db_fingerprint:
        return "unknown"
    if index_fingerprint != db_fingerprint:
        logger.warning("BM25 index appears stale: index=%s, db=%s", index_fingerprint, db_fingerprint)
        return "stale"
    return "ok"


def _read_bm25_index_fingerprint(index_path: Path) -> str | None:
    try:
        with sqlite3.connect(index_path) as conn:
            row = conn.execute(
                "SELECT value FROM index_metadata WHERE key = ?",
                ("source_db_fingerprint",),
            ).fetchone()
    except sqlite3.Error:
        return None
    return str(row[0]) if row else None


def _source_db_fingerprint(db: Session) -> str | None:
    total_articles = db.query(Article).count()
    embedded_articles = db.query(Article).filter(Article.embedding.isnot(None)).count()
    max_article_id = db.query(Article.id).order_by(Article.id.desc()).limit(1).scalar()
    return f"articles:{total_articles}:embedded:{embedded_articles}:max_id:{max_article_id}"


def _sanitize_fts_query(query_text: str) -> str:
    terms = _extract_keyword_terms(query_text)
    if not terms:
        return ""
    return " OR ".join(f'"{term.replace(chr(34), chr(34) + chr(34))}"' for term in terms)


def _reranker_document_text(article: Article) -> str:
    title = (article.title or "").strip()
    abstract = (article.abstract_text or "").strip()
    return f"{title}. {abstract}".strip()


def _merge_candidate(
    merged: dict[str, RetrievalCandidate],
    candidate: RetrievalCandidate,
) -> None:
    key = _dedupe_key(candidate.article)
    existing = merged.get(key)
    if existing is None:
        merged[key] = RetrievalCandidate(
            article=candidate.article,
            retrieval_source=candidate.retrieval_source,
            vector_score=candidate.vector_score,
            bm25_score=candidate.bm25_score,
            vector_rank=candidate.vector_rank,
            bm25_rank=candidate.bm25_rank,
            fusion_score=candidate.fusion_score,
        )
        return

    existing.retrieval_source = "both"
    if candidate.vector_score is not None:
        existing.vector_score = candidate.vector_score
    if candidate.bm25_score is not None:
        existing.bm25_score = candidate.bm25_score
    if candidate.vector_rank is not None:
        existing.vector_rank = candidate.vector_rank
    if candidate.bm25_rank is not None:
        existing.bm25_rank = candidate.bm25_rank


def _reciprocal_rank_fusion(
    vector_candidates: list[RetrievalCandidate],
    bm25_candidates: list[RetrievalCandidate],
    rrf_k: int = 60,
) -> list[RetrievalCandidate]:
    merged: dict[str, RetrievalCandidate] = {}
    for candidate in vector_candidates:
        _merge_candidate(merged, candidate)
    for candidate in bm25_candidates:
        _merge_candidate(merged, candidate)

    for candidate in merged.values():
        score = 0.0
        if candidate.vector_rank is not None:
            score += 1.0 / (rrf_k + candidate.vector_rank)
        if candidate.bm25_rank is not None:
            score += 1.0 / (rrf_k + candidate.bm25_rank)
        candidate.fusion_score = score

    return sorted(
        merged.values(),
        key=lambda candidate: (
            candidate.fusion_score,
            candidate.vector_score or 0.0,
            candidate.bm25_score or 0.0,
        ),
        reverse=True,
    )


def _weighted_score_fusion(
    vector_candidates: list[RetrievalCandidate],
    bm25_candidates: list[RetrievalCandidate],
) -> list[RetrievalCandidate]:
    merged: dict[str, RetrievalCandidate] = {}
    for candidate in vector_candidates:
        _merge_candidate(merged, candidate)
    for candidate in bm25_candidates:
        _merge_candidate(merged, candidate)

    vector_scores = [candidate.vector_score for candidate in merged.values() if candidate.vector_score is not None]
    bm25_scores = [candidate.bm25_score for candidate in merged.values() if candidate.bm25_score is not None]
    alpha = min(1.0, max(0.0, settings.RAG_WEIGHTED_ALPHA))
    beta = 1.0 - alpha

    for candidate in merged.values():
        vector_score = _minmax(candidate.vector_score, vector_scores)
        bm25_score = _minmax(candidate.bm25_score, bm25_scores)
        candidate.fusion_score = alpha * vector_score + beta * bm25_score

    return sorted(
        merged.values(),
        key=lambda candidate: (
            candidate.fusion_score,
            candidate.vector_score or 0.0,
            candidate.bm25_score or 0.0,
        ),
        reverse=True,
    )


def _minmax(value: float | None, values: list[float | None]) -> float:
    if value is None or not values:
        return 0.0
    concrete = [float(item) for item in values if item is not None]
    if not concrete:
        return 0.0
    low = min(concrete)
    high = max(concrete)
    if high == low:
        return 1.0
    return (float(value) - low) / (high - low)


def _direct_lookup_articles(db: Session, filters: RetrievalFilters) -> list[Article]:
    query = db.query(Article).filter(Article.id.in_(filters.article_ids))
    query = _apply_filters(query, filters, include_article_ids=False)
    articles = query.all()
    by_id = {article.id: article for article in articles}
    return [by_id[article_id] for article_id in filters.article_ids if article_id in by_id]


def _latest_articles(db: Session, filters: RetrievalFilters, limit: int) -> list[Article]:
    query = db.query(Article).filter(Article.publish_date.isnot(None))
    query = _apply_filters(query, filters)
    return query.order_by(Article.publish_date.desc(), Article.id.desc()).limit(limit).all()


KEYWORD_STOPWORDS = {
    "about",
    "adli",
    "arada",
    "article",
    "articles",
    "ayari",
    "bir",
    "bu",
    "called",
    "fine",
    "hangi",
    "makale",
    "makaleler",
    "named",
    "paper",
    "papers",
    "sistem",
    "sistemi",
    "sistemini",
    "sunum",
    "the",
    "ve",
    "which",
}

TURKISH_TRANSLATION = str.maketrans(
    {
        "\u00e7": "c",
        "\u011f": "g",
        "\u0131": "i",
        "\u00f6": "o",
        "\u015f": "s",
        "\u00fc": "u",
        "\u00c7": "c",
        "\u011e": "g",
        "\u0130": "i",
        "\u00d6": "o",
        "\u015e": "s",
        "\u00dc": "u",
    }
)


def _keyword_articles(db: Session, filters: RetrievalFilters, query_text: str, limit: int) -> list[Article]:
    terms = _extract_keyword_terms(query_text)
    if not terms:
        return []

    conditions = []
    for term in terms:
        pattern = f"%{term}%"
        conditions.extend(
            [
                Article.title.ilike(pattern),
                Article.abstract_text.ilike(pattern),
            ]
        )

    query = db.query(Article).filter(or_(*conditions))
    query = _apply_filters(query, filters)
    articles = query.limit(max(limit * 4, limit)).all()
    for article in articles:
        article._keyword_score = _keyword_score(article, terms)
    return sorted(articles, key=lambda article: article._keyword_score, reverse=True)[:limit]


def _extract_keyword_terms(query_text: str) -> list[str]:
    tokens = re.findall(r"[\w.-]{2,}", query_text, flags=re.UNICODE)
    terms: list[str] = []
    for token in tokens:
        cleaned = token.strip(".-").translate(TURKISH_TRANSLATION).lower()
        if len(cleaned) < 3 and not token.isupper():
            continue
        if cleaned in KEYWORD_STOPWORDS:
            continue
        if cleaned not in terms:
            terms.append(cleaned)
    return terms[:8]


def _keyword_score(article: Article, terms: list[str]) -> float:
    title = (article.title or "").lower()
    abstract = (article.abstract_text or "").lower()
    score = 0.0
    for term in terms:
        title_hits = len(re.findall(rf"\b{re.escape(term)}\b", title))
        abstract_hits = len(re.findall(rf"\b{re.escape(term)}\b", abstract))
        score += title_hits * 3.0 + abstract_hits
        if term in title:
            score += 1.0
        if term in abstract:
            score += 0.25
    return score


def _apply_filters(query, filters: RetrievalFilters, include_article_ids: bool = True):
    if include_article_ids and filters.article_ids:
        query = query.filter(Article.id.in_(filters.article_ids))
    if filters.source:
        query = query.filter(Article.source == filters.source)
    if filters.cluster_id is not None:
        query = query.filter(Article.cluster_id == filters.cluster_id)
    if filters.primary_category:
        query = query.filter(Article.primary_category == filters.primary_category)
    if filters.categories_any:
        category_filters = [Article.categories.ilike(f"%{category}%") for category in filters.categories_any]
        query = query.filter(or_(*category_filters))
    if filters.venue:
        query = query.filter(Article.venue.ilike(f"%{filters.venue}%"))
    if filters.doi:
        query = query.filter(Article.doi.ilike(f"%{filters.doi}%"))
    if filters.has_pdf is True:
        query = query.filter(
            or_(
                Article.pdf_url.isnot(None),
                Article.metadata_json["has_pdf"].as_boolean().is_(True),
            )
        )
    elif filters.has_pdf is False:
        query = query.filter(
            and_(
                Article.pdf_url.is_(None),
                or_(
                    Article.metadata_json.is_(None),
                    Article.metadata_json["has_pdf"].as_boolean().isnot(True),
                ),
            )
        )
    if filters.min_citation_count is not None:
        query = query.filter(Article.citation_count >= filters.min_citation_count)
    if filters.publish_date_from:
        query = query.filter(Article.publish_date >= _date_start(filters.publish_date_from))
    if filters.publish_date_to:
        query = query.filter(Article.publish_date <= _date_end(filters.publish_date_to))
    return query


def _deduplicate_and_rerank(rows) -> list[tuple[Article, float | None, float]]:
    best_by_key: dict[str, tuple[Article, float | None, float]] = {}
    for row in rows:
        article, raw_distance = row[:2]
        keyword_score = row[2] if len(row) > 2 else 0.0
        vector_similarity = None if raw_distance is None else max(0.0, 1.0 - float(raw_distance))
        final_score = _final_score(article, vector_similarity or 0.0)
        final_score += _keyword_score_component(keyword_score)
        key = _dedupe_key(article)
        existing = best_by_key.get(key)
        if existing is None or final_score > existing[2]:
            best_by_key[key] = (article, vector_similarity, final_score)

    return sorted(best_by_key.values(), key=lambda item: item[2], reverse=True)


def _deduplicate_preserving_order(articles: list[Article]) -> list[tuple[Article, float | None, float]]:
    seen: set[str] = set()
    ranked: list[tuple[Article, float | None, float]] = []
    for article in articles:
        key = _dedupe_key(article)
        if key in seen:
            continue
        seen.add(key)
        ranked.append((article, None, _final_score(article, 0.0)))
    return ranked


def _dedupe_key(article: Article) -> str:
    if article.doi:
        return f"doi:{article.doi.strip().lower()}"
    return f"external:{article.source}:{article.external_id}"


def _final_score(article: Article, vector_similarity: float) -> float:
    score = vector_similarity
    if article.publish_date:
        now = datetime.now(UTC).replace(tzinfo=None)
        age_days = max(0, (now - _as_naive_datetime(article.publish_date)).days)
        score += max(0.0, 0.05 * (1.0 - min(age_days, 365) / 365))
    if article.citation_count is not None and article.citation_count > 0:
        score += min(0.03, math.log10(article.citation_count + 1) / 100)
    if not (article.abstract_text or "").strip():
        score -= 0.05
    return score


def _keyword_score_component(keyword_score: float) -> float:
    if keyword_score <= 0:
        return 0.0
    return min(0.65, math.log1p(float(keyword_score)) / 5.0)


def _format_candidate_results(candidates: list[RetrievalCandidate]) -> list[RetrievedArticle]:
    results: list[RetrievedArticle] = []
    for index, candidate in enumerate(candidates, start=1):
        article = candidate.article
        results.append(
            RetrievedArticle(
                source=SourceReference(
                    source_id=f"S{index}",
                    article_id=article.id,
                    title=article.title,
                    source=article.source,
                    external_id=article.external_id,
                    doi=article.doi,
                    url=article.url,
                    pdf_url=article.pdf_url,
                    venue=article.venue,
                    publish_date=article.publish_date,
                    authors=article.authors,
                    cluster_id=article.cluster_id,
                    score=candidate.reranker_score if candidate.reranker_score is not None else candidate.fusion_score,
                    vector_score=candidate.vector_score,
                    bm25_score=candidate.bm25_score,
                    vector_rank=candidate.vector_rank,
                    bm25_rank=candidate.bm25_rank,
                    fusion_score=candidate.fusion_score,
                    reranker_score=candidate.reranker_score,
                    retrieval_source=candidate.retrieval_source,
                ),
                abstract_text=article.abstract_text,
                primary_category=article.primary_category,
                categories=article.categories,
                citation_count=article.citation_count,
            )
        )
    return results


def _format_results(ranked: list[tuple[Article, float | None, float]]) -> list[RetrievedArticle]:
    results: list[RetrievedArticle] = []
    for index, (article, vector_score, final_score) in enumerate(ranked, start=1):
        results.append(
            RetrievedArticle(
                source=SourceReference(
                    source_id=f"S{index}",
                    article_id=article.id,
                    title=article.title,
                    source=article.source,
                    external_id=article.external_id,
                    doi=article.doi,
                    url=article.url,
                    pdf_url=article.pdf_url,
                    venue=article.venue,
                    publish_date=article.publish_date,
                    authors=article.authors,
                    cluster_id=article.cluster_id,
                    score=final_score,
                    vector_score=vector_score,
                ),
                abstract_text=article.abstract_text,
                primary_category=article.primary_category,
                categories=article.categories,
                citation_count=article.citation_count,
            )
        )
    return results


def _date_start(value: date | str) -> datetime:
    if isinstance(value, str):
        value = date.fromisoformat(value)
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, datetime.min.time())


def _date_end(value: date | str) -> datetime:
    if isinstance(value, str):
        value = date.fromisoformat(value)
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, datetime.max.time())


def _as_naive_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.replace(tzinfo=None)


def build_rag_context(results: list[RetrievedArticle]) -> str:
    if not results:
        return "No matching articles were retrieved from the local database."

    blocks: list[str] = []
    for result in results:
        source = result.source
        abstract = (result.abstract_text or "").strip()
        if len(abstract) > 1200:
            abstract = f"{abstract[:1200]}..."
        blocks.append(
            "\n".join(
                [
                    f"[{source.source_id}]",
                    f"article_id: {source.article_id}",
                    f"title: {source.title}",
                    f"authors: {source.authors or 'Unknown'}",
                    f"source: {source.source or 'Unknown'}",
                    f"external_id: {source.external_id or 'None'}",
                    f"venue: {source.venue or 'Unknown'}",
                    f"publish_date: {source.publish_date.isoformat() if source.publish_date else 'Unknown'}",
                    f"doi: {source.doi or 'None'}",
                    f"url: {source.url or source.pdf_url or 'None'}",
                    f"cluster_id: {source.cluster_id if source.cluster_id is not None else 'None'}",
                    f"category: {result.primary_category or result.categories or 'None'}",
                    f"citation_count: {result.citation_count if result.citation_count is not None else 'Unknown'}",
                    f"score: {source.score:.4f}" if source.score is not None else "score: None",
                    f"abstract: {abstract or 'No abstract available.'}",
                ]
            )
        )
    return "\n\n".join(blocks)
