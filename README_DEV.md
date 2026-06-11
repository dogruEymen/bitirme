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
EMBEDDING_DEVICE=auto
EMBEDDING_ENCODE_BATCH_SIZE=64
CLUSTERING_HARDWARE_PROFILE=auto
CLUSTERING_THREADS=8
CLUSTERING_LOW_MEMORY=true
CLUSTERING_HDBSCAN_JOBS=6
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
.venv/bin/alembic -c database/alembic.ini upgrade head
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
.venv/bin/python run_bulk_ingest.py --max-results 10000 --sources arxiv,openalex
```

ArXiv ingestion kurallari:

- API sorgusu `cat:cs.*` ile sinirlanir.
- Bir ay icin en fazla `start_offset=3000` seviyesine kadar veri cekilir; limit dolunca onceki aya gecilir.
- DB'ye yalnizca `primary_category` veya `categories` alaninda `cs.` ile baslayan en az bir kategori bulunan arXiv kayitlari yazilir.
- `abstract_text` olmayan veya bos olan makaleler DB'ye yazilmaz.
- arXiv Terms of Use: legacy API'lerde tek baglanti ve en fazla 3 saniyede 1 istek
  kullanilmalidir (yaklasik 1200 istek/saat teorik ust sinir); extractor her HTTP
  isteginden once bu araligi uygular.
- 429 donerse `Retry-After` ve varsa `X-RateLimit-*` / `RateLimit-*` headerlari loglanir.

Kaggle arXiv snapshot dosyasindan API kullanmadan import etmek icin:

```bash
.venv/bin/python run_kaggle_arxiv_ingest.py --input /Users/eymendogru/Downloads/arxiv-metadata-oai-snapshot.json --samples-per-month 2500 --start-year 2016 --end-year 2026 --target-max-records 300000 --dry-run
.venv/bin/python run_kaggle_arxiv_ingest.py --input /Users/eymendogru/Downloads/arxiv-metadata-oai-snapshot.json --samples-per-month 2500 --start-year 2016 --end-year 2026 --target-max-records 300000 --batch-size 1000
```

Bu script dosyayi satir satir okur; kayitlari mevcut `RawArticleSchema` formatina cevirir ve ayni
DB loader filtresinden gecirir. Bu nedenle `cs.` kategori zorunlulugu, bos abstract eleme,
bos title eleme, DOI veya PDF bilgisi zorunlulugu, metadata normalizasyonu ve `external_id`
bazli upsert aynen uygulanir. `2016-2026` araligi dahil edilirse ay basina 2500 hedefi
teorik olarak 330000 kayit eder; `--target-max-records 300000` toplam hacmi 300000 ile sinirlar.

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

`EMBEDDING_DEVICE=auto` CUDA varsa `cuda`, Apple Silicon'da MPS varsa `mps`,
aksi halde `cpu` secer. MacBook M4 Pro 24 GB icin `auto` ve
`EMBEDDING_ENCODE_BATCH_SIZE=64` varsayilani uygundur; bellek baskisi yoksa batch size
128'e cikarilabilir.

## Clustering

Embedding'i olan arXiv Computer Science makalelerini clusterlamak icin:

```bash
.venv/bin/python ai_engine/clustering/ClusterFunctions.py
```

Bu komut varsayilan olarak `source='arxiv'` olan ve `primary_category` veya `categories`
alaninda `cs.*` kategorisi bulunan embedding'li makaleleri clusterlar. BERTopic outlier
makaleleri, orijinal embedding uzayinda en yakin cluster centroid'ine cosine benzerligi
yeterince yuksekse otomatik atanir; kalan outlier makaleler `articles.cluster_id = NULL`
kalir. UMAP varsayilani `n_neighbors=50`, `n_components=10`, `min_dist=0.05` kullanir;
bu ayar eski `n_neighbors=10`, `min_dist=0.0` konfigurasyonunun urettigi asiri sikisik
yerel adaciklari azaltmayi hedefler. HDBSCAN `min_samples` degeri `min_topic_size`
uzerinden otomatik secilir. `CLUSTERING_HARDWARE_PROFILE=auto`
macOS Apple Silicon ve yaklasik 24 GB RAM algilarsa `m4-pro-24gb` profilini kullanir;
bu profil CPU thread sayisini sinirlar, UMAP `low_memory` modunu acar ve HDBSCAN is
sayisini M4 Pro icin makul seviyede tutar. Aynisini CLI'dan acik vermek icin:

```bash
.venv/bin/python ai_engine/clustering/ClusterFunctions.py --hardware-profile m4-pro-24gb --threads 8
```

Deneme veya daha hizli calistirma icin
limit verilebilir:

```bash
.venv/bin/python ai_engine/clustering/ClusterFunctions.py --max-articles 3500
```

Buyuk veri setlerinde daha iri clusterlar icin minimum topic boyutu da artirilabilir:

```bash
.venv/bin/python ai_engine/clustering/ClusterFunctions.py --min-topic-size 50
```

Yuksek guvenli outlier atamayi kapatmak veya esigi degistirmek icin:

```bash
.venv/bin/python ai_engine/clustering/ClusterFunctions.py --no-reassign-outliers
.venv/bin/python ai_engine/clustering/ClusterFunctions.py --outlier-reassignment-threshold 0.90
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

