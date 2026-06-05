from datetime import UTC, datetime, timedelta
import hashlib
import json

import numpy as np
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.app.services.digest_service import DigestService
from database.models.ArticleData import Article
from database.models.ClusterData import Cluster
from database.models.ReportSnapshot import ReportSnapshot


ANALYTICS_SNAPSHOT_KEY = "analytics:v1"
DEFAULT_BULLETIN_LIMIT = 10
DEFAULT_BULLETIN_INCLUDE_DIGESTS = True
DEFAULT_BULLETIN_ABSTRACT_LIMIT = 900

COLORS = [
    "#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6",
    "#ec4899", "#14b8a6", "#6366f1", "#06b6d4", "#f43f5e",
    "#059669", "#2563eb", "#d97706", "#dc2626", "#7c3aed",
    "#db2777", "#0d9488", "#4f46e5", "#0891b2", "#e11d48",
]


def get_color(cluster_id: int) -> str:
    return COLORS[abs(cluster_id) % len(COLORS)]


def calculate_cosine_similarity(v1, v2, default: float = 0.0) -> float:
    if v1 is None or v2 is None:
        return default
    arr1 = np.array(v1, dtype=np.float32)
    arr2 = np.array(v2, dtype=np.float32)
    dot = np.dot(arr1, arr2)
    norm1 = np.linalg.norm(arr1)
    norm2 = np.linalg.norm(arr2)
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return float(dot / (norm1 * norm2))


def bulletin_snapshot_key(
    limit: int,
    include_digests: bool,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    category: str | None = None,
    source: str | None = None,
) -> str:
    params = {
        "limit": limit,
        "include_digests": include_digests,
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "category": category,
        "source": source,
    }
    digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return f"bulletin:v1:{digest}"


def default_bulletin_snapshot_key() -> str:
    return bulletin_snapshot_key(
        limit=DEFAULT_BULLETIN_LIMIT,
        include_digests=DEFAULT_BULLETIN_INCLUDE_DIGESTS,
    )


class ReportSnapshotService:
    def __init__(self, db: Session):
        self.db = db

    def get_analytics(self, force_refresh: bool = False) -> dict:
        if force_refresh:
            return self.refresh_analytics_snapshot()
        snapshot = self._get_snapshot(ANALYTICS_SNAPSHOT_KEY)
        if snapshot:
            return snapshot.payload_json
        return empty_analytics_payload(snapshot_missing=True)

    def get_bulletin(
        self,
        limit: int = DEFAULT_BULLETIN_LIMIT,
        include_digests: bool = DEFAULT_BULLETIN_INCLUDE_DIGESTS,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        category: str | None = None,
        source: str | None = None,
        force_refresh: bool = False,
    ) -> list[dict]:
        key = bulletin_snapshot_key(
            limit=limit,
            include_digests=include_digests,
            period_start=period_start,
            period_end=period_end,
            category=category,
            source=source,
        )
        if force_refresh:
            return self.refresh_bulletin_snapshot(
                limit=limit,
                include_digests=include_digests,
                period_start=period_start,
                period_end=period_end,
                category=category,
                source=source,
            )
        snapshot = self._get_snapshot(key)
        if snapshot:
            return snapshot.payload_json
        return []

    def refresh_default_snapshots(self) -> dict[str, str]:
        self.db.query(ReportSnapshot).filter(
            or_(
                ReportSnapshot.snapshot_key == ANALYTICS_SNAPSHOT_KEY,
                ReportSnapshot.snapshot_key.like("bulletin:%"),
            )
        ).delete(synchronize_session=False)
        self.db.commit()

        self.refresh_analytics_snapshot()
        self.refresh_bulletin_snapshot(
            limit=DEFAULT_BULLETIN_LIMIT,
            include_digests=DEFAULT_BULLETIN_INCLUDE_DIGESTS,
        )
        return {
            "analytics": ANALYTICS_SNAPSHOT_KEY,
            "bulletin": default_bulletin_snapshot_key(),
        }

    def refresh_analytics_snapshot(self) -> dict:
        payload = build_analytics_payload(self.db)
        self._upsert_snapshot(ANALYTICS_SNAPSHOT_KEY, payload, metadata={"kind": "analytics"})
        return payload

    def refresh_bulletin_snapshot(
        self,
        limit: int = DEFAULT_BULLETIN_LIMIT,
        include_digests: bool = DEFAULT_BULLETIN_INCLUDE_DIGESTS,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        category: str | None = None,
        source: str | None = None,
    ) -> list[dict]:
        payload = build_bulletin_payload(
            self.db,
            limit=limit,
            include_digests=include_digests,
            period_start=period_start,
            period_end=period_end,
            category=category,
            source=source,
        )
        key = bulletin_snapshot_key(
            limit=limit,
            include_digests=include_digests,
            period_start=period_start,
            period_end=period_end,
            category=category,
            source=source,
        )
        self._upsert_snapshot(
            key,
            payload,
            metadata={
                "kind": "bulletin",
                "limit": limit,
                "include_digests": include_digests,
                "period_start": period_start.isoformat() if period_start else None,
                "period_end": period_end.isoformat() if period_end else None,
                "category": category,
                "source": source,
            },
        )
        return payload

    def _get_snapshot(self, snapshot_key: str) -> ReportSnapshot | None:
        return self.db.query(ReportSnapshot).filter(ReportSnapshot.snapshot_key == snapshot_key).first()

    def _upsert_snapshot(self, snapshot_key: str, payload, metadata: dict | None = None) -> None:
        generated_at = datetime.now(UTC).replace(tzinfo=None)
        snapshot = self._get_snapshot(snapshot_key)
        if snapshot is None:
            snapshot = ReportSnapshot(snapshot_key=snapshot_key, payload_json=payload)
            self.db.add(snapshot)
        snapshot.payload_json = payload
        snapshot.metadata_json = metadata or {}
        snapshot.generated_at = generated_at
        self.db.commit()


