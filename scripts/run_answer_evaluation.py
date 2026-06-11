from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.database import SessionLocal
from backend.app.schemas.retrieval import RetrievalFilters
from backend.app.services.chat_orchestrator import ChatOrchestrator
from backend.app.services.conversation_memory_service import ConversationMemory
from backend.app.services.embedding_service import get_embedding_service
from backend.app.services.ollama_service import OllamaService, OllamaServiceError
from backend.app.services.rag_router_service import RagRouterService
from backend.app.services.retrieval_service import RetrievalService, build_rag_context


@dataclass
class AnswerGoldenQuestion:
    question_id: str
    question: str
    expected_article_id: int
    expected_title: str
    expected_answer: str
    evidence_from_abstract: str
    key_terms: list[str]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RAG answer generation evaluation with Ollama/Gemma.")
    parser.add_argument("--golden-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "exports/evaluation")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--force-rag", action="store_true")
    parser.add_argument("--use-llm-router", action="store_true")
    parser.add_argument("--disable-keyword", action="store_true")
    parser.add_argument("--model", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.top_k < 1:
        print("--top-k must be greater than zero.", file=sys.stderr)
        return 2

    questions = load_answer_golden_csv(args.golden_csv)
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-answer")
    run_dir = args.output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    ollama = OllamaService(model=args.model) if args.model else OllamaService()
    orchestrator = ChatOrchestrator()
    orchestrator.ollama_service = ollama
    router = RagRouterService(ollama) if args.use_llm_router else RagRouterService.__new__(RagRouterService)
    embedding_service = get_embedding_service()

    rows: list[dict] = []
    db = SessionLocal()
    try:
        retrieval_service = RetrievalService(db)
        memory = ConversationMemory(summary=None, recent_messages=[], previous_sources=[])
        for item in questions:
            start = time.perf_counter()
            if args.use_llm_router:
                import asyncio

                route_decision = asyncio.run(router.route(item.question, memory))
            else:
                route_decision = router.fallback_route(item.question, memory.previous_sources)
            if args.force_rag:
                route_decision.use_rag = True
                route_decision.reason = f"{route_decision.reason} Forced RAG for answer evaluation.".strip()
            route_decision.top_k = args.top_k

            retrieved = []
            answer = ""
            error = ""
            if route_decision.use_rag:
                query_embedding = None
                if route_decision.sort_by == "relevance":
                    query_embedding = embedding_service.embed_query(route_decision.rewritten_query)
                retrieved = retrieval_service.retrieve(
                    query_embedding=query_embedding,
                    filters=route_decision.filters or RetrievalFilters(),
                    top_k=args.top_k,
                    sort_by=route_decision.sort_by,
                    query_text=None if args.disable_keyword else route_decision.rewritten_query,
                )

            rag_context = build_rag_context(retrieved) if route_decision.use_rag else ""
            prompt = orchestrator._build_answer_prompt(item.question, memory, route_decision, rag_context, retrieved)
            try:
                answer = ollama.generate(prompt)
            except OllamaServiceError as exc:
                error = str(exc)

            latency_ms = (time.perf_counter() - start) * 1000
            retrieved_ids = [result.source.article_id for result in retrieved]
            expected_rank = retrieved_ids.index(item.expected_article_id) + 1 if item.expected_article_id in retrieved_ids else None
            row = score_answer(item, answer, retrieved_ids, expected_rank)
            row.update(
                {
                    "question_id": item.question_id,
                    "question": item.question,
                    "expected_article_id": item.expected_article_id,
                    "expected_title": item.expected_title,
                    "retrieved_article_ids": json.dumps(retrieved_ids),
                    "retrieval_hit": expected_rank is not None,
                    "expected_rank": expected_rank,
                    "uses_rag": route_decision.use_rag,
                    "source_count": len(retrieved),
                    "latency_ms": latency_ms,
                    "error": error,
                    "answer": answer,
                }
            )
            rows.append(row)
            print(
                f"{item.question_id}: retrieval_hit={row['retrieval_hit']} "
                f"rank={expected_rank} title_mentioned={row['expected_title_mentioned']} "
                f"key_term_coverage={row['key_term_coverage']:.2f}"
            )
    finally:
        db.close()

    write_rows(run_dir / "answer_results.csv", rows)
    summary = summarize(rows, run_id, args)
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Answer evaluation written to {run_dir}")
    return 0


def load_answer_golden_csv(path: Path) -> list[AnswerGoldenQuestion]:
    questions: list[AnswerGoldenQuestion] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key_terms = [term.strip() for term in row.get("key_terms", "").split(";") if term.strip()]
            questions.append(
                AnswerGoldenQuestion(
                    question_id=row["gold_id"],
                    question=row["question"],
                    expected_article_id=int(row["expected_article_id"]),
                    expected_title=row["expected_title"],
                    expected_answer=row.get("expected_answer", ""),
                    evidence_from_abstract=row.get("evidence_from_abstract", ""),
                    key_terms=key_terms,
                )
            )
    return questions


def score_answer(
    item: AnswerGoldenQuestion,
    answer: str,
    retrieved_ids: list[int],
    expected_rank: int | None,
) -> dict:
    normalized_answer = normalize(answer)
    normalized_title = normalize(item.expected_title)
    expected_title_mentioned = normalized_title in normalized_answer
    key_term_hits = [term for term in item.key_terms if normalize(term) in normalized_answer]
    key_term_coverage = len(key_term_hits) / len(item.key_terms) if item.key_terms else 0.0
    evidence_terms = important_terms(item.evidence_from_abstract)
    evidence_hits = [term for term in evidence_terms if term in normalized_answer]
    evidence_term_coverage = len(evidence_hits) / len(evidence_terms) if evidence_terms else 0.0
    citation_marker_count = len(re.findall(r"\[S\d+\]", answer or ""))
    has_sources_section = bool(
        re.search(r"(^|\n)\s*(?:#+\s*)?(?:Sources|Kaynaklar)\b\s*:?", answer or "", flags=re.IGNORECASE)
    )
    insufficient_evidence = bool(
        re.search(r"not contain enough evidence|yeterli kanıt|yeterli evidence|does not contain enough", answer or "", flags=re.IGNORECASE)
    )
    return {
        "retrieval_hit": expected_rank is not None,
        "expected_rank": expected_rank,
        "expected_title_mentioned": expected_title_mentioned,
        "key_term_hits": json.dumps(key_term_hits, ensure_ascii=False),
        "key_term_coverage": key_term_coverage,
        "evidence_term_coverage": evidence_term_coverage,
        "citation_marker_count": citation_marker_count,
        "has_sources_section": has_sources_section,
        "insufficient_evidence": insufficient_evidence,
        "answer_char_count": len(answer or ""),
    }


def important_terms(text: str) -> list[str]:
    stopwords = {
        "the",
        "and",
        "with",
        "that",
        "this",
        "from",
        "into",
        "uses",
        "use",
        "for",
        "through",
        "both",
        "real",
    }
    terms = []
    for token in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{4,}", normalize(text)):
        if token in stopwords or token in terms:
            continue
        terms.append(token)
    return terms[:20]


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def write_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict], run_id: str, args: argparse.Namespace) -> dict:
    count = len(rows)
    if not count:
        return {"run_id": run_id, "question_count": 0}
    return {
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "model": args.model,
        "top_k": args.top_k,
        "force_rag": args.force_rag,
        "use_llm_router": args.use_llm_router,
        "disable_keyword": args.disable_keyword,
        "question_count": count,
        "retrieval_hit_rate": mean(bool(row["retrieval_hit"]) for row in rows),
        "expected_title_mention_rate": mean(bool(row["expected_title_mentioned"]) for row in rows),
        "mean_key_term_coverage": mean(float(row["key_term_coverage"]) for row in rows),
        "mean_evidence_term_coverage": mean(float(row["evidence_term_coverage"]) for row in rows),
        "mean_citation_marker_count": mean(int(row["citation_marker_count"]) for row in rows),
        "sources_section_rate": mean(bool(row["has_sources_section"]) for row in rows),
        "insufficient_evidence_rate": mean(bool(row["insufficient_evidence"]) for row in rows),
        "mean_latency_ms": mean(float(row["latency_ms"]) for row in rows),
    }


def mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
