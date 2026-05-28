# 2026-05-28 Degisiklik Raporu

Bu rapor, olusturuldugu anda worktree'de gorulen 69 dosyalik degisiklik setini aciklar:

- 41 tracked dosyada degisiklik
- 28 yeni/untracked dosya

Not: Bu raporun kendisi bu sayiya dahil degildir. `.env` gibi git tarafindan izlenmeyen yerel dosyalar da bu 69 dosyalik listeye dahil edilmemistir.

## Genel Ozet

Bugunku calisma akademik yayin platformunu daha gercek bir MVP akisine yaklastirdi:

- API ingestion pipeline'i arXiv, OpenAlex ve Semantic Scholar icin daha zengin metadata uretir hale getirildi.
- Veritabanina yazma katmani PostgreSQL upsert, metadata normalizasyonu, batch icinde tekillestirme ve schema dogrulama ile guclendirildi.
- Embedding pipeline'i metadata-aware metin uretimi, embedding hash kontrolu ve tekrar calistirmada skip mantigi ile yenilendi.
- BERTopic clustering, precomputed embedding kullanimi, cluster metadata, representative article secimi ve CLI parametreleri ile genisletildi.
- RAG chat akisi icin router, retrieval, conversation memory ve orchestration servisleri eklendi.
- Chat cevaplarinda kaynak metadata'si saklanir hale getirildi; takip sorulari onceki kaynaklara referans verebiliyor.
- Analytics ve bulletin endpoint'leri frontend'in bekledigi gercek veri sekline yaklastirildi.
- Frontend chat, dashboard, bulletin, auth ve layout ekranlari koyu tema ve yeni veri kontratlariyla uyumlu hale getirildi.
- Docker compose artik Ollama container'i calistirmiyor; backend host makinedeki local Ollama'ya baglaniyor.
- Local PostgreSQL kullanimi netlestirildi.
- Hafif unit test seti eklendi.

## Dogrulama Notlari

Calistirilan baslica kontroller:

```bash
.venv/bin/python -m pytest -q
npm run build
docker compose config
.venv/bin/python -m alembic -c database/alembic.ini current
```

Gozlenen durum:

- Python testleri 28 test ile basarili calisti.
- Frontend production build basarili oldu.
- Docker compose config gecerli.
- Local DB Alembic head seviyesinde goruldu.

## Degisen Dosyalar

### Runbook ve Ortam

#### `README_DEV.md`

Developer runbook genisletildi. `.env` ornegi, test komutlari, migration, local Ollama, ingestion, embedding, clustering, digest ve manuel MVP dogrulama adimlari netlestirildi. Script komutlari sistem `python3` yerine `.venv/bin/python` kullanacak sekilde guncellendi.

#### `.env.example`

Proje icin ornek environment degerleri eklendi/guncellendi. Docker backend'in host makinedeki Ollama'ya ulasabilmesi icin `OLLAMA_BASE_URL=http://host.docker.internal:11434` tanimlandi.

#### `docker-compose.yml`

Ollama servisi compose stack'inden kaldirildi. Backend artik local host makinedeki Ollama'ya `host.docker.internal:11434` ile baglanir. PostgreSQL servisi pgvector image ile devam eder ve verisini `postgres_data` named volume'da saklar. Backend `DATABASE_URL` container icinden `postgres` servis host'una sabitlendi.

#### `requirements.txt`

Backend/AI pipeline icin gerekli ek Python paketleri ana dependency listesine eklendi.

#### `backend/requirements.txt`

Backend tarafinda yeni servislerin ihtiyac duydugu dependency seti guncellendi.

#### `ai_engine/requirements.txt`

AI pipeline ve embedding/clustering isleri icin gerekli ek paketler tanimlandi.

### Veritabani, Model ve Migration

#### `backend/app/core/config.py`

Pydantic settings yapisi `.env` okuyacak sekilde guncellendi. PostgreSQL, Ollama, model adi, embedding modeli, RAG top-k/candidate-k ve chat memory limitleri icin default ayarlar eklendi. Local default Ollama adresi `localhost:11434` olarak tanimlandi.

