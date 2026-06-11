from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.database import SessionLocal
from backend.app.evaluation.clustering_metrics import evaluate_clustering
from backend.app.evaluation.report_writer import new_run_id, write_evaluation_report
from backend.app.evaluation.retrieval_metrics import (
    evaluate_retrieval_questions,
    load_golden_questions,
    summarize_retrieval_results,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline clustering and RAG retrieval evaluation.")
    parser.add_argument("--suite", choices=("all", "clustering", "retrieval"), default="all")
    parser.add_argument("--golden-file", type=Path, default=PROJECT_ROOT / "evaluation/golden_questions.json")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--override-question-top-k",
        action="store_true",
        help="Use --top-k for every golden question even when the golden file contains per-question top_k values.",
    )
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "exports/evaluation")
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--use-llm-router",
        action="store_true",
        help="Use the configured LLM router instead of the deterministic fallback router.",
    )
    parser.add_argument(
        "--force-rag",
        action="store_true",
        help="Force retrieval for every golden question to isolate router failures from retriever quality.",
    )
    parser.add_argument(
        "--disable-keyword",
        action="store_true",
        help="Disable keyword retrieval during evaluation to measure dense vector retrieval in isolation.",
    )
    parser.add_argument(
        "--retrieval-mode",
        choices=("hybrid", "vector", "bm25"),
        default="hybrid",
        help="Retriever mode used for retrieval evaluation.",
    )
    parser.add_argument(
        "--fusion-method",
        choices=("rrf", "weighted"),
        default="rrf",
        help="Fusion method used when --retrieval-mode=hybrid.",
    )
    parser.add_argument("--vector-top-k", type=int, default=None, help="Vector candidate count.")
    parser.add_argument("--bm25-top-k", type=int, default=None, help="BM25 candidate count.")
    parser.add_argument("--final-top-k", type=int, default=None, help="Final context result count.")
    parser.add_argument(
        "--pairwise-sample-limit",
        type=int,
        default=500,
        help="Maximum articles per cluster used for pairwise cosine similarity.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.top_k < 1:
        print("--top-k must be greater than zero.", file=sys.stderr)
        return 2
    if args.pairwise_sample_limit < 2:
        print("--pairwise-sample-limit must be at least 2.", file=sys.stderr)
        return 2
    for option_name in ("vector_top_k", "bm25_top_k", "final_top_k"):
        value = getattr(args, option_name)
        if value is not None and value < 1:
            print(f"--{option_name.replace('_', '-')} must be greater than zero.", file=sys.stderr)
            return 2

    questions = None
    if args.suite in {"all", "retrieval"}:
        try:
            questions = load_golden_questions(args.golden_file)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if args.override_question_top_k:
            for question in questions:
                question.top_k = args.top_k

    db = SessionLocal()
    try:
        clustering_result = None
        retrieval_results = None
        retrieval_summary = None

        if args.suite in {"all", "clustering"}:
            clustering_result = evaluate_clustering(
                db,
                pairwise_sample_limit=args.pairwise_sample_limit,
            )

        if args.suite in {"all", "retrieval"}:
            from backend.app.services.embedding_service import get_embedding_service

            embedding_service = get_embedding_service()
            retrieval_results = asyncio.run(
                evaluate_retrieval_questions(
                    db=db,
                    questions=questions or [],
                    top_k=args.top_k,
                    embedding_service=embedding_service,
                    use_llm_router=args.use_llm_router,
                    force_rag=args.force_rag,
                    use_keyword=not args.disable_keyword,
                    retrieval_mode=args.retrieval_mode,
                    fusion_method=args.fusion_method,
                    vector_top_k=args.vector_top_k,
                    bm25_top_k=args.bm25_top_k,
                    final_top_k=args.final_top_k,
                )
            )
            retrieval_summary = summarize_retrieval_results(retrieval_results)

        run_id = args.run_id or new_run_id()
        run_dir = write_evaluation_report(
            output_root=args.output_dir,
            run_id=run_id,
            suite=args.suite,
            clustering_result=clustering_result,
            retrieval_results=retrieval_results,
            retrieval_summary=retrieval_summary,
        )
    finally:
        db.close()

    print(f"Evaluation report written to {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
