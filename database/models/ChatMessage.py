from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from database.db import Base

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id      = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role    = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    metadata_json = Column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint("role IN ('user', 'agent')", name="check_chat_message_role"),
    )