#### `database/alembic.ini`

Alembic config, projenin guncel database ayarlari ve migration akisiyle uyumlu hale getirildi.

#### `database/alembic/env.py`

Alembic online/offline migration akisi backend settings ve proje modelleriyle uyumlu calisacak sekilde guncellendi.

#### `database/alembic/versions/1fa1c80bab80_init_embedding.py`

Embedding migration'inda pgvector extension kullanimi icin ek duzenleme yapildi.

#### `database/alembic/versions/2094e58d9e01_update_schema_for_all_articles.py`

Article schema migration'i pgvector extension ve guncel article tablosu gereksinimleriyle uyumlu hale getirildi.

#### `database/alembic/versions/c1d2e3f4a5b6_add_rag_chat_metadata.py`

Yeni migration eklendi. Articles tablosuna embedding metadata alanlari, `metadata_json`, `language`, `document_type`, `ingestion_run_id` ve ilgili indexler eklendi. Chat session/message tablolarina memory ve metadata alanlari eklendi.

#### `database/alembic/versions/d2e3f4a5b6c7_add_cluster_metadata_and_digests.py`

Cluster metadata ve digest ozellikleri icin yeni migration eklendi. `clusters.metadata_json` kolonu ve `cluster_digests` tablosu olusturuldu.

#### `database/models/ArticleData.py`

Article modeli RAG ve pipeline icin zenginlestirildi. URL, updated date, categories, DOI, citation count, venue, embedding metadata, JSONB metadata, language, document type ve ingestion run id alanlari modele eklendi/guncellendi.

#### `database/models/ChatMessage.py`

Chat message modeli `created_at` ve `metadata_json` ile genisletildi. Assistant cevaplarinda RAG kaynaklari ve route kararini saklamak mumkun hale geldi.

#### `database/models/ChatSession.py`

Chat session modeli title, summary ve timestamp alanlariyla genisletildi. Session-local memory ve summary icin gerekli alanlar eklendi.

#### `database/models/ClusterData.py`

Cluster modeli `metadata_json` destekleyecek sekilde guncellendi. Representative article, source distribution, date range ve keyword metadata'si saklanabilir hale geldi.

#### `database/models/ClusterDigest.py`

Cluster digest cache modeli eklendi. Cluster bazli summary, highlights ve representative article id listeleri JSONB olarak saklanir.

#### `database/models/__init__.py`

Yeni `ClusterDigest` modeli model package export'una eklendi.

### Ingestion Pipeline

#### `run_bulk_ingest.py`

Bulk ingestion akisi kaynak bazli ve batch bazli hale getirildi. arXiv icin batch checkpoint/state yazimi eklendi. DB schema validation eklendi; eksik kolon veya `external_id` unique index yoksa net hata veriyor. Ingestion run id uretimi ve detayli exception logging eklendi.

#### `ai_engine/ingestion/schemas.py`

Raw article schema zenginlestirildi. `updated_date`, `url`, `categories`, `doi`, `citation_count`, `venue`, `metadata_json`, `language`, `document_type` ve `ingestion_run_id` alanlari desteklendi.

#### `ai_engine/ingestion/loader.py`

DB load katmani genisletildi. Computer Science filtreleme, string temizleme, uzunluk limitleri, metadata normalizasyonu, JSONB metadata uretimi, `ingestion_run_id`, batch ici `external_id` tekillestirme ve PostgreSQL upsert mantigi eklendi.

#### `ai_engine/ingestion/extractors/arxiv_extractor.py`

arXiv extractor tarih bazli cursor ile 2000'den itibaren aylik araliklarda cekim yapacak sekilde genisletildi. Batch streaming, checkpoint, category/primary category/DOI/venue metadata'si ve retry/backoff mantigi eklendi. Timeout, 429 ve 5xx durumlarinda daha dayanikli hale getirildi.

