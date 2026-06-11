Sen Senior AI Engineer, RAG Architect ve LLM Retrieval Systems uzmanısın.

Benim görevim, mevcut projemdeki RAG retrieval başarısının neden düşük olduğunu anlamak ve bunu sistematik şekilde iyileştirmek. Senden yüzeysel tavsiyeler değil; skeptik, mühendislik odaklı, ölçülebilir ve uygulanabilir bir analiz bekliyorum.

## Bağlam

Aşağıda projemle ilgili teknik detayları ve analiz bulgularını bulabilirsin:

* Proje amacı:
  Akademik literatürü otomatik olarak toplamak, temizlemek, yapay zekâ yöntemleriyle gruplamak (clustering), trend analizleri çıkarmak ve RAG (Retrieval-Augmented Generation) destekli akıllı bir soru-cevap asistanı aracılığıyla araştırmacılara sunmak amacıyla geliştirilmiş uçtan uca bir akademik araştırma ve analiz platformudur.

* Kullanılan veri kaynakları:
  ArXiv (özellikle Computer Science `cs.*` kategorisi), OpenAlex ve Semantic Scholar API'lerinden çekilen akademik makaleler. Veritabanında (PostgreSQL) başlık, özet (abstract), yazar, yayın tarihi, doi, atıf sayısı, kategori, pdf_url ve kaynak bilgisi gibi metadatalar saklanmaktadır. Dokümanlar için tam metin yerine başlık ve özet metinleri kullanılmaktadır.

* Mevcut RAG mimarisi:
  * **Chunking yöntemi:** Chunking uygulanmamaktadır (Document-level embedding). Makale başlığı (`title_clean`) iki kez tekrarlanıp özet metni (`abstract_truncated`, maksimum 250 kelime) ile birleştirilerek tek bir metin (`embedding_text`) oluşturulur ve doğrudan bu metnin embedding'i üretilir: `f"{title_clean}. {title_clean}. {abstract_truncated}"`.
  * **Embedding modeli:** `intfloat/multilingual-e5-base` (768 boyutlu), `sentence-transformers` ile yerel cihazda çalıştırılmaktadır.
  * **Vector database:** PostgreSQL + `pgvector` eklentisi. Cosine distance hesaplaması kullanılmaktadır.
  * **Retriever (Hybrid Search):**
    * LLM (`gemma4:e4b`) veya regex tabanlı bir yönlendirici (Router) kullanıcı sorusunu analiz eder, arama yapılmasına karar verirse sorguyu yeniden yazar ve metadata filtrelerini (kategori, tarih, atıf sayısı, DOI vb.) çıkarır.
    * Vektör araması ile cosine distance bazlı `candidate_k` (varsayılan 25) aday makale çekilir.
    * Eş zamanlı olarak, başlık ve özet metinleri üzerinde kelime bazlı basit bir arama (`ilike %term%`) yapılarak kelime eşleşme sıklığına göre (`_keyword_score`) `candidate_k` (varsayılan 25) aday makale çekilir.
    * Vektör ve kelime araması adayları birleştirilip DOI veya external_id baz alınarak tekilleştirilir.
  * **Reranker:** Tekilleştirilmiş adaylar arasında özel bir formülle (`_final_score`) yeniden sıralama yapılır. Formül: `Score = vector_similarity + publish_date_bonus + citation_count_bonus - abstract_penalty`. (Burada `vector_similarity` değeri, kelime aramasından gelen ve vektör mesafesi olmayan makaleler için varsayılan olarak `1.0` kabul edilmektedir). Yeniden sıralanan makaleler arasından `top_k` (varsayılan 5, maks 10) makale seçilerek LLM'e sunulur.
  * **LLM:** Yerel Ollama sunucusu üzerinde çalışan `gemma4:e4b`.
  * **Prompt yapısı:** Kullanıcı sorusu, sohbet geçmişi (memory), router kararı, getirilen makalelerin başlık, yazar, doi, atıf sayısı, özet gibi bilgileri (`rag_context`) ve kaynak gösterme talimatları (`[S1]`, `[S2]`) birleştirilerek LLM prompt'u oluşturulur.

