from datetime import datetime

from backend.app.services.report_snapshot_service import (
    ANALYTICS_SNAPSHOT_KEY,
    ANALYTICS_SCHEMA_VERSION,
    DEFAULT_BULLETIN_INCLUDE_DIGESTS,
    DEFAULT_BULLETIN_LIMIT,
    acceleration,
    analytics_snapshot_key,
    bulletin_snapshot_key,
    default_bulletin_snapshot_key,
    empty_cluster_quality,
)
from database.db import Base
from database.models.ReportSnapshot import ReportSnapshot


def test_report_snapshot_model_registered():
    assert ReportSnapshot.__tablename__ in Base.metadata.tables


def test_analytics_snapshot_key_is_stable():
    assert ANALYTICS_SNAPSHOT_KEY == analytics_snapshot_key()
    assert ANALYTICS_SNAPSHOT_KEY.startswith(f"{ANALYTICS_SCHEMA_VERSION}:")


def test_analytics_snapshot_key_changes_with_filters():
    base_key = analytics_snapshot_key()
    filtered_key = analytics_snapshot_key(source="arxiv", category="cs.CL", period="3m")

    assert filtered_key.startswith(f"{ANALYTICS_SCHEMA_VERSION}:")
    assert base_key != filtered_key


def test_acceleration_handles_zero_previous_window():
    assert acceleration(5, 0) == 5
    assert acceleration(0, 0) == 0


def test_empty_cluster_quality_avoids_zero_division_defaults():
    quality = empty_cluster_quality()

    assert quality["outlierRatio"] == 0
    assert quality["largestClusterRatio"] == 0
    assert quality["avgRepresentationScore"] == 0


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
