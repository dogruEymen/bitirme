from backend.app.core.DbFunctions import DbFunctions
from backend.app.services.embedding_service import get_embedding_service


def generate_missing_article_embeddings(total_articles: int = 50000, batch_size: int = 1000) -> int:
    embedding_service = get_embedding_service()
    processed = 0

    while processed < total_articles:
        current_batch = min(batch_size, total_articles - processed)
        articles = DbFunctions.get_articles_for_embedding(current_batch)

        if not articles:
            print("Islenecek makale kalmadi")
            break

        print(f"{len(articles)} makale isleniyor... ({processed + len(articles)}/{total_articles})")
        embeddings = embedding_service.embed_documents(articles)

        for article, embedding in zip(articles, embeddings):
            DbFunctions.update_embedding(article.id, embedding)

        processed += len(articles)
        print(f"Toplam islenen: {processed}")

    return processed


if __name__ == "__main__":
    generate_missing_article_embeddings()
