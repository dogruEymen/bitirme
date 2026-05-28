# 02_RAG_ROUTING_AND_CHAT.md — RAG Routing, Metadata Filters, and Chat Orchestration

## Role

You are a Senior AI Engineer implementing a minimal but production-shaped RAG chat flow. You must preserve existing FastAPI endpoints and frontend compatibility.

## Target files

Create:

```text
backend/app/services/rag_router_service.py
backend/app/services/retrieval_service.py
backend/app/services/conversation_memory_service.py
backend/app/services/chat_orchestrator.py
backend/app/schemas/retrieval.py
backend/app/schemas/source.py
```

Modify:

```text
backend/app/api/routes/chat.py
backend/app/schemas/chat.py
backend/app/services/ollama_service.py
backend/app/services/embedding_service.py
```

## End-to-end chat flow

```text
POST /chat/sessions/{session_id}/message
  -> identify user
  -> validate session ownership
  -> save user message
  -> load conversation memory
  -> route question with LLM
  -> parse strict JSON route decision
  -> fallback heuristic if JSON fails
  -> if route.use_rag:
       -> embed route.rewritten_query
       -> retrieve using vector similarity + metadata filters
       -> build RAG context
  -> generate final answer with memory + context
  -> save assistant message with metadata_json
  -> stream answer as text/plain
```

The existing simple `/chat` endpoint can remain as a non-session fallback, but the real MVP path should be session-based because memory requires a session.

## Router prompt behavior

The router is not the answer generator. It only decides whether retrieval is needed and what filters to apply.

Router input:

- current user message,
- conversation summary,
- recent messages,
- previous cited sources,
- current date.

Router output must be strict JSON:

```json
{
  "use_rag": true,
  "reason": "The user asks about stored papers and asks for recent results.",
  "rewritten_query": "recent retrieval augmented generation papers",
  "filters": {
    "source": "arxiv",
    "cluster_id": null,
    "primary_category": "cs.CL",
    "categories_any": ["cs.CL"],
    "venue": null,
    "doi": null,
    "has_pdf": null,
    "min_citation_count": null,
    "publish_date_from": "2026-04-28",
    "publish_date_to": "2026-05-28",
    "article_ids": []
  },
  "top_k": 5
}
```

Add `article_ids` because follow-up questions may refer to previous sources. Example: “ikinci makaleyi detaylandır” should map to the second source from previous assistant metadata.

## Filter extraction rules

Use filters only when clearly justified.

Examples:

- “arXiv’den gelenler” -> `source="arxiv"`.
- “cs.CL paperları” -> `primary_category="cs.CL"` or `categories_any=["cs.CL"]`.
- “son 30 gün” -> explicit date range.
- “PDF’i olanlar” -> `has_pdf=true`.
- “citation sayısı yüksek olanlar” -> do not guess a threshold unless user gives one; prefer reranking by citation count.
- “doi’si 10.x olan makale” -> `doi="10.x"`.
- “cluster 4” -> `cluster_id=4`.
- “önceki cevaptaki ikinci makale” -> `article_ids=[previous_sources[1].article_id]`.

## Fallback heuristic

If the LLM router returns invalid JSON, implement deterministic fallback:

Use RAG if message contains any of:

```text
paper, papers, makale, makaleler, article, articles, yayın, publication,
cluster, topic, abstract, özet, veritabanı, bu sistemde, kaynak,
arxiv, doi, son yayın, haftalık, aylık, trend, önceki makale, bunlar,
ikinci makale, bu cluster
```

Do not use RAG for:

```text
selam, merhaba, nasılsın, RAG nedir, LLM nedir, bana Python anlat,
uygulamayı nasıl kullanırım
```

When in doubt, prefer RAG only if the user appears to refer to stored project data.

## Final answer prompt behavior

Final answer input:

- current user message,
- conversation memory block,
- route decision,
- retrieved context if any.

When RAG is used:

- Answer in the user’s language.
- Use only retrieved context for paper-specific claims.
- Cite paper-specific claims using `[S1]`, `[S2]`, etc.
- Include a `Sources` section.
- If context is weak, say the local database did not contain enough evidence.

When RAG is not used:

- Use conversation memory for continuity.
- Do not invent stored paper names, DOI values, cluster IDs, or database statistics.

## Chat message metadata

Save assistant message with metadata:

```json
{
  "used_rag": true,
  "model": "gemma4:e4b",
  "route_decision": {...},
  "retrieval_filters": {...},
  "sources": [
    {
      "source_id": "S1",
      "article_id": 123,
      "title": "...",
      "doi": "...",
      "url": "...",
      "score": 0.82
    }
  ]
}
```

This metadata is essential for follow-up questions. Do not skip it.

## Streaming strategy

For MVP, keep streaming plain text. Build the answer stream from Ollama and save the full response at the end. The frontend can display citations and sources as normal text.

Do not introduce a complex SSE/JSON streaming protocol unless plain streaming already works.

## Acceptance criteria

- “RAG nedir?” returns a normal LLM answer without retrieval.
- “Bu sistemdeki son RAG makalelerini özetle” uses retrieval and citations.
- “Sadece arXiv kaynaklı olanları göster” uses source filter.
- “PDF’i olanları filtrele” uses metadata filter.
- “Önceki cevaptaki ikinci makaleyi detaylandır” uses previous sources from chat memory.
- Assistant messages persist `sources` and `route_decision` in `metadata_json`.
