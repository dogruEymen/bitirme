# 11_ANALYTICS_DEEPENING.md — P2 Analytics Derinlestirme Uygulama Plani

## Amac

PDF'teki trend/istatistik hedefini arastirmaci odakli hale getirmek.

Bu fazin sonunda dashboard su soruya cluster bazinda cevap verebilmelidir:

```text
Bu ay hangi topic yukseldi?
```

## Mevcut Durum

Mevcut analytics akisi:

- Backend endpoint: `GET /analytics`
- Route: `backend/app/api/routes/analytics.py`
- Snapshot servisi: `backend/app/services/report_snapshot_service.py`
- Snapshot tablosu: `report_snapshots`
- Frontend sayfasi: `frontend/src/pages/DashboardPage.tsx`
- Mevcut payload anahtarlari:
  - `metrics`
  - `barData`
  - `pieData`
  - `scatterData`
  - `monthlyData`
  - `clusters`
  - `papers`
  - `sourceDistribution`
  - `categoryDistribution`

Mevcut eksikler:

- `monthlyData` global yayin sayisini gosteriyor; cluster bazli trend yok.
- Dashboard'da source/category filtresi yok.
- Cluster kalite metrikleri hesaplanip UI'da gosterilmiyor.
- Snapshot payload versiyonu net bir sozlesme olarak donmuyor.
- Geriye donuk uyumluluk testleri sadece temel key seviyesinde.

## Kapsam

Bu dokuman yalnizca analytics derinlestirme fazini kapsar.

Kapsam disi:

- Notification sistemi.
- Pipeline job orchestration.
- PDF chunk retrieval.
- RAG cevap kalitesi.

## Hedef Payload Sozlesmesi

`GET /analytics` mevcut anahtarlari korumali ve yeni alanlari eklemelidir.

Yeni payload:

```json
{
  "schemaVersion": "analytics:v2",
  "generatedAt": "2026-06-09T10:00:00",
  "filters": {
    "source": null,
    "category": null,
    "period": "12m"
  },
  "metrics": {},
  "barData": [],
  "pieData": [],
  "scatterData": [],
  "monthlyData": [],
  "clusters": [],
  "papers": [],
  "sourceDistribution": [],
  "categoryDistribution": [],
  "clusterTrendData": [],
  "risingTopics": [],
  "clusterQuality": {}
}
```

Geriye donuk uyumluluk icin mevcut alanlar silinmemelidir.

## Backend Degisiklikleri

### 1. Analytics query parametreleri

`backend/app/api/routes/analytics.py` endpoint'i su filtreleri kabul etmelidir:

```text
GET /analytics?source=arxiv&category=cs.CL&period=12m&force_refresh=true
```

Parametreler:

- `source`: optional string
- `category`: optional string
- `period`: `3m`, `6m`, `12m`, `all`; default `12m`
- `force_refresh`: mevcut davranis korunur

Not:

- Filtreli analytics istekleri snapshot key'e dahil edilmelidir.
- `force_refresh=false` iken varsa snapshot okunmalidir.
- Snapshot yoksa mevcut davranisa benzer sekilde bos payload donulebilir veya ilk fazda lazy refresh yapilabilir. Tercih: manual `force_refresh` mevcut pattern ile korunur.

### 2. Snapshot key versiyonlama

Yeni helper eklenmelidir:

```python
ANALYTICS_SCHEMA_VERSION = "analytics:v2"

def analytics_snapshot_key(
    source: str | None = None,
    category: str | None = None,
    period: str = "12m",
) -> str:
    ...
```

Beklenen key formati:

```text
analytics:v2:<hash>
```

Eski `analytics:v1` snapshot'i okunmaya devam edilebilir, ancak yeni refresh her zaman `analytics:v2` uretmelidir.

### 3. Ortak article filtresi

`report_snapshot_service.py` icinde analytics query'leri icin ortak filtre helper'i eklenmelidir:

```python
def _filtered_articles_query(db, source=None, category=None, period="12m"):
    query = db.query(Article)
    ...
    return query
```

Filtre kurallari:

- `source` varsa `Article.source == source`
- `category` varsa:
  - `Article.primary_category == category`
  - veya `Article.categories.ilike(f"%{category}%")`