#### `ai_engine/ingestion/extractors/openalex_extractor.py`

OpenAlex extractor sadece Computer Science concept id'si ve `from_publication_date:2000-01-01` filtresiyle calisacak sekilde guncellendi. Donen kayitlar defensively CS ve tarih filtresinden tekrar geciriliyor. Cursor state'e filtre imzasi eklendi.

#### `ai_engine/ingestion/extractors/s2_extractor.py`

Semantic Scholar extractor metadata kapsami genisletildi. Fields of study, external ids, venue, DOI, citation count ve PDF metadata'si normalize ediliyor.

#### `ai_engine/ingestion/ingestion_state.json`

Ingestion cursor/checkpoint state'i guncellendi. Kaynaklarin kaldigi noktadan devam edebilmesi icin state dosyasi yeni formatlarla uyumlu hale geldi.

### Embedding Pipeline

#### `ai_engine/embeddings/embeddings_to_db.py`

Embedding script'i CLI parametreleri, proje kokunu import path'e ekleme, batch isleme ve hash bazli skip mantigiyle yenilendi. `title + abstract + metadata` metni embed ediliyor; embedding model adi, text hash ve created_at alanlari yaziliyor.

#### `ai_engine/embeddings/model.py`

Embedding model wrapper'i backend `EmbeddingService` ile uyumlu hale getirildi. Document text uretimi metadata alanlarini dikkate alacak sekilde hizalandi.

#### `backend/app/services/embedding_service.py`

Embedding servisinde model cache, query/document text uretimi ve deterministic text hash yardimcilari eklendi. RAG ve embedding script'i ayni metin formatini kullanir hale geldi.

### Clustering ve Digest

#### `ai_engine/clustering/ClusterFunctions.py`

Clustering script'i dogrudan calistirildiginda proje importlarini bulacak sekilde `sys.path` ayari kazandi. DB'den precomputed embedding'li article'lari okuyor, title + abstract metniyle BERTopic calistiriyor, cluster metadata'si ve representative article skorlarini sakliyor. `--max-articles` ve `--min-topic-size` CLI parametreleri eklendi; varsayilan olarak tum embedding'li makaleleri clusterlar.

#### `backend/app/services/digest_service.py`

Cluster digest uretimi icin yeni servis eklendi. Cluster representative article secimi, deterministic score payload'i, LLM summary fallback'i, highlights ve cache mantigi saglandi.

#### `backend/app/api/routes/bulletin.py`

Bulletin endpoint'i cluster metadata ve digest verisiyle genisletildi. Cluster digest endpoint'i eklendi ve `include_digests` gibi parametrelerle frontend'e zengin veri saglanir hale geldi.

### RAG, Retrieval ve Chat Memory

#### `backend/app/schemas/retrieval.py`

RAG retrieval icin Pydantic schema'lari eklendi. `RetrievalFilters`, `RouteDecision` ve `RetrievedArticle` tipleri tanimlandi. `sort_by` ile relevance veya yayin tarihi siralamasi destekleniyor.

#### `backend/app/schemas/source.py`

Cevaplarda kullanilacak kaynak referansi modeli eklendi. Article id, title, source, DOI, URL, PDF URL, venue, publish date, authors, cluster id ve score alanlari standardize edildi.

#### `backend/app/services/rag_router_service.py`

LLM destekli ve deterministic fallback'li RAG router eklendi. Mesajdan RAG gerekip gerekmedigi, source/category/date/DOI/PDF/citation filtreleri, top_k, takip sorusu referanslari ve yayin tarihi siralamasi cikariliyor.

#### `backend/app/services/retrieval_service.py`

pgvector tabanli retrieval servisi eklendi. Metadata filtreleri, direct article id lookup, DOI/source/category/date/PDF/citation filtreleri, deduplication, final scoring ve source formatting destekleniyor. "Yayin tarihi en yeni" sorulari icin `publish_date DESC` siralama yolu eklendi.

#### `backend/app/services/conversation_memory_service.py`

