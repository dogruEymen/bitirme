# 03_INGESTION_AND_EMBEDDING.md — Ingestion, Embedding, and Metadata Enrichment

## Role

You are a Senior AI/Data Engineer. Your task is to make ingestion and embeddings useful for metadata-aware RAG. Keep the pipeline script-based and simple for MVP.

## Target files

Modify:

```text
ai_engine/ingestion/loader.py
ai_engine/ingestion/schemas.py
ai_engine/embeddings/embeddings_to_db.py
ai_engine/embeddings/model.py
backend/app/services/embedding_service.py
database/models/ArticleData.py
```

## Design rule

A vector without metadata is not enough. Every article used for RAG should answer:

- where did it come from,
- when was it published,
- what category/topic/cluster does it belong to,
- does it have a PDF,
- what DOI/URL should be cited,
- which embedding model generated the vector,
- what text was embedded.

## Normalized article metadata

During ingestion, normalize these fields:

```text
source
external_id
title
abstract_text
publish_date
updated_date
authors
url
pdf_url
primary_category
categories
doi
citation_count
venue
language
document_type
ingestion_run_id
metadata_json
```

`metadata_json` should contain structured lists and source-specific values:

```json
{
  "authors_list": ["..."],
  "categories_list": ["cs.CL", "cs.AI"],
  "has_pdf": true,
  "publish_year": 2026,
  "publish_month": 5,
  "source_payload_version": "v1"
}
```

Do not store only a raw API response. Keep metadata small and useful. If raw payload is needed later, store it in object storage or a separate table, not in MVP.

## Embedding input format

Use one deterministic function for document text:

```text
passage: {title}

{abstract_text}

metadata: source={source}; venue={venue}; category={primary_category}; date={publish_date}
```

Reasoning:

- title and abstract carry semantic meaning,
- selected metadata helps retrieval when terms are sparse,
- deterministic text enables hashing and skip logic.

## Hashing and skip logic

In `embeddings_to_db.py`:

1. Build embedding input text.
2. Compute `sha256` hash.
3. Skip article if:
   - `embedding is not null`,
   - `embedding_model == EMBEDDING_MODEL_NAME`,
   - `embedding_text_hash == current_hash`.
4. Otherwise generate embedding and update:
   - `embedding`,
   - `embedding_model`,
   - `embedding_text_hash`,
   - `embedding_created_at`.

## Query embedding

Keep query embedding format:

```text
query: {rewritten_query}
```

Do not include metadata in query embeddings. Metadata filters are handled by SQL filters, not by injecting fake metadata into the query.

## Handling missing metadata

The pipeline must not fail when DOI, venue, PDF URL, citation count, or category is missing. Use `None` and let retrieval filters ignore unavailable fields.

## Acceptance criteria

- Running ingestion creates articles with normalized metadata.
- Running embeddings stores model, hash, timestamp, and vector.
- Re-running embeddings skips unchanged articles.
- Retrieval can filter on source, publish date, category, DOI, PDF availability, and cluster.
- No ingestion code depends on a specific single source forever.
