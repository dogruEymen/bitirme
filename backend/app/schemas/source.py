from datetime import datetime

from pydantic import BaseModel


class SourceReference(BaseModel):
    source_id: str
    article_id: int
    title: str
    source: str | None = None
    external_id: str | None = None
    doi: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    venue: str | None = None
    publish_date: datetime | None = None
    authors: str | None = None
    cluster_id: int | None = None
    score: float | None = None
    vector_score: float | None = None
    bm25_score: float | None = None
    vector_rank: int | None = None
    bm25_rank: int | None = None
    fusion_score: float | None = None
    reranker_score: float | None = None
    retrieval_source: str | None = None
