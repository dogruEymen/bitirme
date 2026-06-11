from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from backend.app.evaluation.schemas import (
    ClusteringEvalResult,
    RetrievalEvalResult,
    RetrievalEvalSummary,
)


def new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def write_evaluation_report(
    output_root: Path,
    run_id: str,
    suite: str,
    clustering_result: ClusteringEvalResult | None = None,
    retrieval_results: list[RetrievalEvalResult] | None = None,
    retrieval_summary: RetrievalEvalSummary | None = None,
) -> Path:
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if clustering_result is not None:
        _write_json(run_dir / "clustering_metrics.json", clustering_result)

    if retrieval_results is not None:
        _write_retrieval_csv(run_dir / "retrieval_results.csv", retrieval_results)

    summary = {
        "run_id": run_id,
        "suite": suite,
        "generated_at": datetime.now(UTC).isoformat(),
        "clustering": _dump(clustering_result) if clustering_result is not None else None,
        "retrieval": {
            "summary": _dump(retrieval_summary),
            "question_count": len(retrieval_results or []),
        } if retrieval_results is not None else None,
    }
    _write_json(run_dir / "summary.json", summary)
    return run_dir


def _write_json(path: Path, payload: BaseModel | dict[str, Any]) -> None:
    path.write_text(
        json.dumps(_dump(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_retrieval_csv(path: Path, results: list[RetrievalEvalResult]) -> None:
    fieldnames = [
        "question_id",
        "question",
        "expected_article_ids",
        "retrieved_article_ids",
        "rewritten_query",
        "route_reason",
        "filters",
        "sort_by",
        "hit_at_k",
        "recall_at_k",
        "precision_at_k",
        "mrr",
        "ndcg_at_k",
        "latency_ms",
        "top_k",
        "retrieval_mode",
        "fusion_method",
        "bm25_index_status",
        "duplicate_rate",
        "vector_result_count",
        "bm25_result_count",
        "hybrid_result_count",
        "uses_rag",
        "source_count",
        "citation_marker_count",
        "has_sources_section",
        "retrieved_context_empty",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            row = result.model_dump()
            row["expected_article_ids"] = json.dumps(row["expected_article_ids"])
            row["retrieved_article_ids"] = json.dumps(row["retrieved_article_ids"])
            row["filters"] = json.dumps(row["filters"], ensure_ascii=False, sort_keys=True)
            writer.writerow(row)


def _dump(payload):
    if payload is None:
        return None
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    return payload
