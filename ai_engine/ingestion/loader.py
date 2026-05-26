from typing import List
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from database.models import Article
from .schemas import RawArticleSchema

def _clean_string(val):
    if isinstance(val, str):
        cleaned = val.replace('\x00', '').strip()
        return cleaned or None
    return val

def save_articles_to_db(db_session: Session, articles: List[RawArticleSchema]) -> int:
    """
    Saves a list of articles to the database.
    Uses PostgreSQL UPSERT to insert new rows and enrich existing rows based on external_id.
    """
    if not articles:
        return 0

    values = []
    for art in articles:
        d = art.to_dict()
        
        # Tüm string alanlardan NUL (\x00) karakterlerini temizle
        for k, v in d.items():
            d[k] = _clean_string(v)
            
        # Veritabanı modelindeki karakter sınırlarına göre kesme işlemi yap
        if d.get("title") and len(d["title"]) > 500:
            d["title"] = d["title"][:497] + "..."
        if d.get("external_id") and len(d["external_id"]) > 100:
            d["external_id"] = d["external_id"][:100]
        length_limits = {
            "source": 50,
            "url": 500,
            "pdf_url": 500,
            "primary_category": 100,
            "doi": 255,
            "venue": 500,
        }
        for field, limit in length_limits.items():
            if d.get(field) and len(d[field]) > limit:
                d[field] = d[field][:limit]
            
        values.append(d)

    total_inserted = 0

    # PostgreSQL'in tek bir sorguda gönderebileceği parametre sınırını aşmamak için
    # verileri 1000'erli paketler (chunk) halinde kaydediyoruz.
    chunk_size = 1000
    for i in range(0, len(values), chunk_size):
        chunk = values[i:i+chunk_size]
        
        stmt = insert(Article).values(chunk)
        update_columns = [
            "source",
            "title",
            "abstract_text",
            "publish_date",
            "updated_date",
            "authors",
            "url",
            "pdf_url",
            "primary_category",
            "categories",
            "doi",
            "citation_count",
            "venue",
        ]
        stmt = stmt.on_conflict_do_update(
            index_elements=['external_id'],
            set_={
                column: sa.func.coalesce(getattr(stmt.excluded, column), getattr(Article, column))
                for column in update_columns
            }
        )

        result = db_session.execute(stmt)
        total_inserted += result.rowcount

    db_session.commit()
    return total_inserted
