from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.services.ollama_service import OllamaService, OllamaServiceError
from database.models.ChatMessage import ChatMessage
from database.models.ChatSession import ChatSession


MAX_PREVIOUS_SOURCES = 10


@dataclass
class ConversationMemory:
    summary: str | None
    recent_messages: list[ChatMessage]
    previous_sources: list[dict]

    def as_prompt_block(self) -> str:
        lines: list[str] = [
            "Conversation summary:",
            self.summary or "No summary yet.",
        ]

        lines.append("")
        lines.append("Recent messages:")
        if self.recent_messages:
            for message in self.recent_messages:
                role = "User" if message.role == "user" else "Assistant"
                lines.append(f"{role}: {message.content}")
        else:
            lines.append("No recent messages.")

        lines.append("")
        lines.append("Previous cited sources:")
        if self.previous_sources:
            for index, source in enumerate(self.previous_sources, start=1):
                title = source.get("title") or "Untitled"
                article_id = source.get("article_id")
                source_id = source.get("source_id") or f"S{index}"
                doi = source.get("doi") or "None"
                url = source.get("url") or source.get("pdf_url") or "None"
                lines.append(f"[{source_id}] article_id={article_id} title=\"{title}\" doi=\"{doi}\" url=\"{url}\"")
        else:
            lines.append("No previous cited sources.")

        return "\n".join(lines).strip()


class ConversationMemoryService:
    def __init__(self, db: Session):
        self.db = db

    def load_memory(self, session_id: int) -> ConversationMemory:
        session = self.db.query(ChatSession).filter(ChatSession.id == session_id).first()
        recent_messages = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.chat_id == session_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(settings.CHAT_HISTORY_LIMIT)
            .all()
        )
        recent_messages.reverse()

        return ConversationMemory(
            summary=session.summary if session else None,
            recent_messages=recent_messages,
            previous_sources=self._previous_sources(session_id),
        )

    def _previous_sources(self, session_id: int) -> list[dict]:
        messages = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.chat_id == session_id, ChatMessage.role == "agent")
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(settings.CHAT_HISTORY_LIMIT)
            .all()
        )
        sources: list[dict] = []
        seen_article_ids: set[int] = set()
        for message in messages:
            metadata = message.metadata_json or {}
            for source in metadata.get("sources") or []:
                article_id = source.get("article_id")
                if article_id in seen_article_ids:
                    continue
                if article_id is not None:
                    seen_article_ids.add(article_id)
                sources.append(source)
                if len(sources) >= MAX_PREVIOUS_SOURCES:
                    return sources

        return sources

    async def update_summary_if_needed(self, session_id: int, ollama_service: OllamaService) -> bool:
        session = self.db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            return False

        total_messages = self.db.query(ChatMessage).filter(ChatMessage.chat_id == session_id).count()
        if total_messages < settings.CHAT_SUMMARY_TRIGGER_MESSAGES:
            return False

        if session.summary_updated_at:
            messages_since_summary = (
                self.db.query(ChatMessage)
                .filter(
                    ChatMessage.chat_id == session_id,
                    ChatMessage.created_at > session.summary_updated_at,
                )
                .count()
            )
            if messages_since_summary < settings.CHAT_SUMMARY_TRIGGER_MESSAGES:
                return False

        messages = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.chat_id == session_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(settings.CHAT_SUMMARY_TRIGGER_MESSAGES)
            .all()
        )
        messages.reverse()
        prompt = self._summary_prompt(session.summary, messages, self._previous_sources(session_id))
        try:
            summary = await ollama_service.generate_async(prompt)
        except OllamaServiceError:
            return False

        cleaned_summary = summary.strip()
        if not cleaned_summary:
            return False

        session.summary = cleaned_summary[:4000]
        session.summary_updated_at = datetime.utcnow()
        session.updated_at = datetime.utcnow()
        self.db.commit()
        return True

    @staticmethod
    def _summary_prompt(existing_summary: str | None, messages: list[ChatMessage], previous_sources: list[dict]) -> str:
        lines = [
            "Summarize this chat session for future assistant continuity.",
            "Keep it factual and compact.",
            "Include:",
            "- the user's research intent,",
            "- mentioned topics/clusters/papers,",
            "- important cited article IDs/titles,",
            "- unresolved follow-up tasks.",
            "Do not include hidden reasoning.",
            "",
            "Existing summary:",
            existing_summary or "No summary yet.",
            "",
            "Recent session messages:",
        ]
        for message in messages:
            role = "User" if message.role == "user" else "Assistant"
            lines.append(f"{role}: {message.content}")

        lines.append("")
        lines.append("Recent cited sources:")
        if previous_sources:
            for source in previous_sources:
                lines.append(
                    f"article_id={source.get('article_id')} title=\"{source.get('title') or 'Untitled'}\" "
                    f"doi=\"{source.get('doi') or 'None'}\" url=\"{source.get('url') or source.get('pdf_url') or 'None'}\""
                )
        else:
            lines.append("No cited sources.")

        return "\n".join(lines)