def build_analytics_payload(db: Session) -> dict:
    total_papers = db.query(Article).count()
    active_clusters = db.query(Cluster).count()
    clustered_papers = db.query(Article).filter(Article.cluster_id.isnot(None)).count()
    avg_papers_per_cluster = clustered_papers / active_clusters if active_clusters else 0
    week_ago = datetime.utcnow() - timedelta(days=7)
    pdf_available = (
        db.query(Article)
        .filter(
            or_(
                Article.pdf_url.isnot(None),
                Article.metadata_json["has_pdf"].as_boolean().is_(True),
            )
        )
        .count()
    )

    clusters = db.query(Cluster).order_by(Cluster.article_count.desc()).all()

    formatted_clusters = [
        _format_cluster_payload(cluster, _cluster_representation_score(cluster))
        for cluster in clusters
    ]

    metrics = {
        "totalPapers": total_papers,
        "activeClusters": active_clusters,
        "avgPapersPerCluster": avg_papers_per_cluster,
        "weeklyPicks": db.query(Article).filter(Article.publish_date >= week_ago).count(),
        "clusteredPapers": clustered_papers,
        "pdfAvailable": pdf_available,
    }

    bar_data = [
        {"name": cluster["name"], "count": cluster["paper_count"], "color": cluster["color"], "papers": cluster["paper_count"]}
        for cluster in formatted_clusters
    ]
    pie_data = [{"name": item["name"], "value": item["count"], "color": item["color"]} for item in bar_data[:8]]
    scatter_data = [
        {
            "cluster": cluster["name"],
            "fullName": cluster["name"],
            "x": cluster["paper_count"],
            "y": round((cluster.get("representation_score") or 0) * 100, 2),
            "z": cluster["paper_count"],
            "color": cluster["color"],
        }
        for cluster in formatted_clusters
    ]

    monthly_data = _monthly_data(db)
    source_distribution = [
        {"source": source or "unknown", "count": count}
        for source, count in db.query(Article.source, func.count(Article.id)).group_by(Article.source).all()
    ]
    category_distribution = [
        {"category": category or "unknown", "count": count}
        for category, count in (
            db.query(Article.primary_category, func.count(Article.id))
            .group_by(Article.primary_category)
            .order_by(func.count(Article.id).desc())
            .limit(20)
            .all()
        )
    ]

    return {
        "metrics": metrics,
        "barData": bar_data,
        "pieData": pie_data,
        "scatterData": scatter_data,
        "monthlyData": monthly_data,
        "clusters": formatted_clusters,
        "papers": [],
        "sourceDistribution": source_distribution,
        "categoryDistribution": category_distribution,
    }


