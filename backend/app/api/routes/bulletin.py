from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime
import numpy as np

from backend.app.core.database import get_db
from backend.app.services.digest_service import DigestService
from database.models.ClusterData import Cluster
from database.models.ArticleData import Article

router = APIRouter()

COLORS = [
    "#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6", 
    "#ec4899", "#14b8a6", "#6366f1", "#06b6d4", "#f43f5e"
]

def get_color(cluster_id: int) -> str:
    return COLORS[abs(cluster_id) % len(COLORS)]

def calculate_cosine_similarity(v1, v2):
    if v1 is None or v2 is None:
        return 0.8  # Default representation score if embeddings are missing
    arr1 = np.array(v1, dtype=np.float32)
    arr2 = np.array(v2, dtype=np.float32)
    dot = np.dot(arr1, arr2)
    norm1 = np.linalg.norm(arr1)
    norm2 = np.linalg.norm(arr2)
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return float(dot / (norm1 * norm2))

@router.get("/bulletin")
def get_bulletin(
    limit: int = Query(default=50, description="Maksimum makale sayisi"),
    include_digests: bool = Query(default=False, description="Cluster digest bilgisini ekle"),
    period_start: datetime | None = Query(default=None, description="Digest baslangic tarihi"),
    period_end: datetime | None = Query(default=None, description="Digest bitis tarihi"),
    category: str | None = Query(default=None, description="Kategori filtresi"),
    source: str | None = Query(default=None, description="Kaynak filtresi"),
    db: Session = Depends(get_db)
):
    clusters = db.query(Cluster).order_by(Cluster.article_count.desc()).all()
    digest_service = DigestService(db)
    
    # Pre-calculate centroids for clusters
    centroids = {}
    for c in clusters:
        # Get all embeddings in this cluster to calculate the average embedding
        articles_emb = db.query(Article.embedding).filter(
            Article.cluster_id == c.cluster_id,
            Article.embedding.isnot(None)
        ).all()
        if articles_emb:
            embeddings = [np.array(a[0], dtype=np.float32) for a in articles_emb]
            centroids[c.cluster_id] = np.mean(embeddings, axis=0)

    # Format the results
    result_clusters = []
    for c in clusters:
        articles = _cluster_articles(db, c, limit)
        
        # Extract first word of description as keyword
        desc = c.cluster_description or ""
        keyword = desc.split(",")[0].strip() if "," in desc else desc.split(" ")[0].strip()
        if not keyword:
            keyword = f"Topic {c.cluster_id}"
            
        cluster_color = get_color(c.cluster_id)
        
        formatted_papers = []
        centroid = centroids.get(c.cluster_id)
        
        for paper in articles:
            # Compute representation score
            if centroid is not None and paper.embedding is not None:
                score = calculate_cosine_similarity(paper.embedding, centroid)
            else:
                score = 0.8
                
            authors_str = paper.authors or "Unknown Authors"
            venue_str = paper.venue or "Unknown Venue"
            year_str = str(paper.publish_date.year) if paper.publish_date else ""
            ref = f"{authors_str} - {venue_str} ({year_str})" if year_str else f"{authors_str} - {venue_str}"
            
            formatted_papers.append({
                "id": str(paper.id),
                "cluster_id": str(paper.cluster_id),
                "title": paper.title,
                "reference": ref,
                "abstract": paper.abstract_text or "",
                "url": paper.url or paper.pdf_url,
                "is_representative": True, # For UI styling
                "representation_score": score,
                "published_at": paper.publish_date.isoformat() if paper.publish_date else None,
                "is_weekly_pick": False, # Will be set on a global basis if needed
                "week_label": "This Week",
                "created_at": paper.publish_date.isoformat() if paper.publish_date else datetime.utcnow().isoformat(),
            })
            
        # Sort papers by representation score
        formatted_papers.sort(key=lambda x: x["representation_score"], reverse=True)
            
        cluster_payload = {
            "cluster": {
                "id": str(c.cluster_id),
                "name": c.cluster_description or f"Cluster {c.cluster_id}",
                "keyword": keyword,
                "description": c.cluster_description or "",
                "color": cluster_color,
                "paper_count": c.article_count,
                "created_at": c.created_at.isoformat() if c.created_at else datetime.utcnow().isoformat(),
                "metadata": c.metadata_json or {},
            },
            "papers": formatted_papers
        }

        if include_digests:
            cluster_payload["digest"] = digest_service.get_or_create_cluster_digest(
                cluster_id=c.cluster_id,
                period_start=period_start,
                period_end=period_end,
                category=category,
                source=source,
                max_articles=min(max(limit, 1), 10),
                use_llm=False,
            )

        result_clusters.append(cluster_payload)
        
    return result_clusters


@router.get("/bulletin/clusters/{cluster_id}/digest")
def get_cluster_digest(
    cluster_id: int,
    period_start: datetime | None = Query(default=None, description="Digest baslangic tarihi"),
    period_end: datetime | None = Query(default=None, description="Digest bitis tarihi"),
    category: str | None = Query(default=None, description="Kategori filtresi"),
    source: str | None = Query(default=None, description="Kaynak filtresi"),
    max_articles: int = Query(default=5, ge=1, le=10, description="Digest icin temsilci makale sayisi"),
    use_llm: bool = Query(default=True, description="Ollama ile ozet uret"),
    db: Session = Depends(get_db),
):
    return DigestService(db).get_or_create_cluster_digest(
        cluster_id=cluster_id,
        period_start=period_start,
        period_end=period_end,
        category=category,
        source=source,
        max_articles=max_articles,
        use_llm=use_llm,
    )


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
