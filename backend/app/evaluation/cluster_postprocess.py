from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np


DEFAULT_OUTLIER_REASSIGNMENT_THRESHOLD = 0.90
DEFAULT_CLUSTER_MERGE_THRESHOLD = 0.99


@dataclass(frozen=True)
class ReassignmentResult:
    labels: np.ndarray
    outliers_before_reassignment: int
    outliers_after_reassignment: int
    reassigned_outlier_count: int
    reassignment_acceptance_rate: float


@dataclass(frozen=True)
class MergeResult:
    labels: np.ndarray
    merge_mapping: dict[int, int]
    cluster_count_before_merge: int
    cluster_count_after_merge: int
    merged_cluster_count: int
    largest_cluster_ratio_after_merge: float | None


def reassign_outliers_to_nearest_centroid(
    embeddings,
    labels,
    threshold: float = DEFAULT_OUTLIER_REASSIGNMENT_THRESHOLD,
) -> ReassignmentResult:
    matrix = normalize_rows(np.asarray(embeddings, dtype=np.float32))
    next_labels = np.asarray(labels, dtype=np.int64).copy()
    outlier_mask = next_labels == -1
    outliers_before = int(outlier_mask.sum())
    centroids = compute_centroids(matrix, next_labels)

    if outliers_before == 0 or not centroids:
        return ReassignmentResult(
            labels=next_labels,
            outliers_before_reassignment=outliers_before,
            outliers_after_reassignment=outliers_before,
            reassigned_outlier_count=0,
            reassignment_acceptance_rate=0.0,
        )

    centroid_labels = np.array(sorted(centroids), dtype=np.int64)
    centroid_matrix = np.vstack([centroids[int(label)] for label in centroid_labels])

    reassigned = 0
    for index in np.where(outlier_mask)[0]:
        similarities = centroid_matrix @ matrix[index]
        best_position = int(np.argmax(similarities))
        best_similarity = float(similarities[best_position])
        if best_similarity >= threshold:
            next_labels[index] = int(centroid_labels[best_position])
            reassigned += 1

    outliers_after = int((next_labels == -1).sum())
    return ReassignmentResult(
        labels=next_labels,
        outliers_before_reassignment=outliers_before,
        outliers_after_reassignment=outliers_after,
        reassigned_outlier_count=reassigned,
        reassignment_acceptance_rate=reassigned / outliers_before if outliers_before else 0.0,
    )


def merge_close_centroid_clusters(
    embeddings,
    labels,
    threshold: float = DEFAULT_CLUSTER_MERGE_THRESHOLD,
) -> MergeResult:
    matrix = normalize_rows(np.asarray(embeddings, dtype=np.float32))
    original_labels = np.asarray(labels, dtype=np.int64)
    centroids = compute_centroids(matrix, original_labels)
    cluster_labels = sorted(centroids)
    parent = {label: label for label in cluster_labels}

    def find(label: int) -> int:
        while parent[label] != label:
            parent[label] = parent[parent[label]]
            label = parent[label]
        return label

    def union(a: int, b: int) -> None:
        root_a = find(a)
        root_b = find(b)
        if root_a == root_b:
            return
        parent[max(root_a, root_b)] = min(root_a, root_b)

    for left_index, left_label in enumerate(cluster_labels):
        for right_label in cluster_labels[left_index + 1:]:
            similarity = float(centroids[left_label] @ centroids[right_label])
            if similarity >= threshold:
                union(left_label, right_label)

    merge_mapping = {label: find(label) for label in cluster_labels}
    next_labels = original_labels.copy()
    for index, label in enumerate(next_labels):
        if int(label) in merge_mapping:
            next_labels[index] = merge_mapping[int(label)]

    before_count = len(cluster_labels)
    after_count = len(set(label for label in next_labels.tolist() if label != -1))
    return MergeResult(
        labels=next_labels,
        merge_mapping=merge_mapping,
        cluster_count_before_merge=before_count,
        cluster_count_after_merge=after_count,
        merged_cluster_count=before_count - after_count,
        largest_cluster_ratio_after_merge=largest_cluster_ratio(next_labels),
    )


def compute_centroids(matrix: np.ndarray, labels: np.ndarray) -> dict[int, np.ndarray]:
    result: dict[int, np.ndarray] = {}
    for label in sorted(set(int(item) for item in labels.tolist()) - {-1}):
        cluster_vectors = matrix[labels == label]
        if cluster_vectors.size == 0:
            continue
        result[label] = normalize_rows(cluster_vectors.mean(axis=0, keepdims=True))[0]
    return result


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return matrix / norms


def largest_cluster_ratio(labels: np.ndarray) -> float | None:
    non_outlier_labels = [int(label) for label in labels.tolist() if int(label) != -1]
    if not non_outlier_labels:
        return None
    counts = Counter(non_outlier_labels)
    return max(counts.values()) / len(non_outlier_labels)
