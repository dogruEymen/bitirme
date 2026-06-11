from functools import lru_cache
import hashlib

import torch
from sentence_transformers import SentenceTransformer

from ai_engine.data_hygiene import build_embedding_text
from backend.app.core.config import settings

EMBEDDING_MODEL_NAME = settings.EMBEDDING_MODEL_NAME
SUPPORTED_EMBEDDING_DEVICES = {"auto", "cuda", "mps", "cpu"}


def _mps_is_available() -> bool:
    mps_backend = getattr(torch.backends, "mps", None)
    return bool(mps_backend and mps_backend.is_available())


def resolve_embedding_device(requested_device: str | None = None) -> str:
    device = (requested_device or settings.EMBEDDING_DEVICE).strip().lower()
    if device not in SUPPORTED_EMBEDDING_DEVICES:
        supported = ", ".join(sorted(SUPPORTED_EMBEDDING_DEVICES))
        raise ValueError(f"Unsupported embedding device '{device}'. Use one of: {supported}.")

    if device == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if _mps_is_available():
            return "mps"
        return "cpu"

    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("EMBEDDING_DEVICE=cuda was requested, but CUDA is not available.")
    if device == "mps" and not _mps_is_available():
        raise RuntimeError("EMBEDDING_DEVICE=mps was requested, but Apple MPS is not available.")
    return device


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    device = resolve_embedding_device()
    return SentenceTransformer(EMBEDDING_MODEL_NAME, device=device)


class EmbeddingService:
    def __init__(self, model: SentenceTransformer | None = None):
        self.model = model or get_embedding_model()

    def encode(self, sentences):
        return self.model.encode(
            sentences,
            normalize_embeddings=True,
            batch_size=settings.EMBEDDING_ENCODE_BATCH_SIZE,
        )

    def embed_query(self, query: str) -> list[float]:
        vector = self.encode(self.query_text(query))
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
        vector = self.encode(text)
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
        vectors = self.encode(texts)
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
        return EmbeddingService.passage_text(build_embedding_text(title, abstract))

    @staticmethod
    def query_text(query: str) -> str:
        return f"query: {query}"

    @staticmethod
    def passage_text(text: str) -> str:
        normalized = str(text or "").strip()
        if normalized.lower().startswith("passage:"):
            return normalized
        return f"passage: {normalized}"

    @staticmethod
    def text_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
