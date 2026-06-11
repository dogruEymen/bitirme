import math
import re
from datetime import UTC, date, datetime

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.schemas.retrieval import RetrievedArticle, RetrievalFilters
from backend.app.schemas.source import SourceReference
from database.models.ArticleData import Article


class RetrievalService:
    def __init__(self, db: Session):
        self.db = db

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
            top_k=top_k or settings.RAG_TOP_K,
            candidate_k=settings.RAG_CANDIDATE_K,
            sort_by=sort_by,
            query_text=query_text,
        )


def search_articles(
    db: Session,
    query_embedding: list[float] | None,
    filters: RetrievalFilters,
    top_k: int = 5,
    candidate_k: int = 25,
    sort_by: str = "relevance",
    query_text: str | None = None,
) -> list[RetrievedArticle]:
    top_k = max(1, top_k)
    candidate_k = max(top_k, candidate_k)

    if sort_by == "publish_date_desc":
        articles = _latest_articles(db, filters, limit=candidate_k)
        ranked = _deduplicate_preserving_order(articles)
        return _format_results(ranked[:top_k])

    if filters.article_ids and len(filters.article_ids) <= 5:
        articles = _direct_lookup_articles(db, filters)
        ranked = _deduplicate_and_rerank([(article, None) for article in articles])
        return _format_results(ranked[:top_k])

    rows = []
    if query_text:
        keyword_articles = _keyword_articles(db, filters, query_text, limit=candidate_k)
        rows.extend((article, None, getattr(article, "_keyword_score", 0.0)) for article in keyword_articles)
        for article in keyword_articles:
            if hasattr(article, "_keyword_score"):
                delattr(article, "_keyword_score")

    if query_embedding is None:
        ranked = _deduplicate_and_rerank(rows)
        return _format_results(ranked[:top_k])

    distance = Article.embedding.cosine_distance(query_embedding).label("distance")
    query = db.query(Article, distance).filter(Article.embedding.isnot(None))
    query = _apply_filters(query, filters)
    rows.extend(query.order_by(distance.asc()).limit(candidate_k).all())

    if not rows:
        return []

    ranked = _deduplicate_and_rerank(rows)
    return _format_results(ranked[:top_k])


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
