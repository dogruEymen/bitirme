from datetime import UTC, datetime
import math

from sqlalchemy.orm import Session

from backend.app.services.ollama_service import OllamaServiceError, get_ollama_service
from database.models.ArticleData import Article
from database.models.ClusterData import Cluster
from database.models.ClusterDigest import ClusterDigest


class DigestService:
    def __init__(self, db: Session):
        self.db = db
        self.ollama = get_ollama_service()

    def get_or_create_cluster_digest(
        self,
        cluster_id: int,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        category: str | None = None,
        source: str | None = None,
        max_articles: int = 5,
        use_llm: bool = True,
    ) -> dict | None:
        cluster = self.db.query(Cluster).filter(Cluster.cluster_id == cluster_id).first()
        if cluster is None:
            return None

        cached = self._cached_digest(cluster_id, period_start, period_end, category, source)
        if cached:
            return self._format_cached_digest(cluster, cached)

        selected_articles = self._select_digest_articles(
            cluster_id=cluster_id,
            period_start=period_start,
            period_end=period_end,
            category=category,
            source=source,
            max_articles=max_articles,
        )
        if not selected_articles:
            return {
                "cluster_id": cluster_id,
                "summary": "The local database does not contain enough matching articles for this digest.",
                "highlights": [],
                "representative_sources": [],
                "article_ids": [],
                "created_at": datetime.now(UTC).isoformat(),
            }

        summary = self._summarize_cluster(cluster, selected_articles, use_llm=use_llm)
        highlights = self._highlights(cluster, selected_articles)
        article_ids = [article.id for article in selected_articles]

        digest = ClusterDigest(
            cluster_id=cluster_id,
            period_start=period_start,
            period_end=period_end,
            summary=summary,
            highlights_json=highlights,
            representative_article_ids_json=article_ids,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
        self.db.add(digest)
        self.db.commit()
        self.db.refresh(digest)
        return self._format_cached_digest(cluster, digest, selected_articles=selected_articles)

    def _cached_digest(
        self,
        cluster_id: int,
        period_start: datetime | None,
        period_end: datetime | None,
        category: str | None,
        source: str | None,
    ) -> ClusterDigest | None:
        if category or source:
            return None
        query = self.db.query(ClusterDigest).filter(ClusterDigest.cluster_id == cluster_id)
        if period_start is None:
            query = query.filter(ClusterDigest.period_start.is_(None))
        else:
            query = query.filter(ClusterDigest.period_start == period_start)
        if period_end is None:
            query = query.filter(ClusterDigest.period_end.is_(None))
        else:
            query = query.filter(ClusterDigest.period_end == period_end)
        return query.order_by(ClusterDigest.created_at.desc()).first()

    def _select_digest_articles(
        self,
        cluster_id: int,
        period_start: datetime | None,
        period_end: datetime | None,
        category: str | None,
        source: str | None,
        max_articles: int,
    ) -> list[Article]:
        cluster = self.db.query(Cluster).filter(Cluster.cluster_id == cluster_id).first()
        representative_ids = []
        if cluster and cluster.metadata_json:
            representative_ids = cluster.metadata_json.get("representative_article_ids") or []
        if not representative_ids and cluster and cluster.representative_docs:
            representative_ids = [int(value) for value in cluster.representative_docs.split(",") if value.strip().isdigit()]

        query = self.db.query(Article).filter(Article.cluster_id == cluster_id)
        if period_start:
            query = query.filter(Article.publish_date >= period_start)
        if period_end:
            query = query.filter(Article.publish_date <= period_end)
        if category:
            query = query.filter(Article.primary_category == category)
        if source:
            query = query.filter(Article.source == source)

        articles = query.all()
        centrality_scores = self._centrality_scores(cluster, representative_ids)
        articles.sort(
            key=lambda article: self._article_digest_score(article, centrality_scores),
            reverse=True,
        )
        return articles[:max_articles]

    def _summarize_cluster(self, cluster: Cluster, articles: list[Article], use_llm: bool) -> str:
        if use_llm:
            prompt = self._summary_prompt(cluster, articles)
            try:
                summary = self.ollama.generate(prompt).strip()
                if summary:
                    return summary[:3000]
            except (OllamaServiceError, RuntimeError):
                pass

        titles = "; ".join(article.title for article in articles[:3])
        categories = sorted({article.primary_category for article in articles if article.primary_category})
        category_text = ", ".join(categories[:3]) if categories else "uncategorized papers"
        return (
            f"Cluster {cluster.cluster_id} contains {len(articles)} selected real articles related to "
            f"{cluster.cluster_description or category_text}. "
            f"Representative papers include: {titles}. "
            "This digest is based only on locally stored article metadata and abstracts."
        )

    @staticmethod
    def _summary_prompt(cluster: Cluster, articles: list[Article]) -> str:
        lines = [
            "Summarize this academic paper cluster in 3 to 5 factual sentences.",
            "Use only the provided article metadata. Do not invent papers, metrics, or conclusions.",
            f"Cluster id: {cluster.cluster_id}",
            f"Cluster label: {cluster.cluster_description or 'Unlabeled'}",
            "Representative articles:",
        ]
        for index, article in enumerate(articles, start=1):
            abstract = (article.abstract_text or "").strip()
            if len(abstract) > 500:
                abstract = f"{abstract[:500]}..."
            lines.append(
                f"{index}. article_id={article.id}; title={article.title}; "
                f"authors={article.authors or 'Unknown'}; venue={article.venue or 'Unknown'}; "
                f"date={article.publish_date.isoformat() if article.publish_date else 'Unknown'}; "
                f"doi={article.doi or 'None'}; abstract={abstract or 'No abstract'}"
            )
        return "\n".join(lines)

    @staticmethod
    def _highlights(cluster: Cluster, articles: list[Article]) -> list[str]:
        highlights = []
        if cluster.metadata_json and cluster.metadata_json.get("keywords"):
            highlights.append("Keywords: " + ", ".join(cluster.metadata_json["keywords"][:5]))
        categories = sorted({article.primary_category for article in articles if article.primary_category})
        if categories:
            highlights.append("Top categories: " + ", ".join(categories[:5]))
        cited = [article for article in articles if article.citation_count]
        if cited:
            top_cited = max(cited, key=lambda article: article.citation_count or 0)
            highlights.append(f"Most cited selected paper: {top_cited.title} ({top_cited.citation_count} citations)")
        return highlights[:3]

    @staticmethod
    def _centrality_scores(cluster: Cluster | None, representative_ids: list[int]) -> dict[int, float]:
        if not representative_ids:
            return {}

        metadata_scores = {}
        if cluster and cluster.metadata_json:
            metadata_scores = cluster.metadata_json.get("representative_article_scores") or {}

        scores: dict[int, float] = {}
        for index, article_id in enumerate(representative_ids):
            raw_score = metadata_scores.get(str(article_id), metadata_scores.get(article_id))
            if raw_score is not None:
                try:
                    scores[int(article_id)] = float(raw_score)
                    continue
                except (TypeError, ValueError):
                    pass
            scores[int(article_id)] = 1.0 / (index + 1)
        return scores

    @staticmethod
    def _article_digest_score(article: Article, centrality_scores: dict[int, float]) -> tuple[float, float, float]:
        centrality = centrality_scores.get(article.id, 0.0)
        citation_score = math.log10((article.citation_count or 0) + 1)
        recency_score = article.publish_date.timestamp() if article.publish_date else 0.0
        return (centrality, recency_score, citation_score)

    @classmethod
    def _article_digest_score_payload(cls, article: Article, centrality_scores: dict[int, float]) -> dict:
        centrality, recency, citation = cls._article_digest_score(article, centrality_scores)
        return {
            "centrality": centrality,
            "recency": recency,
            "citation": citation,
        }

    def _format_cached_digest(
        self,
        cluster: Cluster,
        digest: ClusterDigest,
        selected_articles: list[Article] | None = None,
    ) -> dict:
        article_ids = digest.representative_article_ids_json or []
        if selected_articles is None and article_ids:
            articles = self.db.query(Article).filter(Article.id.in_(article_ids)).all()
            by_id = {article.id: article for article in articles}
            selected_articles = [by_id[article_id] for article_id in article_ids if article_id in by_id]
        selected_articles = selected_articles or []
        representative_ids = []
        if cluster.metadata_json:
            representative_ids = cluster.metadata_json.get("representative_article_ids") or []
        if not representative_ids and cluster.representative_docs:
            representative_ids = [int(value) for value in cluster.representative_docs.split(",") if value.strip().isdigit()]
        centrality_scores = self._centrality_scores(cluster, representative_ids)
        return {
            "cluster_id": cluster.cluster_id,
            "summary": digest.summary,
            "highlights": digest.highlights_json or [],
            "representative_sources": [
                {
                    "source_id": f"S{index}",
                    "article_id": article.id,
                    "title": article.title,
                    "source": article.source,
                    "external_id": article.external_id,
                    "doi": article.doi,
                    "url": article.url or article.pdf_url,
                    "pdf_url": article.pdf_url,
                    "venue": article.venue,
                    "primary_category": article.primary_category,
                    "citation_count": article.citation_count,
                    "publish_date": article.publish_date.isoformat() if article.publish_date else None,
                    "centrality_score": centrality_scores.get(article.id, 0.0),
                    "digest_score": self._article_digest_score_payload(article, centrality_scores),
                }
                for index, article in enumerate(selected_articles, start=1)
            ],
            "article_ids": article_ids,
            "created_at": digest.created_at.isoformat() if digest.created_at else None,
        }
