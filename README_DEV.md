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
DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/academic_platform"
OLLAMA_BASE_URL="http://localhost:11434"
MODEL_NAME="gemma4:e4b"
EMBEDDING_MODEL_NAME="intfloat/multilingual-e5-base"
RAG_TOP_K=5
RAG_CANDIDATE_K=25
CHAT_HISTORY_LIMIT=12
CHAT_SUMMARY_TRIGGER_MESSAGES=24
```

Neon kullaniliyorsa `DATABASE_URL` Neon connection string olmalidir.

## Python Bagimliliklari

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

## Testler

Hafif unit testleri calistirmak icin:

```bash
pytest tests
```

Bu testler Ollama veya canli PostgreSQL gerektirmez; router fallback, retrieval filter SQL'i,
conversation memory ve analytics response contract'ini kontrol eder.

## PostgreSQL ve Migration

PostgreSQL tarafinda `vector` extension gerekir.

Sadece migration uygulamak icin:

```bash
alembic -c database/alembic.ini upgrade head
```

## Ollama

```bash
ollama serve
ollama pull gemma4:e4b
```

Farkli model kullanilacaksa `.env` icinde `MODEL_NAME` degerini degistirin.

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
.venv/bin/python run_bulk_ingest.py --reset-state --max-results 10000 --sources arxiv,openalex
```

Semantic Scholar sorgu ile calistirilmalidir:

```bash
.venv/bin/python run_bulk_ingest.py --max-results 1000 --sources semanticscholar --query "machine learning"
```

`ai_engine/ingestion/ingestion_state.json` repo'da tutulur; ekip ayni cursor/offset bilgisinden devam edebilir.

## Data Hygiene ve Text Preparation

ArXiv CS verisini embedding ve BERTopic icin temiz CSV'lere hazirlamak:

```bash
.venv/bin/python ai_engine/data_hygiene/export_clean_papers.py --output-dir exports/data_hygiene
```

Bu komut `clean_papers.csv`, `clean_papers_for_bertopic.csv`, `data_hygiene_metrics.csv`,
`removed_records.csv`, `duplicate_records.csv` ve `data_hygiene_report.md` dosyalarini uretir.
Pipeline embedding icin `embedding_text`, BERTopic representation icin `representation_text`
alanlarini kullanir.

## Embedding

Embedding uretilmemis makaleler icin:

```bash
.venv/bin/python ai_engine/embeddings/embeddings_to_db.py --total-articles 3500 --batch-size 250
```

Bu script varsayilan olarak varsa `exports/data_hygiene/clean_papers.csv` ve
`exports/data_hygiene_openalex/clean_papers.csv` dosyalarindaki `embedding_text` alanini
okur; CSV yoksa DB taramasina fallback yapar. `articles.embedding`, `embedding_model`,
`embedding_text_hash` ve `embedding_created_at` alanlarini doldurur. Tekrar calistirildiginda
modeli ve metin hash'i degismeyen makaleleri atlar.

## Clustering

Embedding'i olan arXiv Computer Science makalelerini clusterlamak icin:

```bash
.venv/bin/python ai_engine/clustering/ClusterFunctions.py
```

Bu komut varsayilan olarak `source='arxiv'` olan ve `primary_category` veya `categories`
alaninda `cs.*` kategorisi bulunan embedding'li makaleleri clusterlar. BERTopic outlier
makaleleri `articles.cluster_id = NULL` kalir. Deneme veya daha hizli calistirma icin
limit verilebilir:

```bash
.venv/bin/python ai_engine/clustering/ClusterFunctions.py --max-articles 3500
```

Buyuk veri setlerinde daha iri clusterlar icin minimum topic boyutu da artirilabilir:

```bash
.venv/bin/python ai_engine/clustering/ClusterFunctions.py --min-topic-size 50
```

BERTopic iyilestirme deneyi icin baseline karsilastirmasi ve CSV/model ciktilari:

```bash
.venv/bin/python ai_engine/clustering/ClusterFunctions.py --run-experiments --output-dir exports/bertopic
```

