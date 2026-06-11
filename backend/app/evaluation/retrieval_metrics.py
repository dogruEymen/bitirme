from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.app.evaluation.schemas import GoldenQuestion, RetrievalEvalResult, RetrievalEvalSummary
from backend.app.schemas.retrieval import RetrievedArticle, RetrievalFilters, RouteDecision
from backend.app.services.conversation_memory_service import ConversationMemory
from backend.app.services.rag_router_service import RagRouterService
from backend.app.services.retrieval_service import RetrievalService


class QueryEmbeddingService(Protocol):
    def embed_query(self, query: str) -> list[float]:
        ...


def dedupe_preserving_order(values: list[int]) -> list[int]:
    seen: set[int] = set()
    deduped: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def score_retrieval(
    expected_article_ids: list[int],
    retrieved_article_ids: list[int],
    top_k: int,
) -> dict[str, float | bool | list[int]]:
    if not expected_article_ids:
        raise ValueError("expected_article_ids must contain at least one article id.")
    if top_k < 1:
        raise ValueError("top_k must be greater than zero.")

    expected = set(expected_article_ids)
    retrieved = dedupe_preserving_order(retrieved_article_ids)[:top_k]
    relevant_positions = [index for index, article_id in enumerate(retrieved, start=1) if article_id in expected]
    hit_count = len(relevant_positions)

    dcg = sum(1.0 / math.log2(position + 1) for position in relevant_positions)
    ideal_hits = min(len(expected), top_k)
    idcg = sum(1.0 / math.log2(position + 1) for position in range(1, ideal_hits + 1))

    return {
        "retrieved_article_ids": retrieved,
        "hit_at_k": hit_count > 0,
        "recall_at_k": hit_count / len(expected),
        "precision_at_k": hit_count / top_k,
        "mrr": 1.0 / relevant_positions[0] if relevant_positions else 0.0,
        "ndcg_at_k": dcg / idcg if idcg else 0.0,
    }


def answer_quality_signals(answer: str, uses_rag: bool, source_count: int) -> dict[str, bool | int]:
    citation_marker_count = len(re.findall(r"\[S\d+\]", answer or ""))
    return {
        "uses_rag": uses_rag,
        "source_count": source_count,
        "citation_marker_count": citation_marker_count,
        "has_sources_section": bool(re.search(r"(^|\n)\s*Sources\s*:", answer or "", flags=re.IGNORECASE)),
        "retrieved_context_empty": source_count == 0,
    }


def load_golden_questions(path: Path) -> list[GoldenQuestion]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed golden questions JSON: {exc}") from exc

    records = raw.get("questions") if isinstance(raw, dict) else raw
    if not isinstance(records, list):
        raise ValueError("Golden questions JSON must be a list or an object with a 'questions' list.")

    try:
        return [GoldenQuestion.model_validate(record) for record in records]
    except ValidationError as exc:
        raise ValueError(f"Invalid golden question record: {exc}") from exc


async def evaluate_retrieval_questions(
    db: Session,
    questions: list[GoldenQuestion],
    top_k: int,
    embedding_service: QueryEmbeddingService,
    retrieval_service: RetrievalService | None = None,
    use_llm_router: bool = False,
    force_rag: bool = False,
    use_keyword: bool = True,
) -> list[RetrievalEvalResult]:
    if top_k < 1:
        raise ValueError("top_k must be greater than zero.")

    retrieval_service = retrieval_service or RetrievalService(db)
    router = RagRouterService() if use_llm_router else RagRouterService.__new__(RagRouterService)
    results: list[RetrievalEvalResult] = []

    for question in questions:
        effective_top_k = question.top_k or top_k
        start = time.perf_counter()
        route_decision = await _route_question(router, question.question, use_llm_router)
        if force_rag:
            route_decision.use_rag = True
            route_decision.reason = f"{route_decision.reason} Forced RAG for retrieval evaluation.".strip()
        route_decision.top_k = effective_top_k
        route_decision.filters = _merge_eval_filters(route_decision.filters, question.filters)

        retrieved: list[RetrievedArticle] = []
        if route_decision.use_rag:
            query_embedding = None
            if route_decision.sort_by == "relevance":
                query_embedding = embedding_service.embed_query(route_decision.rewritten_query)
            retrieved = retrieval_service.retrieve(
                query_embedding=query_embedding,
                filters=route_decision.filters,
                top_k=effective_top_k,
                sort_by=route_decision.sort_by,
                query_text=route_decision.rewritten_query if use_keyword else None,
            )

        latency_ms = (time.perf_counter() - start) * 1000
        retrieved_ids = [item.source.article_id for item in retrieved]
        scores = score_retrieval(question.expected_article_ids, retrieved_ids, effective_top_k)
        answer_signals = answer_quality_signals("", route_decision.use_rag, len(retrieved))

        results.append(
            RetrievalEvalResult(
                question_id=question.id,
                question=question.question,
                expected_article_ids=question.expected_article_ids,
                retrieved_article_ids=scores["retrieved_article_ids"],
                rewritten_query=route_decision.rewritten_query,
                route_reason=route_decision.reason,
                filters=route_decision.filters.model_dump(mode="json"),
                sort_by=route_decision.sort_by,
                hit_at_k=bool(scores["hit_at_k"]),
                recall_at_k=float(scores["recall_at_k"]),
                precision_at_k=float(scores["precision_at_k"]),
                mrr=float(scores["mrr"]),
                ndcg_at_k=float(scores["ndcg_at_k"]),
                latency_ms=latency_ms,
                top_k=effective_top_k,
                uses_rag=bool(answer_signals["uses_rag"]),
                source_count=int(answer_signals["source_count"]),
                citation_marker_count=int(answer_signals["citation_marker_count"]),
                has_sources_section=bool(answer_signals["has_sources_section"]),
                retrieved_context_empty=bool(answer_signals["retrieved_context_empty"]),
            )
        )

    return results


def summarize_retrieval_results(results: list[RetrievalEvalResult]) -> RetrievalEvalSummary:
    if not results:
        return RetrievalEvalSummary(
            question_count=0,
            hit_rate_at_k=0.0,
            mean_recall_at_k=0.0,
            mean_precision_at_k=0.0,
            mean_mrr=0.0,
            mean_ndcg_at_k=0.0,
            mean_latency_ms=0.0,
        )

    count = len(results)
    return RetrievalEvalSummary(
        question_count=count,
        hit_rate_at_k=sum(1 for result in results if result.hit_at_k) / count,
        mean_recall_at_k=sum(result.recall_at_k for result in results) / count,
        mean_precision_at_k=sum(result.precision_at_k for result in results) / count,
        mean_mrr=sum(result.mrr for result in results) / count,
        mean_ndcg_at_k=sum(result.ndcg_at_k for result in results) / count,
        mean_latency_ms=sum(result.latency_ms for result in results) / count,
    )


async def _route_question(router: RagRouterService, question: str, use_llm_router: bool) -> RouteDecision:
    memory = ConversationMemory(summary=None, recent_messages=[], previous_sources=[])
    if use_llm_router:
        return await router.route(question, memory)
    return router.fallback_route(question, memory.previous_sources)


def _merge_eval_filters(route_filters: RetrievalFilters, override: dict) -> RetrievalFilters:
    if not override:
        return route_filters
    data = route_filters.model_dump()
    data.update(override)
    return RetrievalFilters.model_validate(data)
