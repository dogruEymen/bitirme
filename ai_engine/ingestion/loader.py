from typing import List
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from database.models import Article
from .schemas import RawArticleSchema

ARTICLE_INSERT_COLUMNS = [
    "source",
    "external_id",
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

ARTICLE_UPDATE_COLUMNS = [
    column for column in ARTICLE_INSERT_COLUMNS
    if column != "external_id"
]

LENGTH_LIMITS = {
    "source": 50,
    "external_id": 100,
    "title": 500,
    "url": 500,
    "pdf_url": 500,
    "primary_category": 100,
    "doi": 255,
    "venue": 500,
}


def _clean_string(val):
    if isinstance(val, str):
        cleaned = val.replace('\x00', '').strip()
        return cleaned or None
    return val


def _article_to_row(article: RawArticleSchema) -> dict:
    raw_data = article.to_dict()
    row = {
        column: _clean_string(raw_data.get(column))
        for column in ARTICLE_INSERT_COLUMNS
    }

    if row.get("title") and len(row["title"]) > LENGTH_LIMITS["title"]:
        row["title"] = row["title"][:497] + "..."

    for field, limit in LENGTH_LIMITS.items():
        if field == "title":
            continue
        if row.get(field) and len(row[field]) > limit:
            row[field] = row[field][:limit]

    return row


def save_articles_to_db(db_session: Session, articles: List[RawArticleSchema]) -> int:
    """
    Saves a list of articles to the database.
    Uses PostgreSQL UPSERT to insert new rows and enrich existing rows based on external_id.
    """
    if not articles:
        return 0

    values = []
    for art in articles:
        row = _article_to_row(art)
        if not row["source"] or not row["external_id"] or not row["title"]:
            continue
        values.append(row)

    if not values:
        return 0

    total_inserted = 0

    # PostgreSQL'in tek bir sorguda gönderebileceği parametre sınırını aşmamak için
    # verileri 1000'erli paketler (chunk) halinde kaydediyoruz.
    chunk_size = 1000
    try:
        for i in range(0, len(values), chunk_size):
            chunk = values[i:i+chunk_size]

            stmt = insert(Article).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=['external_id'],
                set_={
                    column: sa.func.coalesce(getattr(stmt.excluded, column), getattr(Article, column))
                    for column in ARTICLE_UPDATE_COLUMNS
                }
            )

            result = db_session.execute(stmt)
            total_inserted += result.rowcount

        db_session.commit()
    except Exception:
        db_session.rollback()
        raise

    return total_inserted
