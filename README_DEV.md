# Developer Runbook

Bu dokuman proje entrypoint'lerini ve yerel gelistirme komutlarini netlestirir.

## Gereksinimler

- Python 3.11+
- Node.js 20+
- PostgreSQL + pgvector
- Redis
- Ollama

## Ortam Degiskenleri

Kok dizinde `.env` dosyasi olusturun:

```bash
DATABASE_URL="postgresql://USER:PASSWORD@HOST:PORT/DB"
OLLAMA_BASE_URL="http://localhost:11434"
OLLAMA_MODEL="gemma4"
```

Neon kullaniliyorsa `DATABASE_URL` Neon connection string olmalidir.

## Python Bagimliliklari

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

## PostgreSQL ve Migration

PostgreSQL tarafinda `vector` extension gerekir.

Sadece migration uygulamak icin:

```bash
alembic -c database/alembic.ini upgrade head
```

## Ollama

```bash
ollama serve
ollama pull gemma4
```

Farkli model kullanilacaksa `.env` icinde `OLLAMA_MODEL` degerini degistirin.

## Backend

Backend icin tek entrypoint:

```bash
uvicorn backend.app.main:app --reload
```

Kontrol endpoint'i:

```bash
curl http://127.0.0.1:8000/health
```

Beklenen cevap:

```json
{ "status": "ok" }
```

Chat endpoint'i:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello"}'
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Varsayilan frontend adresi:

```text
http://localhost:5173
```

## Ingestion

Varsayilan kaynaklar `arxiv,openalex` ve Computer Science filtreleriyle calisir.

```bash
python3 run_bulk_ingest.py --reset-state --max-results 10000 --sources arxiv,openalex
```

Semantic Scholar sorgu ile calistirilmalidir:

```bash
python3 run_bulk_ingest.py --max-results 1000 --sources semanticscholar --query "machine learning"
```

`ai_engine/ingestion/ingestion_state.json` repo'da tutulur; ekip ayni cursor/offset bilgisinden devam edebilir.

## Embedding

Embedding uretilmemis makaleler icin:

```bash
python3 ai_engine/embeddings/embeddings_to_db.py
```

Bu script `articles.embedding` alanini doldurur.

## Clustering

Embedding'i olan makaleleri clusterlamak icin:

```bash
python3 ai_engine/clustering/ClusterFunctions.py
```

Bu script `clusters` tablosunu yeniler ve `articles.cluster_id` alanlarini gunceller.

## Worker

Redis ayaktayken Celery worker:

```bash
celery -A backend.worker.scheduler.app worker --loglevel=info
```

Mevcut worker yapisi MVP seviyesindedir; chat/RAG akisi henuz Celery uzerinden calismaz.