def build_bulletin_payload(
    db: Session,
    limit: int = DEFAULT_BULLETIN_LIMIT,
    include_digests: bool = DEFAULT_BULLETIN_INCLUDE_DIGESTS,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    category: str | None = None,
    source: str | None = None,
) -> list[dict]:
    clusters = db.query(Cluster).order_by(Cluster.article_count.desc()).all()
    digest_service = DigestService(db)
    result_clusters = []

    for cluster in clusters:
        articles = _cluster_articles(db, cluster, limit)
        metadata_scores = _representative_scores(cluster)
        formatted_papers = []
        for paper in articles:
            score = metadata_scores.get(paper.id, 0.8)
            formatted_papers.append(
                _format_paper_payload(
                    paper,
                    score,
                    week_ago=None,
                    representative=True,
                    abstract_limit=DEFAULT_BULLETIN_ABSTRACT_LIMIT,
                )
            )
        formatted_papers.sort(key=lambda item: item["representation_score"], reverse=True)

        cluster_payload = {
            "cluster": _format_cluster_payload(cluster, representation_score=None),
            "papers": formatted_papers,
        }

        if include_digests:
            digest = digest_service.get_or_create_cluster_digest(
                cluster_id=cluster.cluster_id,
                period_start=period_start,
                period_end=period_end,
                category=category,
                source=source,
                max_articles=min(max(limit, 1), 10),
                use_llm=False,
            )
            cluster_payload["digest"] = _compact_digest(digest)

        result_clusters.append(cluster_payload)

    return result_clusters


def _compact_digest(digest: dict | None) -> dict | None:
    if digest is None:
        return None
    return {
        "cluster_id": digest.get("cluster_id"),
        "summary": digest.get("summary"),
        "highlights": digest.get("highlights") or [],
        "article_ids": digest.get("article_ids") or [],
        "created_at": digest.get("created_at"),
    }


def empty_analytics_payload(snapshot_missing: bool = False) -> dict:
    return {
        "metrics": {
            "totalPapers": 0,
            "activeClusters": 0,
            "avgPapersPerCluster": 0,
            "weeklyPicks": 0,
            "clusteredPapers": 0,
            "pdfAvailable": 0,
        },
        "barData": [],
        "pieData": [],
        "scatterData": [],
        "monthlyData": [],
        "clusters": [],
        "papers": [],
        "sourceDistribution": [],
        "categoryDistribution": [],
        "snapshotMissing": snapshot_missing,
    }


def _cluster_centroids(db: Session, clusters: list[Cluster]) -> dict[int, np.ndarray]:
    centroids = {}
    for cluster in clusters:
        article_embeddings = (
            db.query(Article.embedding)
            .filter(Article.cluster_id == cluster.cluster_id, Article.embedding.isnot(None))
            .all()
        )
        if article_embeddings:
            embeddings = [np.array(article[0], dtype=np.float32) for article in article_embeddings]
            centroids[cluster.cluster_id] = np.mean(embeddings, axis=0)
    return centroids


