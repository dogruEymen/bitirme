# 13_EVALUATION_METRICS_IMPLEMENTATION.md — Kodla Ölçülebilir Clustering ve RAG Evaluation

## Summary

Bu faz, API/dashboard eklemeden çalışan offline CLI evaluation sistemi kurar. Sistem clustering kalitesini mevcut DB embedding/cluster verilerinden; RAG retrieval kalitesini elle hazırlanmış golden JSON soru setinden ölçer. Raporlar `exports/evaluation/{run_id}/` altında JSON ve CSV olarak üretilir.

## Key Changes

- Yeni evaluation paketi:
  - `backend/app/evaluation/clustering_metrics.py`
  - `backend/app/evaluation/retrieval_metrics.py`
  - `backend/app/evaluation/schemas.py`
  - `backend/app/evaluation/report_writer.py`
  - `scripts/run_evaluation.py`
- Clustering metrikleri:
  - `silhouette_score`, `davies_bouldin_score`, `calinski_harabasz_score`
  - `outlier_ratio`, `cluster_count`, `largest_cluster_ratio`, `median_cluster_size`
  - `avg_intra_cluster_cosine_similarity`, `avg_centroid_similarity`
- Retrieval metrikleri:
  - `hit@k`, `recall@k`, `precision@k`, `mrr`, `ndcg@k`
  - `retrieved_article_ids`, `latency_ms`
  - hafif cevap sinyalleri: `uses_rag`, `source_count`, `citation_marker_count`, `has_sources_section`, `retrieved_context_empty`

## CLI

```bash
python scripts/run_evaluation.py --suite all
python scripts/run_evaluation.py --suite clustering
python scripts/run_evaluation.py --suite retrieval --golden-file evaluation/golden_questions.json --top-k 5
```

Çıktılar:

- `exports/evaluation/{run_id}/summary.json`
- `exports/evaluation/{run_id}/retrieval_results.csv`
- `exports/evaluation/{run_id}/clustering_metrics.json`

## Test Plan

- `pytest tests/test_evaluation_metrics.py`
- `pytest tests`

## Assumptions

- İlk teslimat yalnızca CLI raporu üretir.
- Golden set elle oluşturulur.
- Yeni ağır dependency eklenmez; mevcut `numpy` ve `scikit-learn` kullanılır.
- LLM-as-judge ve semantik cevap doğruluğu bu fazda ölçülmez.
