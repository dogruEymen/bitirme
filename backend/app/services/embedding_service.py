from functools import lru_cache
import hashlib

import torch
from sentence_transformers import SentenceTransformer

from backend.app.core.config import settings

EMBEDDING_MODEL_NAME = settings.EMBEDDING_MODEL_NAME


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return SentenceTransformer(EMBEDDING_MODEL_NAME, device=device)


class EmbeddingService:
    def __init__(self, model: SentenceTransformer | None = None):
        self.model = model or get_embedding_model()

    def embed_query(self, query: str) -> list[float]:
        vector = self.model.encode(self.query_text(query), normalize_embeddings=True)
        return vector.tolist()

    def embed_document(
        self,
        title: str,
        abstract: str | None,
        source: str | None = None,
        venue: str | None = None,
        primary_category: str | None = None,
        publish_date=None,
    ) -> list[float]:
        text = self.document_text(
            title=title,
            abstract=abstract,
            source=source,
            venue=venue,
            primary_category=primary_category,
            publish_date=publish_date,
        )
        vector = self.model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def embed_documents(self, articles) -> list[list[float]]:
        texts = [
            self.document_text(
                title=article.title,
                abstract=article.abstract_text,
                source=getattr(article, "source", None),
                venue=getattr(article, "venue", None),
                primary_category=getattr(article, "primary_category", None),
                publish_date=getattr(article, "publish_date", None),
            )
            for article in articles
        ]
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]

    @staticmethod
    def document_text(
        title: str,
        abstract: str | None,
        source: str | None = None,
        venue: str | None = None,
        primary_category: str | None = None,
        publish_date=None,
    ) -> str:
        publish_value = publish_date.isoformat() if hasattr(publish_date, "isoformat") else publish_date
        return (
            f"passage: {title}\n\n"
            f"{abstract or ''}\n\n"
            "metadata: "
            f"source={source or ''}; "
            f"venue={venue or ''}; "
            f"category={primary_category or ''}; "
            f"date={publish_value or ''}"
        )

    @staticmethod
    def query_text(query: str) -> str:
        return f"query: {query}"

    @staticmethod
    def text_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
