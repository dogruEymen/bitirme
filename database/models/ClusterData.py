from sqlalchemy import Column, Integer, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from database.db import Base
from datetime import datetime

class Cluster(Base):
    __tablename__ = "clusters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Cluster numarası (BERTopic tarafından atanan topic ID)
    cluster_id = Column(Integer, nullable=False, unique=True, index=True)
    
    # Cluster açıklaması (top 10 kelimeler)
    cluster_description = Column(Text, nullable=True)
    
    # Clusterdaki makale sayısı
    article_count = Column(Integer, default=0)
    
    # Clusterdaki tüm makale ID'leri (virgülle ayrılmış)
    article_ids = Column(Text, nullable=True)
    
    # Clusterın temsilci dokümanları (virgülle ayrılmış)
    representative_docs = Column(Text, nullable=True)

    metadata_json = Column(JSONB, nullable=True)
    
    # Oluşturulma tarihi
    created_at = Column(DateTime, default=datetime.utcnow)
