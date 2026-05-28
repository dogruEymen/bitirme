from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from database.db import Base
from pgvector.sqlalchemy import Vector

class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Hangi kaynaktan geldiğini belirten alan (ör: 'arxiv', 'openalex', 'semanticscholar')
    source = Column(String(50), nullable=False, index=True)

    # Kaynağa ait benzersiz ID (ör: arXiv ID, OpenAlex ID)
    external_id = Column(String(100), unique=True, index=True, nullable=False)

    # 3.Başlık
    # Başlıklar genellikle kısadır ancak bazen çok uzun bilimsel başlıklar olabilir.
    # Bu yüzden karakter sınırını geniş tutuyoruz.
    title = Column(String(500), nullable=False)

    # 4. Özet Metni
    # Neden String yerine Text? String(VARCHAR) veritabanlarında belirli bir karakter limitine 
    # sahiptir (genelde 255). Makale özetleri (abstract) sayfalarca sürebilir. Text tipi 
    # çok daha büyük boyutlu karakter dizilerini depolamak için optimize edilmiştir.
    abstract_text = Column(Text, nullable=True)

    # 5. Yayın Tarihi
    # XML'deki <published> etiketi bir tarih ve saat bilgisi taşır (örn: "2023-10-12T15:30:00Z").
    # Bunu veritabanında da DateTime objesi olarak tutmak, ileride "son 1 ayın makalelerini getir" 
    # gibi tarihsel sorgular yapabilmenizi sağlar.
    publish_date = Column(DateTime, nullable=True, index=True)

    # API kaydının kaynak tarafındaki son guncellenme tarihi.
    updated_date = Column(DateTime, nullable=True)

    # 6. Yazarlar (Şüpheli Nokta!)
    # Burada biraz kalıp dışı düşünelim: Birden fazla yazar var. Onları "Ali, Ayşe, Veli" gibi 
    # tek bir String içinde tutmak şu an için kolaydır. Ancak ileride "Ayşe'nin yazdığı tüm makaleler" 
    # demek isterseniz bu tasarım sizi yavaşlatır (veritabanı normalizasyon kurallarına aykırıdır).
    # Şimdilik talebinize uygun olarak tek sütun (Text) yapıyoruz, ancak profesyonel bir sistemde 
    # 'authors' ayrı bir tablo olup 'Çoka-Çok' (Many-to-Many) ilişki ile bağlanmalıdır.
    authors = Column(Text, nullable=True)

    # 7. URL ve Kategori
    # URL'ler standart metinlerdir. Bir makalenin URL'si veya kategorisi bazen eksik olabilir, 
    # bu ihtimale karşı nullable=True (boş bırakılabilir) olarak ayarlıyoruz.
    url = Column(String(500), nullable=True)
    pdf_url = Column(String(500), nullable=True)
    primary_category = Column(String(100), nullable=True, index=True)
    categories = Column(Text, nullable=True)

    # Yayin kimlikleri ve bibliyometrik metadata.
    doi = Column(String(255), nullable=True, index=True)
    citation_count = Column(Integer, nullable=True)
    venue = Column(String(500), nullable=True)


    # EMBEDDING
    embedding = Column(Vector(768), nullable=True)
    embedding_model = Column(String(120), nullable=True)
    embedding_text_hash = Column(String(64), nullable=True, index=True)
    embedding_created_at = Column(DateTime, nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    language = Column(String(20), nullable=True, index=True)
    document_type = Column(String(50), nullable=True, index=True)
    ingestion_run_id = Column(String(80), nullable=True, index=True)
    
    # CLUSTER ID
    # Makalenin ait olduğu cluster ID'si
    cluster_id = Column(Integer, nullable=True, index=True)
