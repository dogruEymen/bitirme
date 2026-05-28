# 10_AI_PIPELINE_PROMPT.md — Coding LLM Prompt for Ingestion, Embedding, Clustering, and Digest

## Role

You are a Senior AI/Data Engineer. You are improving an existing academic literature pipeline. Keep the pipeline simple, scriptable, and compatible with the backend schema.

## Inspect first

```text
ai_engine/ingestion/loader.py
ai_engine/ingestion/schemas.py
ai_engine/embeddings/embeddings_to_db.py
ai_engine/embeddings/model.py
ai_engine/clustering/ClusterFunctions.py
database/models/ArticleData.py
database/models/ClusterData.py
backend/app/services/embedding_service.py
```

## Required work

### Ingestion

Normalize metadata into explicit columns plus `metadata_json`.

Required explicit fields:

```text
source, external_id, title, abstract_text, publish_date, updated_date,
authors, url, pdf_url, primary_category, categories, doi, citation_count,
venue, language, document_type, ingestion_run_id
```

Required JSON fields:

```text
authors_list, categories_list, has_pdf, publish_year, publish_month,
source-specific small metadata
```

### Embeddings

Use deterministic embedding text:

```text
passage: {title}

{abstract_text}

metadata: source={source}; venue={venue}; category={primary_category}; date={publish_date}
```

Store:

```text
embedding, embedding_model, embedding_text_hash, embedding_created_at
```

Skip unchanged embeddings.

### Clustering

Use BERTopic with precomputed embeddings. Use title + abstract text. Store `Article.cluster_id`. Store cluster keywords and representative article IDs. Prefer centroid-based representative selection.

### Digest

Generate digest from real cluster articles. Use recency, centrality, and citation count. Include article IDs and source metadata. Do not return placeholders.

## Hard rules

- Do not recompute embeddings inside clustering unless requested.
- Do not delete all useful cluster data without rebuilding it transactionally.
- Do not rely on Ollama for clustering to succeed.
- Do not fabricate citation counts or DOI values.

## Acceptance criteria

- Ingested articles contain metadata.
- Embedding script is idempotent.
- Retrieval filters have data to operate on.
- Clustering is repeatable.
- Digest uses real papers only.
