# 00_PROJECT_REVIEW.md — Existing Repository Review

## Role

You are a Senior AI Engineer reviewing an existing academic literature tracking project. Your task is not to redesign the whole repository. Your task is to identify what already exists, what is missing, and how to extend it safely.

## Current useful assets

The repository already has a solid MVP foundation:

- FastAPI backend under `backend/app`.
- Existing chat routes under `backend/app/api/routes/chat.py`.
- Existing analytics and bulletin routes.
- Existing SQLAlchemy models under `database/models`.
- Existing `Article` model with pgvector `Vector(768)` embedding.
- Existing `EmbeddingService` using `intfloat/multilingual-e5-base`.
- Existing Ollama service abstraction.
- Existing BERTopic clustering script.
- Existing React frontend.

Do not throw these away.

## Main gaps to fix

### 1. RAG is not actually implemented yet

The chat route currently builds a prompt from recent messages and streams directly from Ollama. It does not route, retrieve, cite, or store source metadata.

Required fix:

- Add `rag_router_service.py`.
- Add `retrieval_service.py`.
- Add `conversation_memory_service.py`.
- Add `chat_orchestrator.py`.
- Make the chat route delegate orchestration instead of doing everything inline.

### 2. Embeddings need retrieval metadata

The `Article` model has `embedding`, but RAG needs more than a vector. Retrieval must support filtering by source, date, category, cluster, venue, DOI, PDF availability, citation count, and other metadata.

Required fix:

- Keep explicit columns for common filters.
- Add `metadata_json` for flexible source-specific metadata.
- Add `embedding_model`, `embedding_text_hash`, and `embedding_created_at` for embedding lifecycle management.

### 3. Conversation memory exists only as raw last messages

The chat route loads recent messages, but the system lacks a clean memory abstraction. It also does not preserve previous RAG source metadata for follow-up questions.

Required fix:

- Add timestamps to sessions/messages.
- Add `chat_sessions.summary`.
- Add `chat_messages.metadata_json`.
- Build a memory block for routing and answer generation.

### 4. Analytics route has duplicate definitions

`analytics.py` contains duplicate route definitions and should be cleaned. The dashboard should only consume real data.

### 5. Model config is inconsistent

`backend/app/core/config.py` still points to `gemma2:2b`. The MVP target is local Ollama with `gemma4:e4b`.

## Extension principle

Make the code more modular, but not more complex than needed.

Good changes:

- small services,
- typed Pydantic schemas,
- clear SQLAlchemy queries,
- JSONB metadata,
- deterministic fallback logic,
- simple tests.

Avoid:

- LangChain,
- LlamaIndex,
- external vector DB,
- complex agent frameworks,
- background queues for flows that can run as scripts,
- frontend rewrites.

## Final expectation

After these changes, a user should be able to ask:

- “RAG nedir?” and receive a normal LLM answer.
- “Bu sistemdeki son RAG paperlarını özetle” and receive a sourced RAG answer.
- “Önceki cevaptaki ikinci makaleyi detaylandır” and receive a follow-up answer using previous chat memory and previous sources.
