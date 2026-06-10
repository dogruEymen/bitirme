from __future__ import annotations

from collections import Counter
from typing import Iterable

import numpy as np
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.evaluation.schemas import ClusteringEvalResult
from database.models.ArticleData import Article


DEFAULT_PAIRWISE_SAMPLE_LIMIT = 500


def evaluate_clustering(
    db: Session,
    pairwise_sample_limit: int = DEFAULT_PAIRWISE_SAMPLE_LIMIT,
) -> ClusteringEvalResult:
    article_count = int(db.query(func.count(Article.id)).scalar() or 0)
    embedded_article_count = int(
        db.query(func.count(Article.id)).filter(Article.embedding.isnot(None)).scalar() or 0
    )
    articles = (
        db.query(Article.id, Article.embedding, Article.cluster_id)
        .filter(Article.embedding.isnot(None), Article.cluster_id.isnot(None))
        .all()
    )
    return evaluate_clustering_records(
        articles=articles,
        article_count=article_count,
        embedded_article_count=embedded_article_count,
        pairwise_sample_limit=pairwise_sample_limit,
    )


def evaluate_clustering_records(
    articles: Iterable,
    article_count: int | None = None,
    embedded_article_count: int | None = None,
    pairwise_sample_limit: int = DEFAULT_PAIRWISE_SAMPLE_LIMIT,
) -> ClusteringEvalResult:
    vectors: list[np.ndarray] = []
    labels: list[int] = []

    for article in articles:
        embedding = _embedding_from_record(article)
        cluster_id = _cluster_id_from_record(article)
        if embedding is None or cluster_id is None:
            continue
        vectors.append(embedding)
        labels.append(cluster_id)

    eval_count = len(labels)
    article_count = eval_count if article_count is None else article_count
    embedded_article_count = eval_count if embedded_article_count is None else embedded_article_count
    outlier_count = sum(1 for label in labels if label == -1)
    clustered_labels = [label for label in labels if label != -1]
    clustered_article_count = len(clustered_labels)
    cluster_sizes = Counter(clustered_labels)
    cluster_count = len(cluster_sizes)
    outlier_ratio = outlier_count / eval_count if eval_count else 0.0

    base = {
        "article_count": article_count,
        "embedded_article_count": embedded_article_count,
        "clustered_article_count": clustered_article_count,
        "outlier_count": outlier_count,
        "cluster_count": cluster_count,
        "outlier_ratio": outlier_ratio,
        "largest_cluster_ratio": _largest_cluster_ratio(cluster_sizes, clustered_article_count),
        "median_cluster_size": _median_cluster_size(cluster_sizes),
        "pairwise_sample_limit": pairwise_sample_limit,
    }

    if eval_count == 0:
        return ClusteringEvalResult(**base, skipped_reason="No articles with embeddings and cluster_id were found.")
    if clustered_article_count == 0:
        return ClusteringEvalResult(**base, skipped_reason="No non-outlier clustered articles were found.")
    if cluster_count < 2:
        return ClusteringEvalResult(**base, skipped_reason="At least two non-outlier clusters are required.")

    matrix = _normalize_rows(np.vstack(vectors).astype(np.float32))
    labels_array = np.array(labels)
    clustered_mask = labels_array != -1
    clustered_matrix = matrix[clustered_mask]
    clustered_labels_array = labels_array[clustered_mask]

    metric_values = _safe_sklearn_metrics(clustered_matrix, clustered_labels_array)
    return ClusteringEvalResult(
        **base,
        **metric_values,
        avg_intra_cluster_cosine_similarity=_avg_intra_cluster_cosine_similarity(
            clustered_matrix,
            clustered_labels_array,
            pairwise_sample_limit=pairwise_sample_limit,
        ),
        avg_centroid_similarity=_avg_centroid_similarity(clustered_matrix, clustered_labels_array),
    )


def _safe_sklearn_metrics(matrix: np.ndarray, labels: np.ndarray) -> dict[str, float | None]:
    unique_labels = set(labels.tolist())
    if matrix.shape[0] <= len(unique_labels):
        return {
            "silhouette_score": None,
            "davies_bouldin_score": None,
            "calinski_harabasz_score": None,
        }

    return {
        "silhouette_score": float(silhouette_score(matrix, labels, metric="cosine")),
        "davies_bouldin_score": float(davies_bouldin_score(matrix, labels)),
        "calinski_harabasz_score": float(calinski_harabasz_score(matrix, labels)),
    }


def _avg_intra_cluster_cosine_similarity(
    matrix: np.ndarray,
    labels: np.ndarray,
    pairwise_sample_limit: int,
) -> float | None:
    total_similarity = 0.0
    total_pairs = 0
    for label in sorted(set(labels.tolist())):
        cluster_vectors = matrix[labels == label]
        if cluster_vectors.shape[0] < 2:
            continue
        if cluster_vectors.shape[0] > pairwise_sample_limit:
            cluster_vectors = cluster_vectors[:pairwise_sample_limit]
        similarity = cluster_vectors @ cluster_vectors.T
        row_idx, col_idx = np.triu_indices(similarity.shape[0], k=1)
        values = similarity[row_idx, col_idx]
        total_similarity += float(values.sum())
        total_pairs += int(values.size)
    if total_pairs == 0:
        return None
    return total_similarity / total_pairs


def _avg_centroid_similarity(matrix: np.ndarray, labels: np.ndarray) -> float | None:
    total_similarity = 0.0
    total_articles = 0
    for label in sorted(set(labels.tolist())):
        cluster_vectors = matrix[labels == label]
        centroid = _normalize_rows(cluster_vectors.mean(axis=0, keepdims=True))[0]
        similarities = cluster_vectors @ centroid
        total_similarity += float(similarities.sum())
        total_articles += int(similarities.size)
    if total_articles == 0:
        return None
    return total_similarity / total_articles


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return matrix / norms


def _largest_cluster_ratio(cluster_sizes: Counter, clustered_article_count: int) -> float | None:
    if not cluster_sizes or clustered_article_count == 0:
        return None
    return max(cluster_sizes.values()) / clustered_article_count


def _median_cluster_size(cluster_sizes: Counter) -> float | None:
    if not cluster_sizes:
        return None
    return float(np.median(list(cluster_sizes.values())))


def _embedding_from_record(record) -> np.ndarray | None:
    value = getattr(record, "embedding", None)
    if value is None and isinstance(record, (tuple, list)) and len(record) >= 2:
        value = record[1]
    if value is None:
        return None
    if isinstance(value, str):
        value = [float(item.strip()) for item in value.strip("[]").split(",") if item.strip()]
    array = np.asarray(value, dtype=np.float32)
    if array.ndim != 1 or array.size == 0 or not np.isfinite(array).all():
        return None
    return array


def _cluster_id_from_record(record) -> int | None:
    value = getattr(record, "cluster_id", None)
    if value is None and isinstance(record, (tuple, list)) and len(record) >= 3:
        value = record[2]
    return int(value) if value is not None else None