- `period`:
  - `3m`: son 90 gun
  - `6m`: son 180 gun
  - `12m`: son 365 gun
  - `all`: tarih filtresi yok

### 4. Cluster bazli zaman serisi

Yeni payload alanlari:

```json
"clusterTrendData": [
  {
    "month": "Jan 26",
    "monthKey": "2026-01",
    "clusters": {
      "1": 12,
      "2": 7
    },
    "total": 19
  }
]
```

Ek olarak frontend kolayligi icin alternatif long-form alan eklenebilir:

```json
"clusterTrendSeries": [
  {
    "cluster_id": "1",
    "cluster_name": "Retrieval-Augmented Generation",
    "month": "Jan 26",
    "monthKey": "2026-01",
    "count": 12
  }
]
```

Tavsiye:

- UI cizimi icin `clusterTrendSeries` daha basit filtrelenir.
- En fazla top 8 cluster trendi gosterilmelidir.
- Top cluster secimi filtrelenmis period icindeki toplam paper count'a gore yapilmalidir.

### 5. Rising topics / hizlanma metrigi

Yeni payload alani:

```json
"risingTopics": [
  {
    "cluster_id": "1",
    "name": "Retrieval-Augmented Generation",
    "paper_count": 120,
    "last_7d": 4,
    "prev_7d": 1,
    "last_30d": 15,
    "prev_30d": 7,
    "last_90d": 33,
    "prev_90d": 21,
    "acceleration_7d": 3.0,
    "acceleration_30d": 1.14,
    "acceleration_90d": 0.57,
    "score": 1.42
  }
]
```

Hesaplama:

```text
acceleration_N = (last_N - prev_N) / max(prev_N, 1)
score = 0.5 * acceleration_30d + 0.3 * acceleration_90d + 0.2 * acceleration_7d
```

Siralama:

1. `score` desc
2. `last_30d` desc
3. `paper_count` desc

Edge case:

- Yeni clusterlarda `prev_N = 0` olabilir. Bolme icin `max(prev_N, 1)` kullan.
- `last_N = 0` olan clusterlari rising topic listesinin altina it.

### 6. Cluster kalite metrikleri

Yeni payload:

```json
"clusterQuality": {
  "outlierCount": 120,
  "outlierRatio": 0.08,
  "largestClusterId": "3",
  "largestClusterName": "Large Language Models",
  "largestClusterCount": 420,
  "largestClusterRatio": 0.21,
  "avgRepresentationScore": 0.74,
  "clusteredPapers": 1880,
  "totalPapersWithEmbedding": 2000
}
```

Hesaplama:

- `outlierCount`: embedding'i olup `cluster_id is null` olan article sayisi.
- `outlierRatio`: `outlierCount / totalPapersWithEmbedding`
- `largestClusterRatio`: en buyuk cluster article count / clustered paper count
- `avgRepresentationScore`: cluster metadata'sindaki representative score ortalamalarinin ortalamasi.

Not:

- Bu metrikler cluster run kalitesini anlamak icin kullanilir.
- `totalPapersWithEmbedding = 0` ise oranlar `0` donmelidir.

## Frontend Degisiklikleri

### 1. Filtre UI

Dosya:

```text
frontend/src/pages/DashboardPage.tsx
```

Eklenmesi gereken kontroller:

- Source select:
  - `All sources`
  - API'den gelen `sourceDistribution` degerleri
- Category select:
  - `All categories`
  - API'den gelen `categoryDistribution` degerleri
- Period segmented control:
  - `3M`
  - `6M`
  - `12M`
  - `All`

Frontend query:

```ts
const params = new URLSearchParams();
if (source !== "all") params.set("source", source);
if (category !== "all") params.set("category", category);
params.set("period", period);
fetch(`${backendBaseUrl}/analytics?${params.toString()}`);
```

### 2. Rising Topics paneli

Yeni dashboard bolumu:

- Baslik: `Rising Topics`
- Gosterilecek alanlar:
  - cluster name
  - last 30d count
  - acceleration 30d
  - total paper count

