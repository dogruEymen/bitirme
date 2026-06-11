from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "academic_platform"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/academic_platform"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    MODEL_NAME: str = "gemma4:e4b"
    EMBEDDING_MODEL_NAME: str = "intfloat/multilingual-e5-base"
    EMBEDDING_DEVICE: str = "auto"
    EMBEDDING_ENCODE_BATCH_SIZE: int = 64
    CLUSTERING_HARDWARE_PROFILE: str = "auto"
    CLUSTERING_THREADS: int | None = None
    CLUSTERING_LOW_MEMORY: bool = True
    CLUSTERING_HDBSCAN_JOBS: int | None = None
    RAG_TOP_K: int = 5
    RAG_CANDIDATE_K: int = 25
    RAG_RETRIEVAL_MODE: str = "hybrid"
    RAG_VECTOR_TOP_K: int = 25
    RAG_BM25_TOP_K: int = 25
    RAG_FINAL_TOP_K: int = 5
    RAG_FUSION_METHOD: str = "rrf"
    RAG_RRF_K: int = 60
    RAG_WEIGHTED_ALPHA: float = 0.65
    RAG_BM25_INDEX_PATH: str = "exports/retrieval/articles_bm25.sqlite"
    RAG_DEBUG_RETRIEVAL: bool = False
    RAG_RERANKER_ENABLED: bool = True
    RAG_RERANKER_MODEL_NAME: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RAG_RERANKER_TOP_N: int = 50
    CHAT_HISTORY_LIMIT: int = 12
    CHAT_SUMMARY_TRIGGER_MESSAGES: int = 24


settings = Settings()
