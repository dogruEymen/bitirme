# 08_TESTING_AND_RUNBOOK.md — Tests, Manual Validation, and Local Workflow

## Role

You are a Senior Engineer responsible for proving the MVP works. Build lightweight tests and a clear runbook. Do not create a large test framework.

## Minimum automated tests

Create tests for:

```text
tests/test_rag_router.py
tests/test_retrieval_service.py
tests/test_conversation_memory.py
tests/test_analytics_contract.py
```

## Router tests

Validate:

- valid JSON route decision parses correctly,
- invalid JSON falls back to heuristic,
- generic questions do not use RAG,
- stored-paper questions use RAG,
- date/source/category filters parse correctly,
- follow-up references can produce `article_ids`.

## Retrieval tests

Validate:

- source filter is applied,
- date range filter is applied,
- category filter is applied,
- `has_pdf=true` filter is applied,
- empty result returns empty list,
- returned sources include title, article_id, DOI/URL, and score.

Use mocks or a small test database. Do not require real Ollama for retrieval tests.

## Conversation memory tests

Validate:

- recent messages are returned in chronological order,
- previous sources are extracted from assistant `metadata_json`,
- duplicate article IDs are removed,
- memory block contains summary + recent messages + previous sources,
- different sessions do not mix sources.

## Manual validation flow

Start services:

```bash
docker compose up --build
```

Pull local model if needed:

```bash
docker exec -it ollama ollama pull gemma4:e4b
```

Run migrations:

```bash
alembic -c database/alembic.ini upgrade head
```

Ingest sample papers:

```bash
python run_bulk_ingest.py --max-results 100 --sources arxiv --query "retrieval augmented generation"
```

Generate embeddings:

```bash
python ai_engine/embeddings/embeddings_to_db.py
```

Cluster:

```bash
python ai_engine/clustering/ClusterFunctions.py
```

Check endpoints:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/analytics
curl http://localhost:8000/bulletin
```

Create chat session:

```bash
curl -X POST http://localhost:8000/chat/sessions -H "Content-Type: application/json"
```

Generic no-RAG question:

```bash
curl -X POST http://localhost:8000/chat/sessions/1/message \
  -H "Content-Type: application/json" \
  -d '{"message":"RAG nedir?"}'
```

RAG question with metadata filters:

```bash
curl -X POST http://localhost:8000/chat/sessions/1/message \
  -H "Content-Type: application/json" \
  -d '{"message":"Son 30 günde arXiv kaynaklı RAG makalelerini özetle"}'
```

Follow-up memory question:

```bash
curl -X POST http://localhost:8000/chat/sessions/1/message \
  -H "Content-Type: application/json" \
  -d '{"message":"Önceki cevaptaki ikinci makaleyi detaylandır"}'
```

## Expected behavior

- First chat question should not retrieve.
- Second chat question should retrieve and cite sources.
- Third chat question should use previous source metadata.
- Empty database should produce a clear no-evidence message.
- Ollama failure should return a useful error, not a stack trace.

## Done checklist

- Clean Docker Compose start.
- Clean Alembic migration.
- Ingestion works.
- Embedding metadata stored.
- Retrieval filters work.
- Chat memory works.
- RAG citations work.
- Dashboard and bulletin show real data.
