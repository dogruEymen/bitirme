from datetime import datetime

from backend.app.schemas.retrieval import RetrievalFilters, RouteDecision
from backend.app.schemas.retrieval import RetrievedArticle
from backend.app.schemas.source import SourceReference
from backend.app.services.chat_orchestrator import ChatOrchestrator, _format_sources_section, _has_sources_section
from backend.app.services.conversation_memory_service import ConversationMemory


def test_rag_answer_prompt_requires_sources_with_publish_date():
    orchestrator = ChatOrchestrator.__new__(ChatOrchestrator)
    memory = ConversationMemory(summary=None, recent_messages=[], previous_sources=[])
    route_decision = RouteDecision(
        use_rag=True,
        reason="test",
        rewritten_query="retrieval question",
        filters=RetrievalFilters(),
        top_k=5,
    )

    prompt = orchestrator._build_answer_prompt(
        message="retrieval question",
        memory=memory,
        route_decision=route_decision,
        rag_context="[S1]\ntitle: Example\npublish_date: 2026-01-02",
        retrieved=[],
    )

    assert "Sources:" in prompt
    assert "Kaynaklar:" in prompt
    assert "Published: YYYY-MM-DD" in prompt
    assert "Yayın tarihi: YYYY-MM-DD" in prompt
    assert "Published: Unknown" in prompt
    assert "Yayın tarihi: Bilinmiyor" in prompt


def test_source_section_helpers_support_publish_date_and_turkish_heading():
    retrieved = [
        RetrievedArticle(
            source=SourceReference(
                source_id="S1",
                article_id=10,
                title="Example Paper",
                url="https://example.test/paper",
                publish_date=datetime(2026, 1, 2),
            )
        )
    ]

    section = _format_sources_section(retrieved)

    assert _has_sources_section(section)
    assert _has_sources_section("Kaynaklar:\n[S1] Ornek")
    assert "[S1] Example Paper - Published: 2026-01-02 - https://example.test/paper" in section
