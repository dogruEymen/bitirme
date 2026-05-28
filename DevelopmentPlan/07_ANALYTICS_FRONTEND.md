# 07_ANALYTICS_FRONTEND.md — Analytics API and Frontend Compatibility

## Role

You are a Full Stack Engineer. Your task is to keep the existing frontend working while making backend data real and consistent.

## Target files

Modify:

```text
backend/app/api/routes/analytics.py
backend/app/api/routes/bulletin.py
frontend/src/**/*.tsx
```

## Analytics backend requirements

Fix `backend/app/api/routes/analytics.py`:

1. Keep one `router = APIRouter()`.
2. Keep one `@router.get("/analytics")`.
3. Remove duplicate route definitions.
4. Remove fallback dummy data.
5. Use PostgreSQL-compatible date aggregation.
6. Return the shape the frontend expects:

```json
{
  "metrics": {},
  "barData": [],
  "pieData": [],
  "scatterData": [],
  "monthlyData": [],
  "clusters": [],
  "papers": []
}
```

## Metadata-aware analytics

Use the new metadata where useful:

- source distribution from `Article.source`,
- category distribution from `Article.primary_category`,
- monthly trend from `Article.publish_date`,
- cluster sizes from `Article.cluster_id`,
- citation distribution from `Article.citation_count`,
- PDF availability from `Article.pdf_url` or `metadata_json.has_pdf`.

Do not compute expensive analytics inside every request if it becomes slow. For MVP data sizes, direct SQL queries are fine.

## Frontend chat compatibility

Keep the current chat UI. The backend can stream plain text.

Sources should appear directly in the assistant answer:

```text
...

Sources:
[S1] Title — DOI/URL
[S2] Title — DOI/URL
```

No special citation UI is required for MVP.

## Frontend memory compatibility

The frontend already has chat sessions. Use those sessions. Do not create a new memory UI.

Adjust message rendering only if needed:

- use backend `created_at`,
- display assistant text as-is,
- handle error text gracefully.

## Empty states

Add graceful states for:

- no articles ingested,
- no clusters yet,
- no RAG matches,
- Ollama unavailable,
- backend unavailable.

## Acceptance criteria

- Dashboard loads from real backend data.
- Bulletin loads from real cluster/digest data.
- Chat displays streamed answer and citations.
- Follow-up chat messages remain in the same session.
- No frontend global state library is introduced.
