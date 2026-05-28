from pydantic import BaseModel, Field
from typing import Any, Optional
from datetime import datetime

class RawArticleSchema(BaseModel):
    """
    Standardized schema for an article extracted from any API source.
    This schema directly maps to the `Article` SQLAlchemy model.
    """
    source: str = Field(..., description="Source of the article (e.g., 'arxiv', 'openalex', 'semanticscholar')")
    external_id: str = Field(..., description="Unique ID from the source")
    title: str = Field(..., description="Title of the article")
    abstract_text: Optional[str] = Field(None, description="Abstract of the article")
    publish_date: Optional[datetime] = Field(None, description="Publication date")
    updated_date: Optional[datetime] = Field(None, description="Last updated date from the source")
    authors: Optional[str] = Field(None, description="Comma-separated list of authors")
    url: Optional[str] = Field(None, description="Landing page URL")
    pdf_url: Optional[str] = Field(None, description="URL to the PDF file")
    primary_category: Optional[str] = Field(None, description="Primary category or topic")
    categories: Optional[str] = Field(None, description="Comma-separated list of categories or topics")
    doi: Optional[str] = Field(None, description="Digital Object Identifier")
    citation_count: Optional[int] = Field(None, description="Citation count reported by the source")
    venue: Optional[str] = Field(None, description="Publication venue")
    metadata_json: Optional[dict[str, Any]] = Field(None, description="Source-specific metadata")
    language: Optional[str] = Field("en", description="Detected or assumed language")
    document_type: Optional[str] = Field("article", description="Document type")
    ingestion_run_id: Optional[str] = Field(None, description="Ingestion run identifier")

    def to_dict(self) -> dict:
        """Helper to convert to a dictionary suitable for SQLAlchemy ingestion."""
        # Convert HttpUrl to string if present (pydantic v2 handles this differently, but safe fallback)
        data = self.model_dump()
        return data