Session-local memory servisi eklendi. Son mesajlar, session summary ve onceki assistant cevaplarinda saklanan RAG kaynaklari prompt'a dahil ediliyor. Takip sorulari icin previous source extraction yapiliyor.

#### `backend/app/services/chat_orchestrator.py`

Chat akisi route -> retrieval -> prompt -> streaming answer -> metadata save seklinde merkezi bir orchestrator'a tasindi. RAG kullanildiginda kaynaklar saklaniyor, sort_by publish date oldugunda embedding hesaplamasi bypass ediliyor.

#### `backend/app/api/routes/chat.py`

Chat route daha ince bir API katmanina indirildi ve asil is chat orchestrator'a devredildi. Session/message endpoint'leri yeni metadata ve memory akisiyla uyumlu hale getirildi.

#### `backend/app/schemas/chat.py`

Chat response/session schema'lari yeni frontend ve metadata akisiyla uyumlu olacak sekilde genisletildi.

#### `backend/app/services/ollama_service.py`

Ollama servisinde async generate, streaming generate ve tutarli hata sarmalama eklendi. Ollama ulasilamazsa kullaniciya stack trace yerine kontrollu hata metni donulmesi saglandi.

### Analytics ve Backend API

#### `backend/app/api/routes/analytics.py`

Analytics endpoint'i duplicate/dummy yaklasimdan gercek DB aggregation kullanan hale getirildi. Metrics, category distribution, source distribution, monthly data, cluster data ve paper listeleri frontend kontratina uygun uretiliyor.

#### `backend/app/main.py`

FastAPI app startup'i sadeleştirildi. Schema yaratma gibi migration disi davranislar kaldirildi ve route kayitlari guncel backend mimarisiyle uyumlu hale getirildi.

### Frontend

#### `frontend/src/index.css`

Global tema degiskenleri, koyu tema renkleri, typography ve scrollbar stilleri guncellendi. UI daha tutarli dark dashboard gorunumune cekildi.

#### `frontend/src/components/Layout.tsx`

Ana layout ve sidebar yenilendi. Chat session listesi, navigation, auth/logout, responsive menu ve yeni koyu tema ile uyumlu tasarim eklendi.

#### `frontend/src/components/RequireAuth.tsx`

Auth guard davranisi yeni auth/session akisiyle uyumlu hale getirildi.

#### `frontend/src/lib/types.ts`

Frontend data kontratlari genisletildi. Analytics, bulletin, paper, cluster ve chat message tipleri backend'in yeni response sekilleriyle uyumlu hale getirildi.

#### `frontend/src/pages/AuthPage.tsx`

Login/signup ekrani tasarimi ve form davranislari guncellendi. Yeni koyu tema ve auth akisiyle uyum saglandi.

#### `frontend/src/pages/ChatPage.tsx`

Chat UI streaming cevap, retry, session create, thinking indicator, source/link rendering ve markdown parsing ile genisletildi. Input alanindaki plus butonu kaldirildi. Assistant mesajlarinda URL'ler tiklanabilir link olarak render ediliyor.

#### `frontend/src/pages/DashboardPage.tsx`

Dashboard frontend'i yeni analytics payload'ina gore guncellendi. Metrics, grafikler, cluster ve paper data alanlari backend kontratiyla uyumlu hale getirildi.

#### `frontend/src/pages/BulletinPage.tsx`

Bulletin ekrani cluster digest, representative papers, pagination ve yeni backend response alanlariyla uyumlu hale getirildi.

#### `frontend/package-lock.json`

Frontend dependency lock dosyasinda paket agaci guncellendi. Build'in mevcut dependency setiyle calismasi saglandi.

### Testler

#### `tests/conftest.py`

Testlerin proje kokundeki package'lari import edebilmesi icin root path `sys.path`'e eklendi.

#### `tests/test_ai_pipeline.py`

Ingestion metadata normalizasyonu, Computer Science filtreleme, batch ici dedupe, OpenAlex filtre URL'i, embedding text/hash, cluster representative skor ve digest score davranislari test edildi.