def _format_paper_payload(
    paper: Article,
    representation_score: float,
    week_ago: datetime | None,
    representative: bool = False,
    abstract_limit: int | None = None,
) -> dict:
    authors_str = paper.authors or "Unknown Authors"
    venue_str = paper.venue or "Unknown Venue"
    year_str = str(paper.publish_date.year) if paper.publish_date else ""
    ref = f"{authors_str} - {venue_str} ({year_str})" if year_str else f"{authors_str} - {venue_str}"
    is_weekly_pick = bool(week_ago and paper.publish_date and paper.publish_date >= week_ago)
    created_at = paper.publish_date.isoformat() if paper.publish_date else datetime.utcnow().isoformat()

    abstract = paper.abstract_text or ""
    if abstract_limit is not None and len(abstract) > abstract_limit:
        abstract = f"{abstract[:abstract_limit].rstrip()}..."

    return {
        "id": str(paper.id),
        "cluster_id": str(paper.cluster_id),
        "title": paper.title,
        "reference": ref,
        "abstract": abstract,
        "is_representative": representative,
        "representation_score": representation_score,
        "published_at": paper.publish_date.isoformat() if paper.publish_date else None,
        "is_weekly_pick": is_weekly_pick,
        "week_label": "This Week",
        "created_at": created_at,
        "citation_count": paper.citation_count or 0,
        "source": paper.source,
        "primary_category": paper.primary_category,
        "doi": paper.doi,
        "url": paper.url or paper.pdf_url,
        "pdf_url": paper.pdf_url,
        "has_pdf": bool(paper.pdf_url or (paper.metadata_json or {}).get("has_pdf")),
    }


def _format_cluster_payload(cluster: Cluster, representation_score: float | None) -> dict:
    desc = cluster.cluster_description or ""
    keyword = desc.split(",")[0].strip() if "," in desc else desc.split(" ")[0].strip()
    if not keyword:
        keyword = f"Topic {cluster.cluster_id}"

    payload = {
        "id": str(cluster.cluster_id),
        "name": cluster.cluster_description or f"Cluster {cluster.cluster_id}",
        "keyword": keyword,
        "description": cluster.cluster_description or "",
        "color": get_color(cluster.cluster_id),
        "paper_count": cluster.article_count,
        "created_at": cluster.created_at.isoformat() if cluster.created_at else datetime.utcnow().isoformat(),
        "metadata": cluster.metadata_json or {},
    }
    if representation_score is not None:
        payload["representation_score"] = representation_score
    return payload


def _representative_scores(cluster: Cluster) -> dict[int, float]:
    if not cluster.metadata_json:
        return {}
    raw_scores = cluster.metadata_json.get("representative_article_scores") or {}
    scores = {}
    for article_id, score in raw_scores.items():
        try:
            scores[int(article_id)] = float(score)
        except (TypeError, ValueError):
            continue
    return scores


def _cluster_representation_score(cluster: Cluster) -> float:
    scores = list(_representative_scores(cluster).values())
    return sum(scores) / len(scores) if scores else 0.0


def _monthly_data(db: Session) -> list[dict]:
    monthly_rows = (
        db.query(
            func.to_char(func.date_trunc("month", Article.publish_date), "YYYY-MM").label("month_key"),
            func.count(Article.id).label("count"),
        )
        .filter(Article.publish_date.isnot(None))
        .group_by("month_key")
        .order_by("month_key")
        .all()
    )
    return [
        {
            "month": datetime.strptime(row._mapping["month_key"], "%Y-%m").strftime("%b %y"),
            "count": int(row._mapping["count"]),
            "publications": int(row._mapping["count"]),
        }
        for row in monthly_rows[-12:]
    ]


def _cluster_articles(db: Session, cluster: Cluster, limit: int) -> list[Article]:
    representative_ids = []
    if cluster.metadata_json:
        representative_ids = cluster.metadata_json.get("representative_article_ids") or []
    if not representative_ids and cluster.representative_docs:
        representative_ids = [
            int(value)
            for value in cluster.representative_docs.split(",")
            if value.strip().isdigit()
        ]

    if representative_ids:
        articles = db.query(Article).filter(Article.id.in_(representative_ids)).all()
        by_id = {article.id: article for article in articles}
        ordered_articles = [by_id[article_id] for article_id in representative_ids if article_id in by_id]
        if len(ordered_articles) >= limit:
            return ordered_articles[:limit]

        remaining = (
            db.query(Article)
            .filter(Article.cluster_id == cluster.cluster_id, Article.id.notin_(representative_ids))
            .limit(limit - len(ordered_articles))
            .all()
        )
        return ordered_articles + remaining

    return db.query(Article).filter(Article.cluster_id == cluster.cluster_id).limit(limit).all()
