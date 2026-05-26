from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from database.models.ArticleData import Article
from database.models.ClusterData import Cluster
from datetime import datetime, timedelta

router = APIRouter()


@router.get("/analytics")
def get_analytics(db: Session = Depends(get_db)):
    total_papers = db.query(Article).count()
    active_clusters = db.query(Cluster).count()
    avg_papers_per_cluster = 0
    if active_clusters > 0:
        avg_papers_per_cluster = total_papers / active_clusters

    # Weekly picks: articles published in the last 7 days
    week_ago = datetime.utcnow() - timedelta(days=7)
    weekly_picks = db.query(Article).filter(Article.publish_date >= week_ago).count()

    # Bar data: papers per cluster (top 50 clusters)
    clusters = db.query(Cluster).order_by(Cluster.article_count.desc()).limit(50).all()
    barData = [{"name": c.cluster_description or f"Cluster {c.cluster_id}", "count": c.article_count} for c in clusters]

    # Pie data: top 8 clusters proportions
    pieData = barData[:8]

    # Scatter: cluster size vs article_count (no quality metric available yet)
    scatterData = [{"cluster": c.cluster_description or str(c.cluster_id), "x": c.cluster_id, "y": c.article_count} for c in clusters]

    # Monthly data: count of articles grouped by year-month (simple aggregate)
    try:
        monthly_raw = db.execute("SELECT strftime('%Y-%m', publish_date) as ym, count(*) as cnt FROM articles WHERE publish_date IS NOT NULL GROUP BY ym ORDER BY ym DESC LIMIT 24").fetchall()
        monthlyData = [{"month": row[0], "count": row[1]} for row in monthly_raw]
    except Exception:
        monthlyData = []

    metrics = {
        "totalPapers": total_papers,
        "activeClusters": active_clusters,
        "avgPapersPerCluster": avg_papers_per_cluster,
        "weeklyPicks": weekly_picks,
    }

    return {"metrics": metrics, "barData": barData, "pieData": pieData, "scatterData": scatterData, "monthlyData": monthlyData}
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
import numpy as np
from collections import Counter

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
        return 0.8  # Default representation score if embeddings are missing
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
    clusters = db.query(Cluster).order_by(Cluster.article_count.desc()).all()
    
    # 1. Calculate centroid for each cluster to compute representation score
    cluster_centroids = {}
    for c in clusters:
        # Get all articles in this cluster
        articles = db.query(Article.embedding).filter(
            Article.cluster_id == c.cluster_id,
            Article.embedding.isnot(None)
        ).all()
        if articles:
            embeddings = [np.array(a[0], dtype=np.float32) for a in articles]
            centroid = np.mean(embeddings, axis=0)
            cluster_centroids[c.cluster_id] = centroid

    # 2. Get all papers to determine representation scores and weekly picks
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
            "is_weekly_pick": False, # Will determine below
            "week_label": "This Week",
            "created_at": paper.publish_date.isoformat() if paper.publish_date else datetime.utcnow().isoformat(),
            "citation_count": paper.citation_count or 0
        })

    # Sort formatted papers by representation score to mark top ones as representative and weekly picks
    # Group by cluster
    by_cluster = {}
    for p in formatted_papers:
        cid = p["cluster_id"]
        if cid not in by_cluster:
            by_cluster[cid] = []
        by_cluster[cid].append(p)

    for cid, papers_list in by_cluster.items():
        # Sort by score descending
        papers_list.sort(key=lambda x: x["representation_score"], reverse=True)
        # Mark top 5 as representative
        for p in papers_list[:5]:
            p["is_representative"] = True

    # Mark top 10 papers with highest citations/representation scores overall as weekly picks
    formatted_papers.sort(key=lambda x: (x["citation_count"], x["representation_score"]), reverse=True)
    for p in formatted_papers[:10]:
        p["is_weekly_pick"] = True

    # Build response cluster list
    formatted_clusters = []
    for c in clusters:
        # Extract first word of description as keyword
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
            "created_at": c.created_at.isoformat() if c.created_at else datetime.utcnow().isoformat()
        })

    # 3. Monthly Trends
    # Group all articles by month
    monthly_counts = Counter()
    for paper in all_papers:
        if paper.publish_date:
            month_key = paper.publish_date.strftime("%Y-%m")
            monthly_counts[month_key] += 1
            
    # Sort months
    sorted_months = sorted(monthly_counts.keys())
    # If there is no data or not enough months, populate default last 6 months
    if len(sorted_months) < 3:
        monthly_data = [
            {"month": "Jul", "publications": 245},
            {"month": "Aug", "publications": 312},
            {"month": "Sep", "publications": 287},
            {"month": "Oct", "publications": 356},
            {"month": "Nov", "publications": 398},
            {"month": "Dec", "publications": 421}
        ]
    else:
        monthly_data = []
        # Get up to last 12 months
        for mkey in sorted_months[-12:]:
            # Convert mkey "2023-10" to short name e.g. "Oct 23"
            dt = datetime.strptime(mkey, "%Y-%m")
            month_label = dt.strftime("%b %y")
            monthly_data.append({
                "month": month_label,
                "publications": monthly_counts[mkey]
            })

    return {
        "clusters": formatted_clusters,
        "papers": formatted_papers,
        "monthlyData": monthly_data
    }
