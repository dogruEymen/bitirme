import argparse
import csv
import sys
from datetime import UTC, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import settings
from backend.app.services.embedding_service import EmbeddingService, get_embedding_service
from ai_engine.data_hygiene import valid_title_and_abstract
from database.db import SessionLocal
from database.models.ArticleData import Article

DEFAULT_CLEAN_PAPER_CSVS = [
    PROJECT_ROOT / "exports/data_hygiene/clean_papers.csv",
    PROJECT_ROOT / "exports/data_hygiene_openalex/clean_papers.csv",
]


def embedding_input_text(article: Article) -> str:
    return EmbeddingService.document_text(
        title=article.title,
        abstract=article.abstract_text,
        source=article.source,
        venue=article.venue,
        primary_category=article.primary_category,
        publish_date=article.publish_date,
    )


def embedding_text_hash(text: str) -> str:
    return EmbeddingService.text_hash(text)


def existing_clean_paper_csvs() -> list[Path]:
    return [path for path in DEFAULT_CLEAN_PAPER_CSVS if path.exists()]


def iter_clean_embedding_rows(csv_paths: list[Path], total_articles: int):
    emitted_ids = set()
    emitted_count = 0
    for csv_path in csv_paths:
        with csv_path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if emitted_count >= total_articles:
                    return
                article_id = row.get("id")
                embedding_text = row.get("embedding_text")
                if not article_id or not embedding_text:
                    continue
                article_id = int(article_id)
                if article_id in emitted_ids:
                    continue
                emitted_ids.add(article_id)
                emitted_count += 1
                yield article_id, embedding_text


def generate_embeddings_from_clean_csvs(
    csv_paths: list[Path],
    total_articles: int = 3500,
    batch_size: int = 250,
) -> int:
    embedding_service = get_embedding_service()
    updated = 0
    scanned = 0
    pending: list[tuple[int, str]] = []

    db = SessionLocal()
    try:
        for article_id, embedding_text in iter_clean_embedding_rows(csv_paths, total_articles):
            pending.append((article_id, embedding_text))
            if len(pending) >= batch_size:
                batch_updated = _process_clean_embedding_batch(db, embedding_service, pending)
                updated += batch_updated
                scanned += len(pending)
                print(f"Scanned {scanned} clean CSV rows and updated {updated} embeddings in this session.")
                pending = []

        if pending:
            batch_updated = _process_clean_embedding_batch(db, embedding_service, pending)
            updated += batch_updated
            scanned += len(pending)
            print(f"Scanned {scanned} clean CSV rows and updated {updated} embeddings in this session.")
    except Exception as e:
        db.rollback()
        print(f"Error during clean CSV embedding generation: {e}")
        raise
    finally:
        db.close()

    return updated


def _process_clean_embedding_batch(db, embedding_service, rows: list[tuple[int, str]]) -> int:
    article_ids = [article_id for article_id, _ in rows]
    articles = db.query(Article).filter(Article.id.in_(article_ids)).all()
    articles_by_id = {article.id: article for article in articles}

    embedding_jobs = []
    for article_id, embedding_text in rows:
        article = articles_by_id.get(article_id)
        if article is None:
            continue
        text_hash = embedding_text_hash(embedding_text)
        if (
            article.embedding is not None
            and article.embedding_model == settings.EMBEDDING_MODEL_NAME
            and article.embedding_text_hash == text_hash
        ):
            continue
        embedding_jobs.append((article, embedding_text, text_hash))

    if not embedding_jobs:
        return 0

    print(f"Embedding batch of {len(embedding_jobs)} clean CSV articles...")
    vectors = embedding_service.model.encode(
        [job[1] for job in embedding_jobs],
        normalize_embeddings=True,
    )

    for (article, _, text_hash), vector in zip(embedding_jobs, vectors):
        article.embedding = vector.tolist()
        article.embedding_model = settings.EMBEDDING_MODEL_NAME
        article.embedding_text_hash = text_hash
        article.embedding_created_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
    return len(embedding_jobs)


def generate_missing_article_embeddings(total_articles: int = 3500, batch_size: int = 250) -> int:
    embedding_service = get_embedding_service()
    scanned = 0
    updated = 0
    last_seen_id = 0

    db = SessionLocal()
    try:
        while scanned < total_articles:
            current_batch = min(batch_size, total_articles - scanned)
            articles = (
                db.query(Article)
                .filter(Article.abstract_text.isnot(None), Article.title.isnot(None))
                .filter(Article.id > last_seen_id)
                .order_by(Article.id.asc())
                .limit(current_batch)
                .all()
            )

            if not articles:
                break
            last_seen_id = articles[-1].id

            embedding_jobs = []
            for article in articles:
                if not valid_title_and_abstract(article.title, article.abstract_text):
                    continue
                text = embedding_input_text(article)
                text_hash = embedding_text_hash(text)
                if (
                    article.embedding is not None
                    and article.embedding_model == settings.EMBEDDING_MODEL_NAME
                    and article.embedding_text_hash == text_hash
                ):
                    continue
                embedding_jobs.append((article, text, text_hash))

            if not embedding_jobs:
                scanned += len(articles)
                continue

            print(f"Embedding batch of {len(embedding_jobs)} changed articles...")
            vectors = embedding_service.model.encode(
                [job[1] for job in embedding_jobs],
                normalize_embeddings=True,
            )

            for (article, _, text_hash), vector in zip(embedding_jobs, vectors):
                article.embedding = vector.tolist()
                article.embedding_model = settings.EMBEDDING_MODEL_NAME
                article.embedding_text_hash = text_hash
                article.embedding_created_at = datetime.now(UTC).replace(tzinfo=None)
            db.commit()
            updated += len(embedding_jobs)
            
            scanned += len(articles)
            print(f"Scanned {scanned} articles and updated {updated} embeddings in this session.")
            
    except Exception as e:
        db.rollback()
        print(f"Error during embedding generation: {e}")
        raise
    finally:
        db.close()

    return updated


def parse_args():
    parser = argparse.ArgumentParser(description="Generate or refresh article embeddings with metadata hash skip logic.")
    parser.add_argument("--total-articles", type=int, default=3500, help="Maximum number of articles to scan.")
    parser.add_argument("--batch-size", type=int, default=250, help="Number of articles to scan per batch.")
    parser.add_argument(
        "--clean-papers-csv",
        action="append",
        type=Path,
        default=None,
        help="Clean data hygiene CSV to use as the embedding source. Can be passed multiple times.",
    )
    parser.add_argument(
        "--raw-db",
        action="store_true",
        help="Ignore clean CSV exports and use the legacy DB scan fallback.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    clean_csvs = [] if args.raw_db else (args.clean_papers_csv or existing_clean_paper_csvs())
    if clean_csvs:
        print("Using clean data hygiene CSVs for embedding input:")
        for csv_path in clean_csvs:
            print(f"- {csv_path}")
        generate_embeddings_from_clean_csvs(
            csv_paths=clean_csvs,
            total_articles=args.total_articles,
            batch_size=args.batch_size,
        )
    else:
        print("No clean CSVs found. Falling back to raw DB scan with lightweight hygiene checks.")
        generate_missing_article_embeddings(total_articles=args.total_articles, batch_size=args.batch_size)
