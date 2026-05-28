# 06_CLUSTERING_AND_DIGEST.md — BERTopic Clustering and Digest Generation

## Role

You are a Senior NLP Engineer. Your task is to improve existing BERTopic clustering and digest generation without turning the project into a research platform.

## Target files

Modify:

```text
ai_engine/clustering/ClusterFunctions.py
backend/app/api/routes/bulletin.py
backend/app/services/digest_service.py
database/models/ClusterData.py
```

## Clustering requirements

Use existing article embeddings. Do not recompute embeddings inside the clustering script unless explicitly requested.

Document text:

```text
{title}

{abstract_text}
```

BERTopic should use precomputed embeddings.

For each topic/cluster:

- store topic id,
- store article count,
- store keyword representation,
- optionally store LLM-generated label,
- update `Article.cluster_id`,
- compute representative articles by closeness to cluster centroid.

Outliers can have `cluster_id = NULL` for MVP.

## Metadata-aware clustering output

Cluster metadata should help later RAG and digest flows.

For each cluster, store or compute:

```json
{
  "keywords": ["retrieval", "rag", "generation"],
  "representative_article_ids": [1, 5, 8],
  "top_categories": ["cs.CL", "cs.AI"],
  "source_distribution": {"arxiv": 30, "openalex": 10},
  "date_range": {"from": "2026-01-01", "to": "2026-05-28"}
}
```

If `ClusterData` cannot hold this cleanly yet, add `metadata_json` to clusters.

## Digest generation

Create or update `digest_service.py`.

Digest selection should use:

- recency,
- representation score,
- citation count if available,
- metadata filters when requested.

For each digest:

- summarize the cluster in 3-5 sentences,
- list 3 key highlights,
- include representative papers with source IDs,
- save article IDs used for the digest.

Recommended table if not already present:

```text
cluster_digests
- id
- cluster_id
- period_start
- period_end
- summary
- highlights_json
- representative_article_ids_json
- created_at
```

If adding the table is too much for the immediate MVP, generate digest on demand but cache it later. Do not return fake data.

## RAG compatibility

Digest output should be compatible with RAG source format. If a user asks:

- “bu haftaki cs.CL cluster özeti”,
- “cluster 3 içindeki en önemli paperlar”,
- “bu bültendeki kaynakları açıkla”,

then retrieval should be able to use `cluster_id`, `publish_date`, and category metadata.

## Acceptance criteria

- Running clustering twice is idempotent.
- Dashboard cluster counts match article counts.
- Digest uses real articles only.
- If Ollama fails, clustering still works with keyword labels.
- Bulletin never returns fake placeholder summaries.
