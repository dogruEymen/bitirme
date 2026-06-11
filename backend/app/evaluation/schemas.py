from pydantic import BaseModel, ConfigDict, Field, field_validator


class GoldenQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    question: str
    expected_article_ids: list[int]
    expected_cluster_ids: list[int] = Field(default_factory=list)
    filters: dict = Field(default_factory=dict)
    top_k: int | None = None

    @field_validator("expected_article_ids")
    @classmethod
    def _expected_articles_required(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("expected_article_ids must contain at least one article id.")
        return value

    @field_validator("top_k")
    @classmethod
    def _top_k_positive(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("top_k must be greater than zero.")
        return value


class RetrievalEvalResult(BaseModel):
    question_id: str
    question: str
    expected_article_ids: list[int]
    retrieved_article_ids: list[int]
    rewritten_query: str
    route_reason: str = ""
    filters: dict = Field(default_factory=dict)
    sort_by: str = "relevance"
    hit_at_k: bool
    recall_at_k: float
    precision_at_k: float
    mrr: float
    ndcg_at_k: float
    latency_ms: float
    top_k: int
    uses_rag: bool
    source_count: int
    citation_marker_count: int = 0
    has_sources_section: bool = False
    retrieved_context_empty: bool


class RetrievalEvalSummary(BaseModel):
    question_count: int
    hit_rate_at_k: float
    mean_recall_at_k: float
    mean_precision_at_k: float
    mean_mrr: float
    mean_ndcg_at_k: float
    mean_latency_ms: float


class ClusteringEvalResult(BaseModel):
    article_count: int
    embedded_article_count: int
    clustered_article_count: int
    outlier_count: int
    cluster_count: int
    outlier_ratio: float
    cluster_assignment_coverage: float
    bertopic_outlier_count: int | None = None
    largest_cluster_ratio: float | None = None
    median_cluster_size: float | None = None
    silhouette_score: float | None = None
    davies_bouldin_score: float | None = None
    calinski_harabasz_score: float | None = None
    avg_intra_cluster_cosine_similarity: float | None = None
    avg_centroid_similarity: float | None = None
    skipped_reason: str | None = None
    pairwise_sample_limit: int
