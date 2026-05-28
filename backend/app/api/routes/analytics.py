from fastapi import APIRouter, Depends
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import numpy as np

from backend.app.core.database import get_db
from database.models.ClusterData import Cluster
from database.models.ArticleData import Article

router = APIRouter()

COLORS = [
    "#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6", 
    "#ec4899", "#14b8a6", "#6366f1", "#06b6d4", "#f43f5e",
    "#059669", "#2563eb", "#d97706", "#dc2626", "#7c3aed",
    "#db2777", "#0d9488", "#4f46e5", "#0891b2", "#e11d48"
]

def get_color(cluster_id: int) -> str:
    return COLORS[abs(cluster_id) % len(COLORS)]

def calculate_cosine_similarity(v1, v2):
    if v1 is None or v2 is None:
        return 0.0
    arr1 = np.array(v1, dtype=np.float32)
    arr2 = np.array(v2, dtype=np.float32)
    dot = np.dot(arr1, arr2)
    norm1 = np.linalg.norm(arr1)
    norm2 = np.linalg.norm(arr2)
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return float(dot / (norm1 * norm2))

@router.get("/analytics")
def get_analytics(db: Session = Depends(get_db)):
    total_papers = db.query(Article).count()
    active_clusters = db.query(Cluster).count()
    clustered_papers = db.query(Article).filter(Article.cluster_id.isnot(None)).count()
    avg_papers_per_cluster = clustered_papers / active_clusters if active_clusters else 0
    week_ago = datetime.utcnow() - timedelta(days=7)
    weekly_picks = db.query(Article).filter(Article.publish_date >= week_ago).count()
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

    cluster_centroids = {}
    for c in clusters:
        articles = db.query(Article.embedding).filter(
            Article.cluster_id == c.cluster_id,
            Article.embedding.isnot(None)
        ).all()
        if articles:
            embeddings = [np.array(a[0], dtype=np.float32) for a in articles]
            centroid = np.mean(embeddings, axis=0)
            cluster_centroids[c.cluster_id] = centroid

    all_papers = db.query(Article).filter(Article.cluster_id.isnot(None)).all()

    formatted_papers = []
    for paper in all_papers:
        centroid = cluster_centroids.get(paper.cluster_id)
        if centroid is not None and paper.embedding is not None:
            score = calculate_cosine_similarity(paper.embedding, centroid)
        else:
            score = 0.8
        
        # Build reference string
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
            "is_representative": False, # Will determine based on top scores or metadata
            "representation_score": score,
            "published_at": paper.publish_date.isoformat() if paper.publish_date else None,
            "is_weekly_pick": bool(paper.publish_date and paper.publish_date >= week_ago),
            "week_label": "This Week",
            "created_at": paper.publish_date.isoformat() if paper.publish_date else datetime.utcnow().isoformat(),
            "citation_count": paper.citation_count or 0,
            "source": paper.source,
            "primary_category": paper.primary_category,
            "doi": paper.doi,
            "url": paper.url or paper.pdf_url,
            "has_pdf": bool(paper.pdf_url or (paper.metadata_json or {}).get("has_pdf")),
        })

    by_cluster = {}
    for p in formatted_papers:
        cid = p["cluster_id"]
        if cid not in by_cluster:
            by_cluster[cid] = []
        by_cluster[cid].append(p)

    avg_representation_by_cluster = {}
    for cid, papers_list in by_cluster.items():
        papers_list.sort(key=lambda x: x["representation_score"], reverse=True)
        avg_representation_by_cluster[cid] = (
            sum(p["representation_score"] for p in papers_list) / len(papers_list)
            if papers_list
            else 0
        )
        for p in papers_list[:5]:
            p["is_representative"] = True

    formatted_papers.sort(key=lambda x: (x["citation_count"], x["representation_score"]), reverse=True)

    formatted_clusters = []
    for c in clusters:
        desc = c.cluster_description or ""
        keyword = desc.split(",")[0].strip() if "," in desc else desc.split(" ")[0].strip()
        if not keyword:
            keyword = f"Topic {c.cluster_id}"
            
        formatted_clusters.append({
            "id": str(c.cluster_id),
            "name": c.cluster_description or f"Cluster {c.cluster_id}",
            "keyword": keyword,
            "description": c.cluster_description or "",
            "color": get_color(c.cluster_id),
            "paper_count": c.article_count,
            "created_at": c.created_at.isoformat() if c.created_at else datetime.utcnow().isoformat(),
            "metadata": c.metadata_json or {},
            "representation_score": avg_representation_by_cluster.get(str(c.cluster_id), 0),
        })

    metrics = {
        "totalPapers": total_papers,
        "activeClusters": active_clusters,
        "avgPapersPerCluster": avg_papers_per_cluster,
        "weeklyPicks": weekly_picks,
        "clusteredPapers": clustered_papers,
        "pdfAvailable": pdf_available,
    }

    barData = [{"name": c["name"], "count": c["paper_count"], "color": c["color"], "papers": c["paper_count"]} for c in formatted_clusters]
    pieData = [{"name": b["name"], "value": b["count"], "color": b["color"]} for b in barData[:8]]
    scatterData = [
        {
            "cluster": c["name"],
            "fullName": c["name"],
            "x": c["paper_count"],
            "y": round((c.get("representation_score") or 0) * 100, 2),
            "z": c["paper_count"],
            "color": c["color"],
        }
        for c in formatted_clusters
    ]

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
    monthly_data = [
        {
            "month": datetime.strptime(row._mapping["month_key"], "%Y-%m").strftime("%b %y"),
            "count": int(row._mapping["count"]),
            "publications": int(row._mapping["count"]),
        }
        for row in monthly_rows[-12:]
    ]

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
        "barData": barData,
        "pieData": pieData,
        "scatterData": scatterData,
        "monthlyData": monthly_data,
        "clusters": formatted_clusters,
        "papers": formatted_papers,
        "sourceDistribution": source_distribution,
        "categoryDistribution": category_distribution,
    }
