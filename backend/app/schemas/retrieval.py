from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.schemas.source import SourceReference


class RetrievalFilters(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    source: str | None = None
    cluster_id: int | None = None
    primary_category: str | None = None
    categories_any: list[str] = Field(default_factory=list)
    venue: str | None = None
    doi: str | None = None
    has_pdf: bool | None = None
    min_citation_count: int | None = None
    publish_date_from: date | None = None
    publish_date_to: date | None = None
    article_ids: list[int] = Field(default_factory=list)

    @field_validator("categories_any", "article_ids", mode="before")
    @classmethod
    def _none_to_empty_list(cls, value):
        if value is None:
            return []
        return value


class RouteDecision(BaseModel):
    use_rag: bool = False
    reason: str = ""
    rewritten_query: str
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    top_k: int = 5
    sort_by: str = "relevance"


class RetrievedArticle(BaseModel):
    source: SourceReference
    abstract_text: str | None = None
    primary_category: str | None = None
    categories: str | None = None
    citation_count: int | None = None
