from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from database.db import Base


class UserBulletinPreference(Base):
    __tablename__ = "user_bulletin_preferences"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_bulletin_preferences_user_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    selection_type = Column(String(20), nullable=False)
    selected_cluster_ids_json = Column(JSONB, nullable=True)
    selected_categories_json = Column(JSONB, nullable=True)
    bulletin_snapshot_key = Column(String(200), nullable=False, index=True)
    notifications_enabled = Column(Boolean, default=True, nullable=False)
    notification_frequency = Column(String(20), default="weekly", nullable=False)
    last_generated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
