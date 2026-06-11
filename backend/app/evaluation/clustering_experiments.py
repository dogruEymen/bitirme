from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from backend.app.evaluation.cluster_postprocess import (
    DEFAULT_CLUSTER_MERGE_THRESHOLD,
    DEFAULT_OUTLIER_REASSIGNMENT_THRESHOLD,
    merge_close_centroid_clusters,
    reassign_outliers_to_nearest_centroid,
)
from backend.app.evaluation.clustering_metrics import evaluate_clustering_records


@dataclass(frozen=True)
class ClusteringExperimentConfig:
    name: str
    min_topic_size: int
    min_samples: int
    umap_n_neighbors: int
    umap_n_components: int
    umap_min_dist: float
    cluster_selection_method: str


def write_experiment_artifacts(
    output_dir: Path,
    config: ClusteringExperimentConfig,
    article_rows: list[dict],
    embeddings,
    labels,
    outlier_threshold: float = DEFAULT_OUTLIER_REASSIGNMENT_THRESHOLD,
    merge_threshold: float = DEFAULT_CLUSTER_MERGE_THRESHOLD,
    pairwise_sample_limit: int = 500,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    matrix = np.asarray(embeddings, dtype=np.float32)
    raw_labels = np.asarray(labels, dtype=np.int64)
    reassignment = reassign_outliers_to_nearest_centroid(matrix, raw_labels, threshold=outlier_threshold)
    merge = merge_close_centroid_clusters(matrix, reassignment.labels, threshold=merge_threshold)

    records = [
        SimpleNamespace(embedding=embedding.tolist(), cluster_id=int(label))
        for embedding, label in zip(matrix, merge.labels)
    ]
    metrics = evaluate_clustering_records(
        records,
        article_count=len(records),
        embedded_article_count=len(records),
        pairwise_sample_limit=pairwise_sample_limit,
        bertopic_outlier_count=reassignment.outliers_before_reassignment,
    )

    assignment_rows = []
    for article, raw_label, reassigned_label, final_label in zip(
        article_rows,
        raw_labels,
        reassignment.labels,
        merge.labels,
    ):
        assignment_rows.append(
            {
                **article,
                "raw_topic": int(raw_label),
                "topic_after_reassignment": int(reassigned_label),
                "topic": int(final_label),
            }
        )

    summary = {
        "config": asdict(config),
        "metrics": metrics.model_dump(mode="json"),
        "outliers_before_reassignment": reassignment.outliers_before_reassignment,
        "outliers_after_reassignment": reassignment.outliers_after_reassignment,
        "reassigned_outlier_count": reassignment.reassigned_outlier_count,
        "reassignment_acceptance_rate": reassignment.reassignment_acceptance_rate,
        "cluster_count_before_merge": merge.cluster_count_before_merge,
        "cluster_count_after_merge": merge.cluster_count_after_merge,
        "merged_cluster_count": merge.merged_cluster_count,
        "largest_cluster_ratio_after_merge": merge.largest_cluster_ratio_after_merge,
    }

    _write_csv(output_dir / "paper_topic_assignments.csv", assignment_rows)
    _write_json(output_dir / "experiment_summary.json", summary)
    return summary


def select_best_experiment(summaries: list[dict]) -> dict | None:
    if not summaries:
        return None

    def score(summary: dict):
        metrics = summary["metrics"]
        return (
            metrics.get("cluster_assignment_coverage") or 0.0,
            -(metrics.get("outlier_ratio") or 0.0),
            -(metrics.get("davies_bouldin_score") or float("inf")),
            metrics.get("silhouette_score") or -1.0,
            -(metrics.get("largest_cluster_ratio") or 1.0),
        )

    return max(summaries, key=score)


def _write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not fieldnames:
            handle.write("")
            return
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