## Analytics ve Bulletin Snapshotlari

Analytics ve bulletin endpoint'leri pahali DB aggregation/centroid hesaplarini her
sayfa acilisinda tekrar yapmaz. Hazir payload `report_snapshots` tablosunda saklanir.
`/analytics` ve frontend'in kullandigi `/bulletin?limit=10&include_digests=true`
istekleri bu snapshot'i okur.

Yeni snapshot tablosunu olusturmak icin migration uygulanmalidir:

```bash
.venv/bin/alembic -c database/alembic.ini upgrade head
```

Normal guncelleme akisi:

1. Ingestion yeni makaleleri DB'ye yazar.
2. Data hygiene temiz CSV'leri uretir.
3. Embedding adimi yeni veya degisen makalelerin embedding'lerini yazar.
4. Clustering adimi `clusters` ve `articles.cluster_id` alanlarini gunceller.
5. Clustering DB commit'inden sonra analytics ve bulletin snapshot'lari otomatik
   yeniden uretilir.

Manuel snapshot yenilemek icin endpoint uzerinden:

```bash
curl "http://127.0.0.1:8000/analytics?force_refresh=true"
curl "http://127.0.0.1:8000/bulletin?limit=10&include_digests=true&force_refresh=true"
```

Backend calismiyorken ayni yenilemeyi Python ile yapmak icin:

```bash
.venv/bin/python -c "from database.db import SessionLocal; from backend.app.services.report_snapshot_service import ReportSnapshotService; db=SessionLocal(); print(ReportSnapshotService(db).refresh_default_snapshots()); db.close()"
```

Snapshot durumunu kontrol etmek icin:

```bash
psql "$DATABASE_URL" -c "select snapshot_key, generated_at from report_snapshots order by snapshot_key;"
```

Notlar:

- Snapshot yoksa normal endpoint bos/hizli response doner; payload uretimi icin
  clustering veya manuel `force_refresh=true` kullanilmalidir.
- `force_refresh=true` yalnizca manuel operasyon icindir; normal frontend kullanimi bu
  parametreyi gondermemelidir.
- Filtreli bulletin istekleri (`category`, `source`, `period_start`, `period_end`) kendi
  snapshot key'i ile saklanir. Varsayilan pipeline refresh'i frontend'in ana bulletin
  snapshot'ini yeniler.
- Bulletin UI, snapshot'taki mevcut cluster topic havuzunu checkbox listesi olarak gosterir.
  Secilen topic'ler disindaki clusterlar frontend'de gizlenir.
- Bulletin kartlari hizli yuklenmek icin kisaltilmis abstract tasir. Makale karti
  acildiginda tam abstract ve PDF/source linkleri `/bulletin/articles/{article_id}`
  endpoint'inden alinir.

Makale detayini manuel kontrol etmek icin:

```bash
curl "http://127.0.0.1:8000/bulletin/articles/254424"
```

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
.venv/bin/alembic -c database/alembic.ini upgrade head
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

Snapshot'i manuel yeniden uretmek gerektiginde:

```bash
curl "http://localhost:8000/analytics?force_refresh=true"
curl "http://localhost:8000/bulletin?limit=10&include_digests=true&force_refresh=true"
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
