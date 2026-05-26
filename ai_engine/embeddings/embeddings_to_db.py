from backend.app.core.DbFunctions import DbFunctions
from backend.app.services.embedding_service import get_embedding_service
from database.db import SessionLocal
from database.models.ArticleData import Article


def generate_missing_article_embeddings(total_articles: int = 3500, batch_size: int = 250) -> int:
    embedding_service = get_embedding_service()
    processed = 0

    db = SessionLocal()
    try:
        # Check current count of articles with embeddings
        existing_count = db.query(Article).filter(Article.embedding.isnot(None)).count()
        print(f"Existing embedded articles: {existing_count}")
        if existing_count >= total_articles:
            print("Enough embeddings already exist.")
            return 0
            
        to_generate = total_articles - existing_count
        print(f"Need to generate embeddings for {to_generate} articles.")
        
        while processed < to_generate:
            current_batch = min(batch_size, to_generate - processed)
            # Query articles needing embeddings
            articles = db.query(Article).filter(
                Article.abstract_text.isnot(None),
                Article.title.isnot(None),
                Article.embedding.is_(None)
            ).limit(current_batch).all()

            if not articles:
                print("No more articles without embeddings.")
                break

            print(f"Embedding batch of {len(articles)} articles... ({processed + len(articles)}/{to_generate})")
            embeddings = embedding_service.embed_documents(articles)

            # Update in single transaction
            for article, embedding in zip(articles, embeddings):
                article.embedding = embedding
            db.commit()
            
            processed += len(articles)
            print(f"Successfully processed {processed} articles in this session.")
            
    except Exception as e:
        db.rollback()
        print(f"Error during embedding generation: {e}")
        raise
    finally:
        db.close()

    return processed


if __name__ == "__main__":
    generate_missing_article_embeddings()