Bu panel "bu ay hangi topic yukseldi?" sorusunun ana cevabi olmalidir.

### 3. Cluster trend grafiği

Yeni grafik:

- Line chart veya stacked area chart.
- Veri kaynagi: `clusterTrendSeries` veya `clusterTrendData`.
- En fazla top 8 cluster.
- Empty state: `No cluster trend data for selected filters.`

### 4. Cluster quality paneli

Yeni metrik kartlari:

- Outlier Ratio
- Largest Cluster Ratio
- Avg Representation Score
- Clustered Papers

Renk ve uyarilar:

- `outlierRatio > 0.35`: warning
- `largestClusterRatio > 0.45`: warning
- `avgRepresentationScore < 0.4`: warning

Bu uyarilar yalnizca UI sinyali olmali; backend hata saymamali.

## Test Plani

### Backend unit testleri

Dosya:

```text
tests/test_analytics_contract.py
```

Eklenecek testler:

1. Analytics v2 keyleri korunur:
   - `schemaVersion`
   - `generatedAt`
   - `filters`
   - `clusterTrendData`
   - `risingTopics`
   - `clusterQuality`
   - eski v1 keyleri

2. Snapshot key filtreye gore degisir:
   - source degisince key degisir
   - category degisince key degisir
   - period degisince key degisir

3. Bos payload geriye uyumludur:
   - Eski dashboard keyleri her zaman vardir.
   - Yeni v2 keyleri her zaman vardir.

4. Acceleration bolme hatasi uretmez:
   - `prev_30d = 0` durumunda skor hesaplanir.

5. Cluster kalite oranlari sifir bolme hatasi uretmez:
   - embedding yoksa oranlar `0`.

### Frontend test/manuel kontrol

Manuel kabul:

1. Dashboard filtersiz acilir.
2. Source filtresi degisince API query parametresi degisir.
3. Category filtresi degisince grafikler yeniden yuklenir.
4. Period `3M/6M/12M/All` secimleri calisir.
5. Rising Topics paneli bos veriyle empty state gosterir.
6. Cluster Quality paneli oranlari gosterir.

## Kabul Kriterleri

- Dashboard cluster bazli zaman serisi gosterir.
- Dashboard source/category/period filtreleriyle analytics payload'i yeniden ceker.
- Rising Topics paneli bu ay yukselen topicleri sirali gosterir.
- Cluster quality metrikleri backend payload'inda ve UI'da gorunur.
- `GET /analytics` eski frontend contract keylerini korur.
- Snapshot keyleri analytics v2 ve filtre parametreleriyle versiyonlanir.
- Testlerde geriye donuk uyumluluk garanti edilir.

## Uygulama Sirasi

1. Backend snapshot key ve payload versiyonunu ekle.
2. Ortak analytics filtre helper'ini yaz.
3. Cluster trend ve rising topic hesaplarini ekle.
4. Cluster quality hesaplarini ekle.
5. Empty payload'i v2 alanlariyla guncelle.
6. Backend contract testlerini genislet.
7. Dashboard filtre UI'ini ekle.
8. Rising Topics panelini ekle.
9. Cluster trend chart'ini ekle.
10. Cluster quality panelini ekle.
11. Manuel dashboard kontrolu yap.

## Riskler

- PostgreSQL date aggregation farkli ortamlarda timezone kaynakli farklilik gosterebilir. `publish_date` naive datetime kabul edilip mevcut pattern korunmali.
- Snapshot payload buyuyebilir. Top cluster limiti uygulanmali.
- Cluster trend hesaplari her request'te pahali olabilir. Bu nedenle snapshot pattern'i korunmali.
- Category filtresi `categories.ilike` kullandigi icin buyuk veride indexsiz yavaslayabilir. Gerekirse sonraki fazda normalized category tablosu eklenmelidir.

## Basari Tanimi

Bu faz tamamlandiginda arastirmaci dashboard uzerinden:

- Hangi clusterlarin buyudugunu,
- Hangi kaynak/kategoride yogunlasma oldugunu,
- Son 7/30/90 gunde hangi topiclerin hizlandigini,
- Clustering sonucunun kalite sinyallerini

tek ekranda gorebilmelidir.
