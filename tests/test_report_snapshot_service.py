from datetime import datetime

from backend.app.services.report_snapshot_service import (
    ANALYTICS_SNAPSHOT_KEY,
    DEFAULT_BULLETIN_INCLUDE_DIGESTS,
    DEFAULT_BULLETIN_LIMIT,
    bulletin_snapshot_key,
    default_bulletin_snapshot_key,
)
from database.db import Base
from database.models.ReportSnapshot import ReportSnapshot


def test_report_snapshot_model_registered():
    assert ReportSnapshot.__tablename__ in Base.metadata.tables


def test_analytics_snapshot_key_is_stable():
    assert ANALYTICS_SNAPSHOT_KEY == "analytics:v1"


def test_default_bulletin_snapshot_key_matches_default_params():
    assert default_bulletin_snapshot_key() == bulletin_snapshot_key(
        limit=DEFAULT_BULLETIN_LIMIT,
        include_digests=DEFAULT_BULLETIN_INCLUDE_DIGESTS,
    )


def test_bulletin_snapshot_key_changes_with_filters():
    base_key = bulletin_snapshot_key(limit=50, include_digests=True)
    filtered_key = bulletin_snapshot_key(
        limit=50,
        include_digests=True,
        period_start=datetime(2026, 1, 1),
        category="cs.AI",
        source="arxiv",
    )

    assert base_key.startswith("bulletin:v1:")
    assert filtered_key.startswith("bulletin:v1:")
    assert base_key != filtered_key
