# Hybrid Retrieval Integration Plan

## Current RAG Architecture

The current RAG path is article-level retrieval. There is no separate chunk table yet, so the first hybrid version treats each `Article` row as the retrieval chunk. The dense side uses `Article.embedding` with pgvector cosine distance. The embedding model is `intfloat/multilingual-e5-base`; query text is encoded with `query:` and document text is encoded with `passage:` through `EmbeddingService`.

The retrievable document body is currently `title + abstract_text`. Metadata is stored on the `articles` table (`source`, `doi`, `venue`, categories, dates, citations, cluster id, PDF URL, and JSON metadata). Context assembly is handled by `build_rag_context()` and sends article metadata plus a trimmed abstract to the LLM.

The old lexical branch was not BM25. It used `ILIKE` on title and abstract plus a heuristic keyword score. That helped exact title and acronym queries, but it had no inverse document frequency, no durable lexical index, weak tokenization, and scores that could not be safely combined with vector similarity.

## Target Architecture

```text
User query
-> RagRouterService
-> query embedding
-> RetrievalService
   -> VectorRetriever: pgvector cosine top-k
   -> BM25Retriever: SQLite FTS5 BM25 top-k
   -> HybridRetriever: RRF by default, weighted fusion for experiments
   -> DOI/external/article dedupe
-> final top-k articles
-> build_rag_context()
-> LLM
```

Hybrid retrieval is needed because vector search captures semantic similarity but can miss exact paper titles, acronyms, dataset names, method names, author-like names, and domain-specific phrases. BM25 captures exact lexical evidence but misses semantically close wording. The hybrid layer should improve candidate recall without simply stuffing more noisy context into the LLM.

## Implementation Decisions

- Retrieval unit: `Article` as the first-version chunk. Full-text PDF parent-child chunking is deferred.
- BM25 index: persisted SQLite FTS5 sidecar at `exports/retrieval/articles_bm25.sqlite`.
- BM25 fields: `article_id`, `title`, `abstract_text`, `source`, `primary_category`, `categories`, `cluster_id`, `doi`, `venue`, `publish_date`.
- BM25 weighting: `bm25(articles_fts, 3.0, 1.0)` so title matches carry stronger signal than abstract matches.
- Fusion v1: Reciprocal Rank Fusion with `RAG_RRF_K=60`. This avoids directly adding cosine similarity and BM25 scores, which are on incompatible scales.
- Weighted fusion: available only as an evaluation/config mode. Scores are min-max normalized per result list and combined with `RAG_WEIGHTED_ALPHA=0.65`.
- Reranker: out of v1 scope. Add a cross-encoder only if evaluation shows relevant candidates enter top-20/top-40 but fusion fails to rank them into top-5.

## Operational Steps

Build or refresh the BM25 sidecar:

```bash
.venv/bin/python scripts/build_bm25_index.py --batch-size 5000
```

Run retrieval evaluation examples:

```bash
.venv/bin/python scripts/run_evaluation.py --suite retrieval --force-rag --retrieval-mode vector --run-id vector_k5
.venv/bin/python scripts/run_evaluation.py --suite retrieval --force-rag --retrieval-mode bm25 --run-id bm25_k5
.venv/bin/python scripts/run_evaluation.py --suite retrieval --force-rag --retrieval-mode hybrid --fusion-method rrf --run-id hybrid_rrf_k5
.venv/bin/python scripts/run_evaluation.py --suite retrieval --force-rag --retrieval-mode hybrid --fusion-method weighted --run-id hybrid_weighted_k5
```

Important settings:

```text
RAG_RETRIEVAL_MODE=hybrid
RAG_VECTOR_TOP_K=25
RAG_BM25_TOP_K=25
RAG_FINAL_TOP_K=5
RAG_FUSION_METHOD=rrf
RAG_RRF_K=60
RAG_WEIGHTED_ALPHA=0.65
RAG_BM25_INDEX_PATH=exports/retrieval/articles_bm25.sqlite
RAG_DEBUG_RETRIEVAL=false
```

If the BM25 index is missing, hybrid mode logs a warning and falls back to vector-only candidates instead of failing the chat path.

## Evaluation Plan

Compare these systems on the same golden sets:

1. Vector only
2. BM25 only
3. Hybrid RRF
4. Hybrid weighted fusion
5. Hybrid plus reranker, only if v1 ranking analysis justifies it

Track Recall@5/10/20, Precision@5, MRR, nDCG, Hit Rate, retrieval latency, duplicate rate, and final source distribution (`vector`, `bm25`, `both`). A hybrid run is not automatically better because it returns more candidates; it should preserve or improve Hit@5/MRR and improve candidate recall without polluting final context.

Failure cases to inspect separately:

- Exact title, acronym, method, or dataset queries where vector misses and BM25 hits.
- Semantic queries with low lexical overlap where BM25 adds noise.
- Relevant article appears in vector/BM25 candidates but falls out after fusion.
- Metadata filters remove the correct article.
- BM25 index is stale relative to the Postgres corpus.
- Top-k is too high and context relevance drops.
