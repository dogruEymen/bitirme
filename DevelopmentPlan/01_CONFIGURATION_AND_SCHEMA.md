# 01_CONFIGURATION_AND_SCHEMA.md — Configuration, Database Schema, and Migrations

## Role

You are a Senior Backend Engineer. Your job is to make configuration and schema stable for the MVP. Do not change unrelated application logic.

## Goals

1. Use `gemma4:e4b` by default.
2. Make PostgreSQL + pgvector the expected database.
3. Add metadata fields required by RAG filtering.
4. Add chat memory fields required by conversation continuity.
5. Use Alembic migrations only. Do not mutate schema during app startup.

## Configuration updates

Update `backend/app/core/config.py` so it supports at least:

```python
MODEL_NAME: str = "gemma4:e4b"
OLLAMA_BASE_URL: str = "http://ollama:11434"
EMBEDDING_MODEL_NAME: str = "intfloat/multilingual-e5-base"
RAG_TOP_K: int = 5
RAG_CANDIDATE_K: int = 25
CHAT_HISTORY_LIMIT: int = 12
CHAT_SUMMARY_TRIGGER_MESSAGES: int = 24
DATABASE_URL: str
```

Create or update `.env.example`:

```env
MODEL_NAME=gemma4:e4b
OLLAMA_BASE_URL=http://ollama:11434
EMBEDDING_MODEL_NAME=intfloat/multilingual-e5-base
RAG_TOP_K=5
RAG_CANDIDATE_K=25
CHAT_HISTORY_LIMIT=12
CHAT_SUMMARY_TRIGGER_MESSAGES=24
DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/literature
POSTGRES_DB=literature
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
```

## Article schema updates

Modify `database/models/ArticleData.py`.

Keep existing columns. Add only what is needed:

```python
from sqlalchemy.dialects.postgresql import JSONB

embedding_model = Column(String(120), nullable=True)
embedding_text_hash = Column(String(64), nullable=True, index=True)
embedding_created_at = Column(DateTime, nullable=True)
metadata_json = Column(JSONB, nullable=True)
language = Column(String(20), nullable=True, index=True)
document_type = Column(String(50), nullable=True, index=True)
ingestion_run_id = Column(String(80), nullable=True, index=True)
```

Why these fields exist:

- `embedding_model`: lets us know which embedding model produced the vector.
- `embedding_text_hash`: prevents unnecessary re-embedding.
- `embedding_created_at`: helps debugging stale vectors.
- `metadata_json`: stores flexible source-specific fields without a migration every week.
- `language`, `document_type`, `ingestion_run_id`: useful MVP filters and debugging fields.

Do not remove explicit columns like `source`, `doi`, `venue`, `publish_date`, `cluster_id`, or `primary_category`. These should remain normal indexed columns because retrieval filters will use them often.

## Chat schema updates

Modify `database/models/ChatSession.py`:

```python
title = Column(String(255), nullable=True)
summary = Column(Text, nullable=True)
summary_updated_at = Column(DateTime, nullable=True)
created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
```

Modify `database/models/ChatMessage.py`:

```python
from sqlalchemy.dialects.postgresql import JSONB

created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
metadata_json = Column(JSONB, nullable=True)
```

Role values can remain `user` and `agent` for backward compatibility. Convert `agent` to `assistant` only at API boundary if the frontend expects it.

## Metadata JSON contract

For `articles.metadata_json`, use this shape where possible:

```json
{
  "source": "arxiv",
  "external_id": "...",
  "doi": "...",
  "url": "...",
  "pdf_url": "...",
  "venue": "...",
  "publish_year": 2025,
  "publish_month": 5,
  "authors_list": ["Alice", "Bob"],
  "categories_list": ["cs.CL", "cs.AI"],
  "primary_category": "cs.CL",
  "citation_count": 10,
  "has_pdf": true,
  "language": "en"
}
```

For `chat_messages.metadata_json`, use this shape:

```json
{
  "used_rag": true,
  "model": "gemma4:e4b",
  "route_decision": {},
  "retrieval_filters": {},
  "sources": []
}
```

Do not store chain-of-thought. Store only structured routing and retrieval facts.

## Alembic migration requirements

Create a migration that:

1. Adds article metadata fields.
2. Adds chat memory fields.
3. Creates indexes for common filters:
   - `articles.source`
   - `articles.external_id`
   - `articles.doi`
   - `articles.publish_date`
   - `articles.cluster_id`
   - `articles.primary_category`
   - `articles.language`
   - `articles.document_type`
   - `articles.ingestion_run_id`
   - `chat_messages.chat_id`
   - `chat_messages.created_at`
4. Ensures pgvector extension exists.
5. Does not drop existing user data.

## Acceptance criteria

- `alembic -c database/alembic.ini upgrade head` works against a clean PostgreSQL database.
- Existing rows can be read after migration.
- New article rows can store vector + metadata.
- New chat rows can store message metadata and timestamps.
- No schema-changing code remains in FastAPI startup.
