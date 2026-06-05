from datetime import UTC, datetime
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
    "metadata_json",
    "language",
    "document_type",
    "ingestion_run_id",
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
    "language": 20,
    "document_type": 50,
    "ingestion_run_id": 80,
}


def _is_computer_science_article(article: RawArticleSchema) -> bool:
    raw_data = article.to_dict()
    source = (raw_data.get("source") or "").lower()
    primary_category = (raw_data.get("primary_category") or "").strip()
    categories = _split_list(raw_data.get("categories"))
    category_values = [primary_category, *categories]
    normalized = [value.lower() for value in category_values if value]

    if source == "arxiv":
        return any(value.startswith("cs.") for value in normalized)

    metadata = raw_data.get("metadata_json") or {}
    if metadata.get("is_computer_science") is True:
        return True

    return any(value in {"computer science", "cs"} for value in normalized)


def _clean_string(val):
    if isinstance(val, str):
        cleaned = val.replace('\x00', '').strip()
        return cleaned or None
    return val


def _article_to_row(article: RawArticleSchema, ingestion_run_id: str | None = None) -> dict:
    raw_data = article.to_dict()
    row = {
        column: _clean_string(raw_data.get(column))
        for column in ARTICLE_INSERT_COLUMNS
    }
    row["language"] = row.get("language") or "en"
    row["document_type"] = row.get("document_type") or "article"
    row["ingestion_run_id"] = row.get("ingestion_run_id") or ingestion_run_id
    row["metadata_json"] = _metadata_json(raw_data, row)

    if row.get("title") and len(row["title"]) > LENGTH_LIMITS["title"]:
        row["title"] = row["title"][:497] + "..."

    for field, limit in LENGTH_LIMITS.items():
        if field == "title":
            continue
        if row.get(field) and len(row[field]) > limit:
            row[field] = row[field][:limit]

    return row


def _split_list(value: str | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in value.split(",") if item.strip()]


def _metadata_json(raw_data: dict, row: dict) -> dict:
    publish_date = row.get("publish_date")
    incoming_metadata = dict(raw_data.get("metadata_json") or {})
    metadata = {
        key: value
        for key, value in incoming_metadata.items()
        if key != "ingestion_source_payload"
    }
    metadata.update(
        {
            "source": row.get("source"),
            "external_id": row.get("external_id"),
            "doi": row.get("doi"),
            "url": row.get("url"),
            "pdf_url": row.get("pdf_url"),
            "venue": row.get("venue"),
            "publish_year": publish_date.year if publish_date else None,
            "publish_month": publish_date.month if publish_date else None,
            "authors_list": _split_list(row.get("authors")),
            "categories_list": _split_list(row.get("categories")),
            "primary_category": row.get("primary_category"),
            "citation_count": row.get("citation_count"),
            "has_pdf": bool(row.get("pdf_url")),
            "language": row.get("language") or "en",
            "document_type": row.get("document_type") or "article",
            "ingestion_run_id": row.get("ingestion_run_id"),
            "source_payload_version": metadata.get("source_payload_version", "v1"),
            "metadata_normalized_at": datetime.now(UTC).isoformat(),
        }
    )
    return metadata


def _dedupe_rows_by_external_id(rows: list[dict]) -> list[dict]:
    rows_by_external_id = {}
    for row in rows:
        rows_by_external_id[row["external_id"]] = row
    return list(rows_by_external_id.values())


def _articles_to_insert_rows(
    articles: List[RawArticleSchema],
    ingestion_run_id: str | None = None,
) -> list[dict]:
    values = []
    for art in articles:
        if not _is_computer_science_article(art):
            continue
        row = _article_to_row(art, ingestion_run_id=ingestion_run_id)
        if not row["source"] or not row["external_id"] or not row["title"] or not row["abstract_text"]:
            continue
        values.append(row)

    return _dedupe_rows_by_external_id(values)


def save_articles_to_db(
    db_session: Session,
    articles: List[RawArticleSchema],
    ingestion_run_id: str | None = None,
) -> int:
    """
    Saves a list of articles to the database.
    Uses PostgreSQL UPSERT to insert new rows and enrich existing rows based on external_id.
    """
    if not articles:
        return 0

    values = _articles_to_insert_rows(articles, ingestion_run_id=ingestion_run_id)
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
