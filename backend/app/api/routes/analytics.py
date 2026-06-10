from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.services.report_snapshot_service import ReportSnapshotService

router = APIRouter()


@router.get("/analytics")
def get_analytics(
    force_refresh: bool = Query(default=False, description="Snapshot'i yeniden uret"),
    source: str | None = Query(default=None, description="Kaynak filtresi"),
    category: str | None = Query(default=None, description="Kategori filtresi"),
    period: str = Query(default="12m", description="Trend periyodu: 3m, 6m, 12m, all"),
    db: Session = Depends(get_db),
):
    return ReportSnapshotService(db).get_analytics(
        force_refresh=force_refresh,
        source=source,
        category=category,
        period=period,
    )
