from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal
from database.models.ArticleData import Article


def resolve_output_path(path: str | Path) -> Path:
    output = Path(path)
    if output.is_absolute():
        return output
    return PROJECT_ROOT / output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the SQLite FTS5 BM25 sidecar index for article retrieval.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(settings.RAG_BM25_INDEX_PATH),
        help="SQLite index output path. Relative paths are resolved from the project root.",
    )
    parser.add_argument("--batch-size", type=int, default=5000, help="DB rows to stream per batch.")
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum number of articles to index.")
    return parser.parse_args(argv)


def build_bm25_index(output_path: Path, batch_size: int = 5000, limit: int | None = None) -> dict[str, object]:
    output_path = resolve_output_path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    if temp_path.exists():
        temp_path.unlink()

    indexed = 0
    db = SessionLocal()
    try:
        with sqlite3.connect(temp_path) as conn:
            _initialize_index(conn)
            last_seen_id = 0
            while True:
                remaining = None if limit is None else max(0, limit - indexed)
                if remaining == 0:
                    break
                current_batch = batch_size if remaining is None else min(batch_size, remaining)
                rows = (
                    db.query(Article)
                    .filter(
                        Article.id > last_seen_id,
                        Article.title.isnot(None),
                        Article.abstract_text.isnot(None),
                    )
                    .order_by(Article.id.asc())
                    .limit(current_batch)
                    .all()
                )
                if not rows:
                    break
                last_seen_id = rows[-1].id
                payload = [_article_row(article) for article in rows if _has_indexable_text(article)]
                conn.executemany(
                    """
                    INSERT INTO articles_fts (
                        article_id,
                        title,
                        abstract_text,
                        source,
                        primary_category,
                        categories,
                        cluster_id,
                        doi,
                        venue,
                        publish_date
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload,
                )
                indexed += len(payload)
                conn.commit()
                print(f"Indexed {indexed} articles into {temp_path}")

            metadata = _metadata(db, indexed)
            conn.executemany(
                "INSERT INTO index_metadata(key, value) VALUES (?, ?)",
                [(key, str(value)) for key, value in metadata.items()],
            )
            conn.commit()

        os.replace(temp_path, output_path)
        return metadata
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
    finally:
        db.close()


def _initialize_index(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute(
        """
        CREATE VIRTUAL TABLE articles_fts USING fts5(
            article_id UNINDEXED,
            title,
            abstract_text,
            source UNINDEXED,
            primary_category UNINDEXED,
            categories UNINDEXED,
            cluster_id UNINDEXED,
            doi UNINDEXED,
            venue UNINDEXED,
            publish_date UNINDEXED,
            tokenize = 'porter unicode61'
        )
        """
    )
    conn.execute("CREATE TABLE index_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")


def _has_indexable_text(article: Article) -> bool:
    return bool((article.title or "").strip() and (article.abstract_text or "").strip())


def _article_row(article: Article) -> tuple:
    publish_date = article.publish_date.date().isoformat() if article.publish_date else ""
    return (
        article.id,
        article.title or "",
        article.abstract_text or "",
        article.source or "",
        article.primary_category or "",
        article.categories or "",
        "" if article.cluster_id is None else str(article.cluster_id),
        article.doi or "",
        article.venue or "",
        publish_date,
    )


def _metadata(db, indexed: int) -> dict[str, object]:
    total_articles = db.query(Article).count()
    embedded_articles = db.query(Article).filter(Article.embedding.isnot(None)).count()
    max_article_id = db.query(Article.id).order_by(Article.id.desc()).limit(1).scalar()
    return {
        "built_at": datetime.now(UTC).isoformat(),
        "article_count": indexed,
        "total_articles": total_articles,
        "embedded_articles": embedded_articles,
        "embedding_model": settings.EMBEDDING_MODEL_NAME,
        "source_db_fingerprint": f"articles:{total_articles}:embedded:{embedded_articles}:max_id:{max_article_id}",
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.batch_size < 1:
        print("--batch-size must be greater than zero.", file=sys.stderr)
        return 2
    if args.limit is not None and args.limit < 1:
        print("--limit must be greater than zero when provided.", file=sys.stderr)
        return 2

    metadata = build_bm25_index(args.output, batch_size=args.batch_size, limit=args.limit)
    output_path = resolve_output_path(args.output)
    print(f"BM25 index written to {output_path}")
    for key, value in metadata.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