* Retrieval problemleri:
  * **Düşük Hit Rate ve Recall:** Yapılan değerlendirmelerde Hit Rate@5 değeri fallback router ile %10.25, LLM router ile %17.94 civarındadır. Recall@5 ise fallback router ile %2.56, LLM router ile %4.48 gibi son derece düşük seviyelerdedir.
  * **E5 Ön Ek (Prefix) Eksikliği:** E5 modeli asimetrik arama için tasarlanmıştır ve dokümanlar gömülürken `"passage: "` ön ekinin eklenmesi gerekir. Mevcut sistemde sorgulara `"query: "` ön eki eklenirken, veritabanına yazılan dokümanların (`build_embedding_text`) başına `"passage: "` ön eki eklenmemiştir. Bu durum vektör hizalamasını bozmaktadır.
  * **Router Engellemesi (Routing Failure):** Deterministik fallback yönlendirici, kullanıcı sorularında "paper", "makale", "yayın" gibi RAG anahtar kelimeleri geçmediğinde RAG tetiklememekte (`uses_rag=False`), bu da arama yapılması gereken birçok doğrudan bilimsel sorunun boş dönmesine sebep olmaktadır. LLM router kullanıldığında ise RAG tetiklenme oranı artsa da sorgu başına gecikme (latency) 13 saniyenin üzerine çıkmaktadır.
  * **Skor Dengesizliği (Keyword Search Dominance):** Vektör araması yerine kelime aramasıyla dönen makalelerin benzerlik skorunun `1.0` olarak atanması, kelime araması sonuçlarının vektör araması sonuçlarını domine etmesine ve alakasız kelime eşleşmelerinin en üst sıralara çıkmasına yol açmaktadır.
  * **Kısıtlı Bağlam (Tam Metin Eksikliği):** Makale tam metinleri (PDF içerikleri) sisteme dahil edilmediği için sadece başlık ve abstract üzerinden yapılan aramalar derinlemesine teknik soruları karşılayamamaktadır.

* Kullanılan metrikler:
  * Hit Rate @ K (Hit@k)
  * Recall @ K (Recall@k)
  * Precision @ K (Precision@k)
  * MRR (Mean Reciprocal Rank)
  * nDCG @ K (nDCG@k)
  * Latency (Gecikme süresi)

* Örnek başarısız sorgular:
  ```text
  [Sorgu 1 - RAG Tetiklenmeme Problemi]
  Sorgu: "Find research on optimal power flow, voltage stability constrained unit commitment, and solar micro-grid integration in power systems."
  Beklenen sonuç: [263132, 110043, 110143, 62297]
  Gerçek dönen sonuç: [] (RAG hiç tetiklenmedi, uses_rag = False, çünkü RAG anahtar kelimeleri bulunamadığından fallback router aramayı bypass etti).

  [Sorgu 2 - Düşük Vektör Yakınlığı/Eşleşmeme Problemi]
  Sorgu: "Show me publications on discontinuous Galerkin methods, Vanka-type multigrid solvers, and numerical analysis for Laplacian systems."
  Beklenen sonuç: [62124, 246424, 252467, 259101]
  Gerçek dönen sonuç: [100983, 86368, 23024, 256776, 90829] (RAG tetiklendi ancak beklenen hiçbir makale getirilmedi; Hit: False, Recall: 0.0).
  ```

* Mevcut kısıtlar:
  * **Yerel Çalışma Zorunluluğu / Veri Gizliliği:** LLM ve embedding modelleri yerel makinede (Ollama, sentence-transformers) çalıştırılmaktadır.
  * **Donanım ve Latency Sınırı:** Yerel modeller (`gemma4:e4b` vb.) nedeniyle router çıkarım süresi çok yüksektir (LLM router gecikmesi ~13 saniye). Donanım (CPU/GPU) kaynakları kısıtlıdır.
  * **Veri Kısıtı:** Makalelerin sadece üst verileri (başlık, özet vb.) veritabanındadır, PDF tam metinleri taranmamış veya parse edilmemiştir.

---

## Görevin

Projeyi ve mevcut RAG mimarisini bir Senior AI Engineer bakış açısıyla incele.

Önce sistemi skeptik şekilde değerlendir:

* Retrieval başarısızlığı gerçekten retriever kaynaklı mı?
* Problem chunking stratejisinden mi geliyor?
* Embedding modeli domain’e uygun mu?
* Query ile doküman dili/terminolojisi uyuşuyor mu?
* Vector search tek başına yeterli mi?
* Metadata filtering eksik mi?
* Top-k değeri doğru mu?
* Chunk boyutu ve overlap mantıklı mı?
* Doküman preprocessing kalitesi yeterli mi?
* Reranking gerekli mi?
* Evaluation set güvenilir mi?
* Kullanılan metrikler problemi doğru ölçüyor mu?
* LLM cevabı kötü olduğu için retrieval kötü sanılıyor olabilir mi?
* Veri kalitesi, doküman yapısı veya labeling problemi var mı?

Amacın sadece “şunu ekle, bunu değiştir” demek değil. Önce mevcut sistemde hangi varsayımların yanlış olabileceğini sorgula.

---

## Analiz Yaklaşımı

Lütfen aşağıdaki sırayla ilerle:

### 1. Sistem Anlama

