# 09_BACKEND_IMPLEMENTATION_PROMPT.md — Coding LLM Prompt for Backend Work

## Role

You are a Senior Backend Engineer working inside an existing FastAPI + SQLAlchemy project. Implement only the backend changes needed for metadata-aware RAG and session memory.

## Instructions

Before editing, inspect these files:

```text
backend/app/api/routes/chat.py
backend/app/services/ollama_service.py
backend/app/services/embedding_service.py
backend/app/core/config.py
backend/app/schemas/chat.py
database/models/ArticleData.py
database/models/ChatSession.py
database/models/ChatMessage.py
database/alembic/env.py
```

Do not rewrite the whole app. Refactor the chat route by moving logic into services.

## Required deliverables

1. `rag_router_service.py`
2. `retrieval_service.py`
3. `conversation_memory_service.py`
4. `chat_orchestrator.py`
5. `schemas/retrieval.py`
6. `schemas/source.py`
7. schema migration for metadata and memory fields
8. updated chat route using orchestrator
9. tests for router, retrieval, and memory

## Implementation order

1. Add config fields.
2. Add models and migration.
3. Add schemas.
4. Add retrieval service.
5. Add conversation memory service.
6. Add router service.
7. Add chat orchestrator.
8. Simplify chat route.
9. Add tests.

## Hard rules

- Do not add LangChain or LlamaIndex.
- Do not add a new vector DB.
- Do not store chain-of-thought.
- Do not break existing frontend session endpoints.
- Do not remove existing article columns.
- Do not return fake sources.

## Acceptance examples

Question: `RAG nedir?`

Expected:

- `use_rag=false`,
- no retrieval call,
- normal answer.

Question: `Son 30 günde arXiv kaynaklı RAG makalelerini özetle`

Expected:

- `use_rag=true`,
- `source=arxiv`,
- explicit date range,
- cited answer.

Question: `Önceki cevaptaki ikinci makaleyi detaylandır`

Expected:

- uses previous assistant message metadata,
- resolves second source to an `article_id`,
- retrieves or directly loads that article,
- answers with citation.
