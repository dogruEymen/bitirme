from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.services.digest_service import DigestService
from backend.app.services.report_snapshot_service import DEFAULT_BULLETIN_LIMIT
from backend.app.services.report_snapshot_service import ReportSnapshotService
from database.models.ArticleData import Article

router = APIRouter()


@router.get("/bulletin")
def get_bulletin(
    limit: int = Query(default=DEFAULT_BULLETIN_LIMIT, description="Maksimum makale sayisi"),
    include_digests: bool = Query(default=False, description="Cluster digest bilgisini ekle"),
    period_start: datetime | None = Query(default=None, description="Digest baslangic tarihi"),
    period_end: datetime | None = Query(default=None, description="Digest bitis tarihi"),
    category: str | None = Query(default=None, description="Kategori filtresi"),
    source: str | None = Query(default=None, description="Kaynak filtresi"),
    force_refresh: bool = Query(default=False, description="Snapshot'i yeniden uret"),
    db: Session = Depends(get_db),
):
    return ReportSnapshotService(db).get_bulletin(
        limit=limit,
        include_digests=include_digests,
        period_start=period_start,
        period_end=period_end,
        category=category,
        source=source,
        force_refresh=force_refresh,
    )


@router.get("/bulletin/articles/{article_id}")
def get_bulletin_article(article_id: int, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.id == article_id).first()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    return {
        "id": str(article.id),
        "cluster_id": str(article.cluster_id) if article.cluster_id is not None else None,
        "title": article.title,
        "abstract": article.abstract_text or "",
        "url": article.url or article.pdf_url,
        "pdf_url": article.pdf_url,
        "doi": article.doi,
        "source": article.source,
        "external_id": article.external_id,
        "authors": article.authors,
        "venue": article.venue,
        "primary_category": article.primary_category,
        "citation_count": article.citation_count or 0,
        "published_at": article.publish_date.isoformat() if article.publish_date else None,
        "has_pdf": bool(article.pdf_url or (article.metadata_json or {}).get("has_pdf")),
    }


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
