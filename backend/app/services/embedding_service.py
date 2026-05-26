from functools import lru_cache

import torch
from sentence_transformers import SentenceTransformer


EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-base"


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return SentenceTransformer(EMBEDDING_MODEL_NAME, device=device)


class EmbeddingService:
    def __init__(self, model: SentenceTransformer | None = None):
        self.model = model or get_embedding_model()

    def embed_query(self, query: str) -> list[float]:
        text = f"query: {query}"
        vector = self.model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def embed_document(self, title: str, abstract: str | None) -> list[float]:
        text = self._document_text(title, abstract)
        vector = self.model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def embed_documents(self, articles) -> list[list[float]]:
        texts = [
            self._document_text(article.title, article.abstract_text)
            for article in articles
        ]
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]

    @staticmethod
    def _document_text(title: str, abstract: str | None) -> str:
        return f"passage: {title}\n\n{abstract or ''}"


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
