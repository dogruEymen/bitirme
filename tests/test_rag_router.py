import asyncio
import json

from backend.app.services.conversation_memory_service import ConversationMemory
from backend.app.services.rag_router_service import RagRouterService


class FakeOllama:
    def __init__(self, response: str):
        self.response = response

    async def generate_async(self, prompt: str) -> str:
        return self.response


def memory(previous_sources=None):
    return ConversationMemory(summary=None, recent_messages=[], previous_sources=previous_sources or [])


def test_valid_json_route_decision_parses_correctly():
    response = json.dumps(
        {
            "use_rag": True,
            "reason": "stored papers",
            "rewritten_query": "recent RAG papers",
            "filters": {"source": "arxiv", "categories_any": ["cs.CL"], "publish_date_from": "2026-01-01"},
            "top_k": 3,
        }
    )

    route = asyncio.run(RagRouterService(FakeOllama(response)).route("son arxiv RAG makaleleri", memory()))

    assert route.use_rag is True
    assert route.filters.source == "arxiv"
    assert route.filters.categories_any == ["cs.CL"]
    assert route.filters.publish_date_from.isoformat() == "2026-01-01"
    assert route.top_k == 3


def test_invalid_json_falls_back_to_heuristic():
    route = asyncio.run(RagRouterService(FakeOllama("not json")).route("Sadece arXiv kaynakli olanlari goster", memory()))

    assert route.use_rag is True
    assert route.filters.source == "arxiv"


def test_generic_questions_do_not_use_rag():
    route = RagRouterService().fallback_route("RAG nedir?", [])

    assert route.use_rag is False


def test_stored_paper_questions_use_rag():
    route = RagRouterService().fallback_route("Bu sistemdeki son RAG makalelerini ozetle", [])

    assert route.use_rag is True


def test_newest_paper_question_uses_publish_date_sort_and_requested_count():
    route = RagRouterService().fallback_route("Yayın tarihi en yeni 5 makaleyi göster", [])

    assert route.use_rag is True
    assert route.sort_by == "publish_date_desc"
    assert route.top_k == 5


def test_date_source_category_filters_parse():
    route = RagRouterService().fallback_route("son 30 gun arXiv cs.CL paperlari", [])

    assert route.use_rag is True
    assert route.filters.source == "arxiv"
    assert route.filters.primary_category == "cs.CL"
    assert route.filters.publish_date_from is not None
    assert route.filters.publish_date_to is not None


def test_follow_up_reference_produces_article_ids():
    previous_sources = [
        {"source_id": "S1", "article_id": 10, "title": "First"},
        {"source_id": "S2", "article_id": 20, "title": "Second"},
    ]

    route = RagRouterService().fallback_route("Onceki cevaptaki ikinci makaleyi detaylandir", previous_sources)
    source_route = RagRouterService().fallback_route("S2 ne diyor?", previous_sources)

    assert route.filters.article_ids == [20]
    assert source_route.filters.article_ids == [20]