Mevcut RAG pipeline’ını uçtan uca modelle:

```text
User Query
→ Query Preprocessing
→ Retriever
→ Vector Search / Hybrid Search
→ Candidate Chunks
→ Reranking
→ Context Assembly
→ LLM Answer Generation
→ Evaluation
```

Her aşamada hangi hataların retrieval kalitesini düşürebileceğini açıkla.

### 2. Failure Mode Analizi

Retrieval başarısızlığını şu kategorilere ayır:

* Data ingestion problemleri
* Chunking problemleri
* Embedding problemleri
* Query representation problemleri
* Vector DB / indexing problemleri
* Metadata filtering problemleri
* Hybrid search eksikliği
* Reranking eksikliği
* Context assembly problemleri
* Evaluation problemleri
* Domain-specific terminology problemleri

Her kategori için:

* Belirti nedir?
* Nasıl teşhis edilir?
* Hangi test yapılmalı?
* Muhtemel çözüm nedir?
* Trade-off nedir?

### 3. Retrieval İyileştirme Stratejisi

Bana uygulanabilir bir iyileştirme planı öner.

Özellikle şu konuları değerlendir:

* Chunk size / chunk overlap optimizasyonu
* Semantic chunking vs fixed-size chunking
* Parent-child chunk retrieval
* Sliding window retrieval
* Metadata-aware retrieval
* Hybrid search: BM25 + dense retrieval
* Query rewriting
* Multi-query retrieval
* HyDE yaklaşımı
* Cross-encoder reranking
* Domain-specific embedding modeli seçimi
* Fine-tuned embedding ihtiyacı
* Top-k tuning
* Context compression
* Deduplication
* Document-level vs chunk-level retrieval
* Evaluation için golden set oluşturma
* Offline evaluation pipeline
* Error analysis süreci

### 4. Ölçüm ve Deney Tasarımı

Bana sadece tavsiye verme; nasıl ölçeceğimi de söyle.

Şunları içeren bir deney planı oluştur:

* Baseline sistemi nasıl ölçmeliyim?
* Hangi metrikleri kullanmalıyım?
* Hangi retrieval varyasyonlarını karşılaştırmalıyım?
* Her deneyde sadece hangi değişkeni değiştirmeliyim?
* Başarı kriterim ne olmalı?
* Regression risklerini nasıl takip etmeliyim?
* Küçük ama güvenilir bir golden set nasıl oluşturmalıyım?

Ölçülemeyen önerileri zayıf öneri olarak işaretle.

### 5. Önceliklendirilmiş Aksiyon Planı

Tavsiyeleri etki / efor / risk açısından sırala.

Her öneri için tablo oluştur:

| Öncelik | Aksiyon | Beklenen Etki | Efor | Risk | Nasıl Ölçülür |
| ------- | ------- | ------------- | ---- | ---- | ------------- |

Aksiyonları şu kategorilere ayır:

* Hemen yapılacaklar
* 1-2 günlük iyileştirmeler
* 1 haftalık deneyler
* Daha ileri seviye mimari değişiklikler

### 6. Skeptik Değerlendirme

Her önerinin yanında şu soruları cevapla:

* Bu öneri hangi durumda işe yaramaz?
* Yanlış uygulanırsa neyi bozabilir?
* Latency, maliyet ve karmaşıklık etkisi nedir?
* Bu değişiklik gerçekten retrieval problemini mi çözer, yoksa sadece semptomu mu maskeler?

### 7. Sonuç

En sonunda bana net bir teknik yol haritası ver:

* İlk olarak neyi kontrol etmeliyim?
* İlk deneyim ne olmalı?
* En yüksek etki beklenen 3 değişiklik nedir?
* Hangi değişiklikleri şimdilik yapmamalıyım?
* Profesyonel bir RAG retrieval improvement süreci nasıl kurulmalı?

---

## Çıktı Formatı

Cevabını `plan.md` dosyası içeriği gibi Markdown formatında hazırla.

Başlık şu olsun:

```md
# RAG Retrieval Improvement Plan
```

Markdown yapısı profesyonel, rapora uygun ve uygulanabilir olsun.

Genel, klişe ve yüzeysel öneriler verme. Her öneriyi mümkün olduğunca şu üçlüyle destekle:

```text
Problem → Neden Olabilir → Nasıl Test Edilir → Nasıl İyileştirilir
```

Eksik bilgi varsa önce eksik bilgileri listele; ancak analizi durdurma. Mantıklı varsayımlar yaparak devam et ve yaptığın varsayımları açıkça belirt.

Amacın bana sadece cevap vermek değil; kötü retrieval sonuçlarının kök nedenini bulmam için profesyonel bir mühendislik inceleme planı çıkarmak.
