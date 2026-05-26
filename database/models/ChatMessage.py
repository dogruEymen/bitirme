from sqlalchemy import Column, String, Integer, Text, ForeignKey, CheckConstraint

from database.db import Base

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id      = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role    = Column(String, nullable=False)
    content = Column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("role IN ('user', 'agent')", name="check_chat_message_role"),
    )
