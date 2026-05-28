from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB

from database.db import Base


class ClusterDigest(Base):
    __tablename__ = "cluster_digests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(Integer, nullable=False, index=True)
    period_start = Column(DateTime, nullable=True, index=True)
    period_end = Column(DateTime, nullable=True, index=True)
    summary = Column(Text, nullable=False)
    highlights_json = Column(JSONB, nullable=True)
    representative_article_ids_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
