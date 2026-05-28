# 04_RETRIEVAL_METADATA_FILTERING.md — Metadata-Aware Retrieval Service

## Role

You are a Senior AI Engineer implementing the retrieval layer for RAG. Your goal is better answers through filtered, explainable retrieval, not maximal complexity.

## Target files

Create:

```text
backend/app/services/retrieval_service.py
backend/app/schemas/retrieval.py
backend/app/schemas/source.py
```

## Pydantic schemas

Create `RetrievalFilters`:

```python
class RetrievalFilters(BaseModel):
    source: str | None = None
    cluster_id: int | None = None
    primary_category: str | None = None
    categories_any: list[str] = []
    venue: str | None = None
    doi: str | None = None
    has_pdf: bool | None = None
    min_citation_count: int | None = None
    publish_date_from: date | None = None
    publish_date_to: date | None = None
    article_ids: list[int] = []
```

Create `RetrievedArticle`:

```python
class RetrievedArticle(BaseModel):
    source_id: str
    article_id: int
    title: str
    authors: str | None
    venue: str | None
    publish_date: str | None
    doi: str | None
    url: str | None
    abstract_text: str | None
    cluster_id: int | None
    primary_category: str | None
    score: float
```

## Retrieval function

Implement:

```python
def search_articles(
    db: Session,
    query_embedding: list[float],
    filters: RetrievalFilters,
    top_k: int = 5,
    candidate_k: int = 25,
) -> list[RetrievedArticle]:
    ...
```

## SQL filter order

Apply filters before vector ordering:

```text
embedding IS NOT NULL
article_ids if present
source
cluster_id
primary_category
categories_any
venue
doi
has_pdf
min_citation_count
publish_date_from
publish_date_to
```

Then order by:

```python
Article.embedding.cosine_distance(query_embedding)
```

Fetch `candidate_k`, then rerank lightly.

## Lightweight reranking

Do not add a cross-encoder in MVP. Use simple scoring:

```text
final_score = vector_similarity
            + recency_bonus
            + citation_bonus
            - missing_abstract_penalty
```

Rules:

- `vector_similarity = 1 - cosine_distance`.
- `recency_bonus` should be small, for example max `0.05`, only when date exists.
- `citation_bonus` should be small, for example max `0.03`, only when citation count exists.
- Missing abstract penalty can be `0.05`.
- Deduplicate by DOI first, then by external_id.

The score does not need to be perfect. It only needs to avoid obviously bad ordering.

## Source formatting

Assign `source_id` after final ranking:

```text
S1, S2, S3, ...
```

The source block passed to the LLM should look like:

```text
[S1]
article_id: 123
title: ...
authors: ...
venue: ...
publish_date: ...
doi: ...
url: ...
cluster_id: ...
category: ...
abstract: ...
```

Truncate abstracts if needed, but do not remove titles, DOI, or URLs.

## Follow-up retrieval using previous sources

If `filters.article_ids` is non-empty, prioritize those article IDs. This is necessary for:

- “ikinci makaleyi detaylandır”,
- “bunları tablo yap”,
- “bu kaynakların DOI’lerini ver”,
- “önceki cevaptaki paperları karşılaştır”.

In this case, still use vector search if there are many article IDs, but for one to five article IDs, direct lookup is acceptable and simpler.

## Empty result behavior

Return an empty list. Do not fabricate sources. The final prompt must tell the user that the local database does not contain enough matching evidence.

## Acceptance criteria

- Date/source/category filters actually change results.
- Previous-source follow-ups work through `article_ids`.
- Returned sources include all citation metadata.
- Empty result is handled gracefully.