Script `topic_info.csv`, `paper_topic_assignments.csv`, `topic_keywords.csv`,
`bertopic_experiment_results.csv`, `bertopic_cluster_iyilestirme_raporu.md` ve
`bertopic_model` ciktilarini uretir. Sadece rapor/CSV/model uretip veritabanindaki
cluster tablosunu degistirmemek icin:

```bash
.venv/bin/python ai_engine/clustering/ClusterFunctions.py --skip-database-save --run-experiments --output-dir exports/bertopic
```

Mevcut 20.000 temiz embedding uzerindeki son denemede `--min-topic-size 5`, en buyuk
topic oranini baseline'a gore dusururken outlier oranini hedef araliga en yakin tuttu.

OpenAlex verisini de denemeye dahil etmek icin acik opt-in kullanin:

```bash
.venv/bin/python ai_engine/clustering/ClusterFunctions.py --include-openalex
```

Script varsayilan olarak temiz CSV'lerdeki `representation_text` alanini BERTopic docs
girdisi olarak kullanir ve sadece `embedding_text_hash` degeri temiz CSV ile eslesen
precomputed embedding'li makaleleri clusterlar. `clusters` tablosunu yeniler,
`articles.cluster_id` alanlarini gunceller ve cluster metadata/representative article
bilgilerini kaydeder. Keyword listesi stop-word agirlikli topic'ler DB'ye yazilmaz.

Cluster digest uretmek icin:

```bash
curl "http://127.0.0.1:8000/bulletin/clusters/3/digest?max_articles=5"
```

`/bulletin?include_digests=true` cluster listesine deterministic, gercek makalelere dayali
digest bilgisi ekler.

## Worker

Redis ayaktayken Celery worker:

```bash
celery -A backend.worker.scheduler.app worker --loglevel=info
```

Mevcut worker yapisi MVP seviyesindedir; chat/RAG akisi henuz Celery uzerinden calismaz.

## MVP Manuel Dogrulama Akisi

Tum servisleri baslat:

```bash
docker compose up --build
```

Modeli gerekirse indir:

```bash
ollama pull gemma4:e4b
```

Migration uygula:

```bash
alembic -c database/alembic.ini upgrade head
```

Ornek RAG verisi cek:

```bash
.venv/bin/python run_bulk_ingest.py --max-results 100 --sources arxiv --query "retrieval augmented generation"
```

Embedding ve clustering:

```bash
.venv/bin/python ai_engine/embeddings/embeddings_to_db.py --total-articles 100 --batch-size 50
.venv/bin/python ai_engine/clustering/ClusterFunctions.py --max-articles 100
```

Endpoint kontrolleri:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/analytics
curl http://localhost:8000/bulletin
```

Session ve chat kontrolleri:

```bash
curl -X POST http://localhost:8000/chat/sessions -H "Content-Type: application/json"

curl -X POST http://localhost:8000/chat/sessions/1/message \
  -H "Content-Type: application/json" \
  -d '{"message":"RAG nedir?"}'

curl -X POST http://localhost:8000/chat/sessions/1/message \
  -H "Content-Type: application/json" \
  -d '{"message":"Son 30 gunde arXiv kaynakli RAG makalelerini ozetle"}'

curl -X POST http://localhost:8000/chat/sessions/1/message \
  -H "Content-Type: application/json" \
  -d '{"message":"Onceki cevaptaki ikinci makaleyi detaylandir"}'
```

Beklenen davranis:

- `RAG nedir?` retrieval kullanmadan genel yanit verir.
- ArXiv/son 30 gun sorusu retrieval kullanir ve `[S1]` kaynaklariyla cevap verir.
- Takip sorusu onceki assistant mesajindaki `metadata_json.sources` verisini kullanir.
- Bos veritabaninda uydurma kaynak donmez; yeterli kanit olmadigini soyler.
- Ollama kapaliyken stack trace yerine kullanilabilir hata metni doner.
