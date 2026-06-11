# Örnek Veritabanı Veri Analiz Raporu (academic_platform_sample)

Bu doküman, test deneylerini hızlandırmak amacıyla oluşturulan ve en son optimize edilmiş konu kümeleme (Topic Clustering) pipeline'ı çalıştırılan **`academic_platform_sample`** (20.000 makalelik random sampling) veritabanının yapısını, veri dağılımlarını ve elde edilen kümeleme analizlerini açıklamaktadır.

---

## 1. Genel İstatistikler ve Veri Profili

Örnek veritabanının genel istatistikleri ve orijinal veritabanına kıyasla ölçeği aşağıda özetlenmiştir:

* **Toplam Makale Sayısı (`articles`):** 20,000 adet (Orijinal veritabanının tam %6.67'si)
* **Embedding'i Olan Makale Sayısı:** 20,000 adet (%100.00 kapsam)
* **Kümelenen Makale Sayısı:** 19,477 adet
* **Outlier (Kümeye Atanamayan Gürültü) Makale Sayısı:** 523 adet (Toplam verinin %2.61'i)
* **Toplam Küme Sayısı (`clusters`):** 25 adet (Hassas HDBSCAN min_cluster_size=100 parametresi ile oluşan kararlı ana dallar)
* **Tarih Aralığı:** `01-01-2016` ile `21-05-2026` arası (Orijinal veri aralığını tam olarak temsil eder)

---

## 2. Kategori Dağılım Analizi (ArXiv cs.*)

20.000 adet rastgele seçilen makalenin ana konu kategorilerine (`primary_category`) göre dağılımı, orijinal veritabanı ile mükemmel bir paralellik göstermektedir (yine Computer Vision, Machine Learning ve NLP başı çekmektedir):

| Kategori Kodu | Kategori Açıklaması | Makale Sayısı | Oran (%) |
| :--- | :--- | :---: | :---: |
| **`cs.CV`** | Computer Vision and Pattern Recognition | 3,344 | %16.72 |
| **`cs.LG`** | Machine Learning (Computer Science) | 2,872 | %14.36 |
| **`cs.CL`** | Computation and Language (NLP) | 1,745 | %8.73 |
| **`cs.IT`** | Information Theory | 870 | %4.35 |
| **`cs.RO`** | Robotics | 823 | %4.12 |
| **`cs.AI`** | Artificial Intelligence | 735 | %3.68 |
| **`cs.CR`** | Cryptography and Security | 678 | %3.39 |
| **`math.NA`** | Numerical Analysis | 525 | %2.63 |
| **`stat.ML`** | Machine Learning (Statistics) | 481 | %2.41 |
| **`eess.SY`** | Systems and Control | 441 | %2.21 |

---

## 3. Tablo Hacim İstatistikleri

Kümeleme pipeline'ı koşturulduktan sonra örnek veritabanındaki tabloların güncel satır sayıları (Row Counts):

* **`articles`:** 20,000 (Makale metadataları ve vektörleri)
* **`clusters`:** 25 (Konu kümelerinin açıklamaları ve yazar/kategori metadataları)
* **`cluster_digests`:** 25 (Her küme için yerel Ollama/Gemma ile çıkarılmış periyodik özetler)
* **`chat_sessions`:** 17 (RAG test oturumları)
* **`chat_messages`:** 36 (RAG sohbet mesajları ve kaynak döküman listeleri)
* **`users`:** 3 (Geliştirici/Test kullanıcı hesapları)
* **`user_bulletin_preferences`:** 2 (Bülten filtreleme ve bildirim tercihleri)
* **`report_snapshots`:** 2 (Dashboard grafik önbellek kayıtları)

---

## 4. En Büyük 5 Konu Kümesi ve Detayları

Optimize edilmiş kümeleme koşusu sonrasında oluşan, en çok makale içeren ilk 5 konu kümesi ve anahtar kelimeleri:

### 1. Küme ID: 1 — "3D Object Detection and Pose Estimation"
* **Makale Sayısı:** 2,094 makale
* **Baskın Anahtar Kelimeler:** `3d`, `object`, `depth`, `pose`, `object detection`, `point`, `scene`, `monocular`
* **Tanım:** 3D derinlik algılama, nesne tespiti, sahne geometrisi ve kamera bazlı poz tahmini çalışmaları.

### 2. Küme ID: 0 — "Reinforcement Learning for Robotics"
* **Makale Sayısı:** 1,809 makale
* **Baskın Anahtar Kelimeler:** `control`, `reinforcement`, `policy`, `robot`, `rl`, `robots`, `planning`, `controller`, `robotic`
* **Tanım:** Pekiştirmeli öğrenme (RL), robotik kontrol politikaları ve hareket planlama algoritmaları.

### 3. Küme ID: 4 — "Medical Image Segmentation for Brain Analysis"
* **Makale Sayısı:** 1,510 makale
* **Baskın Anahtar Kelimeler:** `segmentation`, `images`, `image`, `clinical`, `medical`, `brain`, `mri`, `patients`, `ct`, `imaging`
* **Tanım:** Klinik ve tıbbi görüntü işleme, MRI/CT taramalarında beyin ve tümör segmentasyonu çalışmaları.

### 4. Küme ID: 3 — "Finite Element Numerical Analysis"
* **Makale Sayısı:** 1,461 makale
* **Baskın Anahtar Kelimeler:** `numerical`, `equations`, `equation`, `finite`, `convergence`, `finite element`, `element`, `problems`, `gradient`
* **Tanım:** Diferansiyel denklemlerin çözümü, sonlu elemanlar analizi (FEM) ve nümerik yakınsama kanıtları.

### 5. Küme ID: 6 — "Neuromorphic Computing and Edge AI"
* **Makale Sayısı:** 1,367 makale
* **Baskın Anahtar Kelimeler:** `neural`, `neural networks`, `networks`, `spiking`, `neuromorphic`, `pruning`, `hardware`, `memory`, `spiking neural`
* **Tanım:** Donanım uyumlu yapay zekâ, budama (pruning), spiking yapay sinir ağları ve nöromorfik işlemciler.

---

## 5. Kümeleme ve RAG Entegrasyon Yorumu

* **Temiz Arama Bağlamı (Clean RAG Context):** 523 adet gürültülü (outlier) makalenin kümeleme dışı (`cluster_id = NULL`) bırakılması, RAG katmanında veya Bulletin ekranında bu makalelerin konu bazlı sorgularda alakasız sonuçlar getirmesini engeller.
* **Hızlı Centroid Hesaplama:** Medyan küme boyutunun 543 olması ve toplam küme sayısının 25'e düşmesi sayesinde, RAG aramaları sırasında veya dashboard yüklendiğinde küme merkezi (centroid) hesaplamaları milisaniyeler içinde tamamlanmaktadır.
* **Geliştirici Avantajı:** 300.000 makale ile saatler süren UMAP/HDBSCAN ve RAG test simülasyonları, bu örnek veritabanı sayesinde **1-2 dakika** gibi çok kısa sürelerde tamamlanabilmektedir.