#### `tests/test_analytics_contract.py`

Analytics route'un tekil kayitli oldugu ve frontend'in bekledigi ana payload key'lerinin korundugu test edildi.

#### `tests/test_conversation_memory.py`

Conversation memory servisinin mesajlari kronolojik siraladigi, onceki kaynaklari dedupe ettigi ve prompt block icine summary/message/source bilgilerini koydugu test edildi.

#### `tests/test_rag_router.py`

Router'in valid JSON parse ettigi, invalid JSON'da fallback yaptigi, genel sorularda RAG kullanmadigi, paper sorularinda RAG kullandigi, filtreleri ve takip referanslarini cikardigi test edildi. "Yayin tarihi en yeni" sorularinda `publish_date_desc` siralamasi da test edildi.

#### `tests/test_retrieval_service.py`

Retrieval filtrelerinin SQL'e uygulandigi, PDF/date/category/source filtrelerinin calistigi, publish date siralamasinin DB order'ini korudugu ve source metadata formatinin dogru oldugu test edildi.

### Plan Dokumanlari

#### `DevelopmentPlan/00_PROJECT_REVIEW.md`

Mevcut repository'nin yetenekleri, eksikleri ve guvenli genisletme stratejisi dokumante edildi.

#### `DevelopmentPlan/01_CONFIGURATION_AND_SCHEMA.md`

Configuration, PostgreSQL/pgvector beklentileri, metadata alanlari ve migration hedefleri tanimlandi.

#### `DevelopmentPlan/02_RAG_ROUTING_AND_CHAT.md`

RAG route karari, metadata filter extraction, chat orchestration ve endpoint akisi planlandi.

#### `DevelopmentPlan/03_INGESTION_AND_EMBEDDING.md`

Ingestion metadata normalizasyonu, embedding metni ve embedding lifecycle'i tanimlandi.

#### `DevelopmentPlan/04_RETRIEVAL_METADATA_FILTERING.md`

Metadata-aware retrieval schema ve filtreleme davranislari planlandi.

#### `DevelopmentPlan/05_CONVERSATION_MEMORY.md`

Session-local chat memory, summary ve previous source kullanimi tasarlandi.

#### `DevelopmentPlan/06_CLUSTERING_AND_DIGEST.md`

BERTopic clustering, representative article secimi, cluster metadata ve digest uretimi planlandi.

#### `DevelopmentPlan/07_ANALYTICS_FRONTEND.md`

Analytics API kontrati ve frontend uyumlulugu icin gerekli degisiklikler planlandi.

#### `DevelopmentPlan/08_TESTING_AND_RUNBOOK.md`

Minimum test kapsami, manuel dogrulama akisi ve runbook hedefleri belirlendi.

#### `DevelopmentPlan/09_BACKEND_IMPLEMENTATION_PROMPT.md`

Backend tarafinda RAG, memory ve schema islerini uygulamak icin coding prompt hazirlandi.

#### `DevelopmentPlan/10_AI_PIPELINE_PROMPT.md`

Ingestion, embedding, clustering ve digest pipeline degisiklikleri icin coding prompt hazirlandi.

## Dikkat Edilecek Noktalar

- `docker compose down -v` calistirilirse local PostgreSQL volume'u silinir.
- Docker backend local Ollama'ya `host.docker.internal:11434` ile baglanir; host'ta Ollama'nin calisiyor olmasi gerekir.
- Clustering artik varsayilan olarak tum embedding'li makaleleri alir. Buyuk veri setlerinde `--min-topic-size` ve istege bagli `--max-articles` kullanmak performans icin onemli olabilir.
- BERTopic `topic_id = -1` olan outlier makaleleri cluster'a atamaz; bu makalelerin `cluster_id` almayacak olmasi beklenen davranistir.
- Ingestion state dosyasi kaldigi yerden devam etmek icin kullanilir; filtre degisikliginde state'in etkisini dikkate almak gerekir.
