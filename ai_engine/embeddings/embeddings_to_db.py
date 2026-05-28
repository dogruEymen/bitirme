import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import settings
from backend.app.services.embedding_service import EmbeddingService, get_embedding_service
from database.db import SessionLocal
from database.models.ArticleData import Article


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
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    generate_missing_article_embeddings(total_articles=args.total_articles, batch_size=args.batch_size)
