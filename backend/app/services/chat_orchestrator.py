from collections.abc import AsyncIterator
from datetime import datetime

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal
from backend.app.schemas.retrieval import RetrievedArticle, RouteDecision
from backend.app.services.conversation_memory_service import ConversationMemory, ConversationMemoryService
from backend.app.services.ollama_service import OllamaServiceError, get_ollama_service
from backend.app.services.rag_router_service import RagRouterService
from backend.app.services.retrieval_service import RetrievalService, build_rag_context
from database.models.ChatMessage import ChatMessage
from database.models.ChatSession import ChatSession


class ChatOrchestrator:
    def __init__(self):
        self.ollama_service = get_ollama_service()
        self.router_service = RagRouterService(self.ollama_service)

    async def stream_session_message(
        self,
        session_id: int,
        user_id: int,
        message: str,
    ) -> AsyncIterator[str]:
        db = SessionLocal()
        full_response = ""
        route_decision: RouteDecision | None = None
        retrieved: list[RetrievedArticle] = []
        try:
            session = self._get_session(db, session_id, user_id)
            self._save_user_message(db, session, message)

            memory = ConversationMemoryService(db).load_memory(session_id)
            try:
                route_decision = await self.router_service.route(message, memory)
            except OllamaServiceError:
                route_decision = self.router_service.fallback_route(message, memory.previous_sources)

            rag_context = ""
            if route_decision.use_rag:
                query_embedding = None
                if route_decision.sort_by == "relevance":
                    from backend.app.services.embedding_service import get_embedding_service

                    embedding_service = get_embedding_service()
                    query_embedding = await run_in_threadpool(
                        embedding_service.embed_query,
                        route_decision.rewritten_query,
                    )
                retrieved = RetrievalService(db).retrieve(
                    query_embedding=query_embedding,
                    filters=route_decision.filters,
                    top_k=route_decision.top_k,
                    sort_by=route_decision.sort_by,
                )
                rag_context = build_rag_context(retrieved)

            prompt = self._build_answer_prompt(message, memory, route_decision, rag_context, retrieved)
            try:
                async for chunk in self.ollama_service.stream_generate(prompt):
                    full_response += chunk
                    yield chunk
            except OllamaServiceError as exc:
                error_text = f"Error: {str(exc)}"
                yield error_text
                return

            if full_response.strip():
                self._save_assistant_message(db, session, full_response.strip(), route_decision, retrieved)
                await ConversationMemoryService(db).update_summary_if_needed(session.id, self.ollama_service)
        finally:
            db.close()

    def _get_session(self, db: Session, session_id: int, user_id: int) -> ChatSession:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
            .first()
        )
        if session is None:
            raise ValueError("Chat session not found.")
        return session

    def _save_user_message(self, db: Session, session: ChatSession, message: str) -> None:
        user_msg = ChatMessage(chat_id=session.id, role="user", content=message)
        db.add(user_msg)
        if not session.title:
            session.title = message[:80]
        session.updated_at = datetime.utcnow()
        db.commit()

    def _save_assistant_message(
        self,
        db: Session,
        session: ChatSession,
        response: str,
        route_decision: RouteDecision,
        retrieved: list[RetrievedArticle],
    ) -> None:
        sources = [item.source.model_dump(mode="json") for item in retrieved]
        metadata = {
            "used_rag": route_decision.use_rag,
            "model": self.ollama_service.model,
            "route_decision": route_decision.model_dump(mode="json"),
            "retrieval_filters": route_decision.filters.model_dump(mode="json"),
            "sources": sources,
        }
        db.add(ChatMessage(chat_id=session.id, role="agent", content=response, metadata_json=metadata))
        session.updated_at = datetime.utcnow()
        db.commit()

    def _build_answer_prompt(
        self,
        message: str,
        memory: ConversationMemory,
        route_decision: RouteDecision,
        rag_context: str,
        retrieved: list[RetrievedArticle],
    ) -> str:
        memory_block = memory.as_prompt_block() or "No prior context."
        if route_decision.use_rag:
            source_instructions = (
                "Use only the retrieved context for paper-specific claims. "
                "Cite paper-specific claims with [S1], [S2], etc. "
                "Include a Sources section with source id, title, and URL or DOI when available. "
                "If the retrieved context is weak or empty, say the local database does not contain enough evidence."
            )
            if route_decision.sort_by == "publish_date_desc":
                source_instructions += (
                    " The retrieved context is already sorted by publish_date from newest to oldest; "
                    "preserve that order in the answer and include each paper's publish_date."
                )
        else:
            source_instructions = (
                "Answer normally using general knowledge and same-session memory. "
                "Do not invent stored paper titles, DOI values, cluster IDs, or database statistics."
            )

        route_json = route_decision.model_dump_json()
        retrieved_note = f"Retrieved {len(retrieved)} local articles." if route_decision.use_rag else "No retrieval used."
        return f"""
You are a helpful, professional Academic Research Assistant.
Answer in the user's language.

Conversation memory:
{memory_block}

Route decision:
{route_json}

Retrieval status:
{retrieved_note}

Retrieved context:
{rag_context or "No retrieved context."}

Instructions:
{source_instructions}

User message:
{message}

Assistant:
""".strip()


def get_chat_orchestrator() -> ChatOrchestrator:
    return ChatOrchestrator()
