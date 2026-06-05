from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.services.report_snapshot_service import ReportSnapshotService

router = APIRouter()


@router.get("/analytics")
def get_analytics(
    force_refresh: bool = Query(default=False, description="Snapshot'i yeniden uret"),
    db: Session = Depends(get_db),
):
    return ReportSnapshotService(db).get_analytics(force_refresh=force_refresh)
