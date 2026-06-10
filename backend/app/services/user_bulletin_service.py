from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.schemas.bulletin import BulletinPreferenceRequest
from backend.app.services.report_snapshot_service import (
    DEFAULT_BULLETIN_INCLUDE_DIGESTS,
    DEFAULT_BULLETIN_LIMIT,
    _format_cluster_payload,
    bulletin_snapshot_key,
)
from backend.app.services.report_snapshot_service import ReportSnapshotService
from database.models.ArticleData import Article
from database.models.ClusterData import Cluster
from database.models.ReportSnapshot import ReportSnapshot
from database.models.UserBulletinPreference import UserBulletinPreference


class UserBulletinService:
    def __init__(self, db: Session):
        self.db = db
        self.snapshots = ReportSnapshotService(db)

    def get_options(self) -> dict:
        clusters = (
            self.db.query(Cluster)
            .filter(Cluster.article_count > 0)
            .order_by(Cluster.article_count.desc())
            .all()
        )
        categories = [
            {"category": category, "paper_count": int(count)}
            for category, count in (
                self.db.query(Article.primary_category, func.count(Article.id))
                .filter(Article.primary_category.isnot(None), Article.primary_category != "")
                .group_by(Article.primary_category)
                .order_by(func.count(Article.id).desc(), Article.primary_category.asc())
                .all()
            )
        ]
        return {
            "clusters": [_format_cluster_payload(cluster, representation_score=None) for cluster in clusters],
            "categories": categories,
        }

    def get_user_bulletin(self, user_id: int, force_refresh: bool = False) -> dict:
        preference = self._get_preference(user_id)
        if preference is None:
            return {
                "configured": False,
                "preference": None,
                "bulletin": [],
            }

        payload = None
        snapshot = self._get_snapshot(preference.bulletin_snapshot_key)
        if snapshot and not force_refresh:
            payload = snapshot.payload_json
        else:
            payload = self._refresh_preference_snapshot(preference)

        return {
            "configured": True,
            "preference": self._format_preference(preference),
            "bulletin": payload,
        }

    def save_preference(self, user_id: int, request: BulletinPreferenceRequest) -> dict:
        selected_cluster_ids = sorted({int(value) for value in request.cluster_ids}) if request.selection_type == "clusters" else []
        selected_categories = (
            sorted({value.strip() for value in request.categories if value and value.strip()})
            if request.selection_type == "categories"
            else []
        )
        snapshot_key = bulletin_snapshot_key(
            limit=request.limit,
            include_digests=request.include_digests,
            cluster_ids=selected_cluster_ids,
            categories=selected_categories,
        )
        payload = self.snapshots.refresh_bulletin_snapshot(
            limit=request.limit,
            include_digests=request.include_digests,
            cluster_ids=selected_cluster_ids,
            categories=selected_categories,
        )

        now = datetime.now(UTC).replace(tzinfo=None)
        preference = self._get_preference(user_id)
        if preference is None:
            preference = UserBulletinPreference(user_id=user_id)
            self.db.add(preference)

        preference.selection_type = request.selection_type
        preference.selected_cluster_ids_json = selected_cluster_ids
        preference.selected_categories_json = selected_categories
        preference.bulletin_snapshot_key = snapshot_key
        preference.notifications_enabled = request.notifications_enabled
        preference.notification_frequency = "weekly"
        preference.last_generated_at = now
        preference.updated_at = now
        if preference.created_at is None:
            preference.created_at = now
        self.db.commit()
        self.db.refresh(preference)

        return {
            "configured": True,
            "preference": self._format_preference(preference),
            "bulletin": payload,
        }

    def _refresh_preference_snapshot(self, preference: UserBulletinPreference) -> list[dict]:
        selected_cluster_ids = preference.selected_cluster_ids_json or []
        selected_categories = preference.selected_categories_json or []
        payload = self.snapshots.refresh_bulletin_snapshot(
            limit=DEFAULT_BULLETIN_LIMIT,
            include_digests=DEFAULT_BULLETIN_INCLUDE_DIGESTS,
            cluster_ids=selected_cluster_ids,
            categories=selected_categories,
        )
        preference.last_generated_at = datetime.now(UTC).replace(tzinfo=None)
        self.db.commit()
        return payload

    def _get_preference(self, user_id: int) -> UserBulletinPreference | None:
        return (
            self.db.query(UserBulletinPreference)
            .filter(UserBulletinPreference.user_id == user_id)
            .first()
        )

    def _get_snapshot(self, snapshot_key: str) -> ReportSnapshot | None:
        return self.db.query(ReportSnapshot).filter(ReportSnapshot.snapshot_key == snapshot_key).first()

    @staticmethod
    def _format_preference(preference: UserBulletinPreference) -> dict:
        return {
            "selection_type": preference.selection_type,
            "cluster_ids": preference.selected_cluster_ids_json or [],
            "categories": preference.selected_categories_json or [],
            "notifications_enabled": preference.notifications_enabled,
            "notification_frequency": preference.notification_frequency,
            "last_generated_at": preference.last_generated_at.isoformat() if preference.last_generated_at else None,
            "created_at": preference.created_at.isoformat() if preference.created_at else None,
            "updated_at": preference.updated_at.isoformat() if preference.updated_at else None,
        }
