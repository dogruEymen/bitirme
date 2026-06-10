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


LEGACY_ANALYTICS_SNAPSHOT_KEY = "analytics:v1"
ANALYTICS_SCHEMA_VERSION = "analytics:v2"
DEFAULT_ANALYTICS_PERIOD = "12m"
ANALYTICS_PERIODS = {"3m": 90, "6m": 180, "12m": 365, "all": None}
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


def normalize_analytics_period(period: str | None) -> str:
    normalized = (period or DEFAULT_ANALYTICS_PERIOD).strip().lower()
    return normalized if normalized in ANALYTICS_PERIODS else DEFAULT_ANALYTICS_PERIOD


def analytics_snapshot_key(
    source: str | None = None,
    category: str | None = None,
    period: str = DEFAULT_ANALYTICS_PERIOD,
) -> str:
    params = {
        "source": source or None,
        "category": category or None,
        "period": normalize_analytics_period(period),
    }
    digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return f"{ANALYTICS_SCHEMA_VERSION}:{digest}"


ANALYTICS_SNAPSHOT_KEY = analytics_snapshot_key()


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
    cluster_ids: list[int] | None = None,
    categories: list[str] | None = None,
) -> str:
    params = {
        "limit": limit,
        "include_digests": include_digests,
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "category": category,
        "source": source,
        "cluster_ids": sorted(cluster_ids or []),
        "categories": sorted(categories or []),
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

    def get_analytics(
        self,
        force_refresh: bool = False,
        source: str | None = None,
        category: str | None = None,
        period: str = DEFAULT_ANALYTICS_PERIOD,
    ) -> dict:
        period = normalize_analytics_period(period)
        key = analytics_snapshot_key(source=source, category=category, period=period)
        if force_refresh:
            return self.refresh_analytics_snapshot(source=source, category=category, period=period)
        snapshot = self._get_snapshot(key)
        if snapshot:
            return with_analytics_defaults(snapshot.payload_json, source=source, category=category, period=period)
        if key == ANALYTICS_SNAPSHOT_KEY:
            legacy_snapshot = self._get_snapshot(LEGACY_ANALYTICS_SNAPSHOT_KEY)
            if legacy_snapshot:
                return with_analytics_defaults(
                    legacy_snapshot.payload_json,
                    source=source,
                    category=category,
                    period=period,
                )
        return self.refresh_analytics_snapshot(source=source, category=category, period=period)

    def get_bulletin(
        self,
        limit: int = DEFAULT_BULLETIN_LIMIT,
        include_digests: bool = DEFAULT_BULLETIN_INCLUDE_DIGESTS,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        category: str | None = None,
        source: str | None = None,
        cluster_ids: list[int] | None = None,
        categories: list[str] | None = None,
        force_refresh: bool = False,
    ) -> list[dict]:
        key = bulletin_snapshot_key(
            limit=limit,
            include_digests=include_digests,
            period_start=period_start,
            period_end=period_end,
            category=category,
            source=source,
            cluster_ids=cluster_ids,
            categories=categories,
        )
        if force_refresh:
            return self.refresh_bulletin_snapshot(
                limit=limit,
                include_digests=include_digests,
                period_start=period_start,
                period_end=period_end,
                category=category,
                source=source,
                cluster_ids=cluster_ids,
                categories=categories,
            )
        snapshot = self._get_snapshot(key)
        if snapshot:
            return snapshot.payload_json
        return []

    def refresh_default_snapshots(self) -> dict[str, str]:
        self.db.query(ReportSnapshot).filter(
            or_(
                ReportSnapshot.snapshot_key == LEGACY_ANALYTICS_SNAPSHOT_KEY,
                ReportSnapshot.snapshot_key.like(f"{ANALYTICS_SCHEMA_VERSION}:%"),
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

    def refresh_analytics_snapshot(
        self,
        source: str | None = None,
        category: str | None = None,
        period: str = DEFAULT_ANALYTICS_PERIOD,
    ) -> dict:
        period = normalize_analytics_period(period)
        payload = build_analytics_payload(self.db, source=source, category=category, period=period)
        key = analytics_snapshot_key(source=source, category=category, period=period)
        self._upsert_snapshot(
            key,
            payload,
            metadata={
                "kind": "analytics",
                "schemaVersion": ANALYTICS_SCHEMA_VERSION,
                "source": source,
                "category": category,
                "period": period,
            },
        )
        return payload

    def refresh_bulletin_snapshot(
        self,
        limit: int = DEFAULT_BULLETIN_LIMIT,
        include_digests: bool = DEFAULT_BULLETIN_INCLUDE_DIGESTS,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        category: str | None = None,
        source: str | None = None,
        cluster_ids: list[int] | None = None,
        categories: list[str] | None = None,
    ) -> list[dict]:
        payload = build_bulletin_payload(
            self.db,
            limit=limit,
            include_digests=include_digests,
            period_start=period_start,
            period_end=period_end,
            category=category,
            source=source,
            cluster_ids=cluster_ids,
            categories=categories,
        )
        key = bulletin_snapshot_key(
            limit=limit,
            include_digests=include_digests,
            period_start=period_start,
            period_end=period_end,
            category=category,
            source=source,
            cluster_ids=cluster_ids,
            categories=categories,
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
                "cluster_ids": sorted(cluster_ids or []),
                "categories": sorted(categories or []),
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


def build_analytics_payload(
    db: Session,
    source: str | None = None,
    category: str | None = None,
    period: str = DEFAULT_ANALYTICS_PERIOD,
) -> dict:
    period = normalize_analytics_period(period)
    article_query = _filtered_articles_query(db, source=source, category=category, period=period)
    total_papers = article_query.count()
    cluster_ids = [
        row[0]
        for row in article_query.with_entities(Article.cluster_id)
        .filter(Article.cluster_id.isnot(None))
        .distinct()
        .all()
    ]
    active_clusters = len(cluster_ids)
    clustered_papers = article_query.filter(Article.cluster_id.isnot(None)).count()
    avg_papers_per_cluster = clustered_papers / active_clusters if active_clusters else 0
    week_ago = datetime.utcnow() - timedelta(days=7)
    pdf_available = (
        article_query
        .filter(
            or_(
                Article.pdf_url.isnot(None),
                Article.metadata_json["has_pdf"].as_boolean().is_(True),
            )
        )
        .count()
    )

    cluster_counts = dict(
        article_query.with_entities(Article.cluster_id, func.count(Article.id))
        .filter(Article.cluster_id.isnot(None))
        .group_by(Article.cluster_id)
        .all()
    )
    clusters = (
        db.query(Cluster)
        .filter(Cluster.cluster_id.in_(cluster_ids))
        .order_by(Cluster.article_count.desc())
        .all()
        if cluster_ids
        else []
    )

    formatted_clusters = [
        _format_cluster_payload(
            cluster,
            _cluster_representation_score(cluster),
            paper_count=int(cluster_counts.get(cluster.cluster_id, cluster.article_count or 0)),
        )
        for cluster in clusters
    ]

    metrics = {
        "totalPapers": total_papers,
        "activeClusters": active_clusters,
        "avgPapersPerCluster": avg_papers_per_cluster,
        "weeklyPicks": article_query.filter(Article.publish_date >= week_ago).count(),
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

    monthly_data = _monthly_data(db, source=source, category=category, period=period)
    source_distribution = [
        {"source": source or "unknown", "count": count}
        for source, count in _filtered_articles_query(db, category=category, period=period)
        .with_entities(Article.source, func.count(Article.id))
        .group_by(Article.source)
        .all()
    ]
    category_distribution = [
        {"category": category or "unknown", "count": count}
        for category, count in (
            _filtered_articles_query(db, source=source, period=period)
            .with_entities(Article.primary_category, func.count(Article.id))
            .group_by(Article.primary_category)
            .order_by(func.count(Article.id).desc())
            .limit(20)
            .all()
        )
    ]
    cluster_trends = _cluster_trend_data(db, clusters, source=source, category=category, period=period)
    cluster_trend_data = cluster_trends["wide"]
    cluster_trend_series = cluster_trends["series"]
    rising_topics = _rising_topics(db, clusters, source=source, category=category)
    cluster_quality = _cluster_quality(db, clusters)

    return {
        "schemaVersion": ANALYTICS_SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        "filters": {
            "source": source,
            "category": category,
            "period": period,
        },
        "metrics": metrics,
        "barData": bar_data,
        "pieData": pie_data,
        "scatterData": scatter_data,
        "monthlyData": monthly_data,
        "clusters": formatted_clusters,
        "papers": [],
        "sourceDistribution": source_distribution,
        "categoryDistribution": category_distribution,
        "clusterTrendData": cluster_trend_data,
        "clusterTrendSeries": cluster_trend_series,
        "risingTopics": rising_topics,
        "clusterQuality": cluster_quality,
    }


def build_bulletin_payload(
    db: Session,
    limit: int = DEFAULT_BULLETIN_LIMIT,
    include_digests: bool = DEFAULT_BULLETIN_INCLUDE_DIGESTS,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    category: str | None = None,
    source: str | None = None,
    cluster_ids: list[int] | None = None,
    categories: list[str] | None = None,
) -> list[dict]:
    category_filters = _normalize_categories(category=category, categories=categories)
    selected_cluster_ids = sorted({int(cluster_id) for cluster_id in (cluster_ids or [])})
    cluster_query = db.query(Cluster)
    if selected_cluster_ids:
        cluster_query = cluster_query.filter(Cluster.cluster_id.in_(selected_cluster_ids))
    elif category_filters or source or period_start or period_end:
        matching_cluster_ids = [
            row[0]
            for row in _matching_article_query(
                db,
                categories=category_filters,
                source=source,
                period_start=period_start,
                period_end=period_end,
            )
            .with_entities(Article.cluster_id)
            .filter(Article.cluster_id.isnot(None))
            .distinct()
            .all()
        ]
        if not matching_cluster_ids:
            return []
        cluster_query = cluster_query.filter(Cluster.cluster_id.in_(matching_cluster_ids))

    clusters = cluster_query.order_by(Cluster.article_count.desc()).all()
    digest_service = DigestService(db)
    result_clusters = []

    for cluster in clusters:
        articles = _cluster_articles(
            db,
            cluster,
            limit,
            categories=category_filters,
            source=source,
            period_start=period_start,
            period_end=period_end,
        )
        if not articles:
            continue
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
            "cluster": _format_cluster_payload(
                cluster,
                representation_score=None,
                paper_count=_matching_article_query(
                    db,
                    cluster_id=cluster.cluster_id,
                    categories=category_filters,
                    source=source,
                    period_start=period_start,
                    period_end=period_end,
                ).count(),
            ),
            "papers": formatted_papers,
        }

        if include_digests:
            digest = digest_service.get_or_create_cluster_digest(
                cluster_id=cluster.cluster_id,
                period_start=period_start,
                period_end=period_end,
                category=category,
                categories=category_filters,
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


def empty_analytics_payload(
    snapshot_missing: bool = False,
    source: str | None = None,
    category: str | None = None,
    period: str = DEFAULT_ANALYTICS_PERIOD,
) -> dict:
    period = normalize_analytics_period(period)
    return {
        "schemaVersion": ANALYTICS_SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        "filters": {
            "source": source,
            "category": category,
            "period": period,
        },
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
        "clusterTrendData": [],
        "clusterTrendSeries": [],
        "risingTopics": [],
        "clusterQuality": empty_cluster_quality(),
        "snapshotMissing": snapshot_missing,
    }


def with_analytics_defaults(
    payload: dict,
    source: str | None = None,
    category: str | None = None,
    period: str = DEFAULT_ANALYTICS_PERIOD,
) -> dict:
    base = empty_analytics_payload(source=source, category=category, period=period)
    merged = {**base, **(payload or {})}
    merged["metrics"] = {**base["metrics"], **(payload or {}).get("metrics", {})}
    merged["filters"] = {**base["filters"], **(payload or {}).get("filters", {})}
    merged["clusterQuality"] = {**base["clusterQuality"], **(payload or {}).get("clusterQuality", {})}
    return merged


def empty_cluster_quality() -> dict:
    return {
        "outlierCount": 0,
        "outlierRatio": 0,
        "largestClusterId": None,
        "largestClusterName": None,
        "largestClusterCount": 0,
        "largestClusterRatio": 0,
        "avgRepresentationScore": 0,
        "clusteredPapers": 0,
        "totalPapersWithEmbedding": 0,
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


def _format_cluster_payload(
    cluster: Cluster,
    representation_score: float | None,
    paper_count: int | None = None,
) -> dict:
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
        "paper_count": paper_count if paper_count is not None else cluster.article_count,
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


def _filtered_articles_query(
    db: Session,
    source: str | None = None,
    category: str | None = None,
    period: str = DEFAULT_ANALYTICS_PERIOD,
):
    query = db.query(Article)
    if source:
        query = query.filter(Article.source == source)
    if category:
        query = query.filter(
            or_(
                Article.primary_category == category,
                Article.categories.ilike(f"%{category}%"),
            )
        )
    days = ANALYTICS_PERIODS[normalize_analytics_period(period)]
    if days is not None:
        query = query.filter(Article.publish_date >= datetime.utcnow() - timedelta(days=days))
    return query


def _monthly_data(
    db: Session,
    source: str | None = None,
    category: str | None = None,
    period: str = DEFAULT_ANALYTICS_PERIOD,
) -> list[dict]:
    monthly_rows = (
        _filtered_articles_query(db, source=source, category=category, period=period)
        .with_entities(
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


def _cluster_trend_data(
    db: Session,
    clusters: list[Cluster],
    source: str | None = None,
    category: str | None = None,
    period: str = DEFAULT_ANALYTICS_PERIOD,
) -> dict[str, list[dict]]:
    top_clusters = sorted(clusters, key=lambda cluster: cluster.article_count or 0, reverse=True)[:8]
    if not top_clusters:
        return {"wide": [], "series": []}

    cluster_ids = [cluster.cluster_id for cluster in top_clusters]
    cluster_names = {
        cluster.cluster_id: cluster.cluster_description or f"Cluster {cluster.cluster_id}"
        for cluster in top_clusters
    }
    rows = (
        _filtered_articles_query(db, source=source, category=category, period=period)
        .with_entities(
            Article.cluster_id,
            func.to_char(func.date_trunc("month", Article.publish_date), "YYYY-MM").label("month_key"),
            func.count(Article.id).label("count"),
        )
        .filter(Article.cluster_id.in_(cluster_ids), Article.publish_date.isnot(None))
        .group_by(Article.cluster_id, "month_key")
        .order_by("month_key")
        .all()
    )

    by_month: dict[str, dict] = {}
    series = []
    for cluster_id, month_key, count in rows:
        month = datetime.strptime(month_key, "%Y-%m").strftime("%b %y")
        month_payload = by_month.setdefault(month_key, {"month": month, "monthKey": month_key, "clusters": {}, "total": 0})
        month_payload["clusters"][str(cluster_id)] = int(count)
        month_payload["total"] += int(count)
        series.append(
            {
                "cluster_id": str(cluster_id),
                "cluster_name": cluster_names.get(cluster_id, f"Cluster {cluster_id}"),
                "month": month,
                "monthKey": month_key,
                "count": int(count),
            }
        )

    return {"wide": [by_month[key] for key in sorted(by_month)], "series": series}


def _rising_topics(
    db: Session,
    clusters: list[Cluster],
    source: str | None = None,
    category: str | None = None,
) -> list[dict]:
    now = datetime.utcnow()
    rows = []
    for cluster in clusters:
        counts = {}
        for days in (7, 30, 90):
            last_start = now - timedelta(days=days)
            prev_start = now - timedelta(days=days * 2)
            base_query = _filtered_articles_query(db, source=source, category=category, period="all").filter(
                Article.cluster_id == cluster.cluster_id
            )
            counts[f"last_{days}d"] = base_query.filter(Article.publish_date >= last_start).count()
            counts[f"prev_{days}d"] = base_query.filter(
                Article.publish_date >= prev_start,
                Article.publish_date < last_start,
            ).count()

        acceleration_7d = acceleration(counts["last_7d"], counts["prev_7d"])
        acceleration_30d = acceleration(counts["last_30d"], counts["prev_30d"])
        acceleration_90d = acceleration(counts["last_90d"], counts["prev_90d"])
        score = 0.5 * acceleration_30d + 0.3 * acceleration_90d + 0.2 * acceleration_7d
        rows.append(
            {
                "cluster_id": str(cluster.cluster_id),
                "name": cluster.cluster_description or f"Cluster {cluster.cluster_id}",
                "paper_count": cluster.article_count or 0,
                **counts,
                "acceleration_7d": round(acceleration_7d, 4),
                "acceleration_30d": round(acceleration_30d, 4),
                "acceleration_90d": round(acceleration_90d, 4),
                "score": round(score, 4),
                "color": get_color(cluster.cluster_id),
            }
        )

    return sorted(rows, key=lambda item: (item["last_30d"] > 0, item["score"], item["last_30d"], item["paper_count"]), reverse=True)[:8]


def acceleration(current: int, previous: int) -> float:
    return (current - previous) / max(previous, 1)


def _cluster_quality(db: Session, clusters: list[Cluster]) -> dict:
    total_papers_with_embedding = db.query(Article).filter(Article.embedding.isnot(None)).count()
    outlier_count = (
        db.query(Article)
        .filter(Article.embedding.isnot(None), Article.cluster_id.is_(None))
        .count()
    )
    clustered_papers = db.query(Article).filter(Article.cluster_id.isnot(None)).count()
    largest_cluster = max(clusters, key=lambda cluster: cluster.article_count or 0, default=None)
    largest_count = largest_cluster.article_count if largest_cluster else 0
    representation_scores = [
        _cluster_representation_score(cluster)
        for cluster in clusters
        if _cluster_representation_score(cluster) > 0
    ]
    quality = empty_cluster_quality()
    quality.update(
        {
            "outlierCount": outlier_count,
            "outlierRatio": round(outlier_count / total_papers_with_embedding, 4) if total_papers_with_embedding else 0,
            "largestClusterId": str(largest_cluster.cluster_id) if largest_cluster else None,
            "largestClusterName": (
                largest_cluster.cluster_description or f"Cluster {largest_cluster.cluster_id}"
                if largest_cluster
                else None
            ),
            "largestClusterCount": largest_count or 0,
            "largestClusterRatio": round(largest_count / clustered_papers, 4) if clustered_papers else 0,
            "avgRepresentationScore": round(sum(representation_scores) / len(representation_scores), 4)
            if representation_scores
            else 0,
            "clusteredPapers": clustered_papers,
            "totalPapersWithEmbedding": total_papers_with_embedding,
        }
    )
    return quality


def _normalize_categories(category: str | None = None, categories: list[str] | None = None) -> list[str]:
    values = []
    if category:
        values.append(category)
    values.extend(categories or [])
    return sorted({value.strip() for value in values if value and value.strip()})


def _matching_article_query(
    db: Session,
    cluster_id: int | None = None,
    categories: list[str] | None = None,
    source: str | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
):
    query = db.query(Article)
    if cluster_id is not None:
        query = query.filter(Article.cluster_id == cluster_id)
    if source:
        query = query.filter(Article.source == source)
    if categories:
        category_clauses = []
        for item in categories:
            category_clauses.append(Article.primary_category == item)
            category_clauses.append(Article.categories.ilike(f"%{item}%"))
        query = query.filter(or_(*category_clauses))
    if period_start:
        query = query.filter(Article.publish_date >= period_start)
    if period_end:
        query = query.filter(Article.publish_date <= period_end)
    return query


def _cluster_articles(
    db: Session,
    cluster: Cluster,
    limit: int,
    categories: list[str] | None = None,
    source: str | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> list[Article]:
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
        articles = (
            _matching_article_query(
                db,
                cluster_id=cluster.cluster_id,
                categories=categories,
                source=source,
                period_start=period_start,
                period_end=period_end,
            )
            .filter(Article.id.in_(representative_ids))
            .all()
        )
        by_id = {article.id: article for article in articles}
        ordered_articles = [by_id[article_id] for article_id in representative_ids if article_id in by_id]
        if len(ordered_articles) >= limit:
            return ordered_articles[:limit]

        remaining = (
            _matching_article_query(
                db,
                cluster_id=cluster.cluster_id,
                categories=categories,
                source=source,
                period_start=period_start,
                period_end=period_end,
            )
            .filter(Article.id.notin_(representative_ids))
            .limit(limit - len(ordered_articles))
            .all()
        )
        return ordered_articles + remaining

    return (
        _matching_article_query(
            db,
            cluster_id=cluster.cluster_id,
            categories=categories,
            source=source,
            period_start=period_start,
            period_end=period_end,
        )
        .limit(limit)
        .all()
    )
