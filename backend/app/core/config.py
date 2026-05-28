from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "academic_platform"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/academic_platform"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    MODEL_NAME: str = "gemma4:e4b"
    EMBEDDING_MODEL_NAME: str = "intfloat/multilingual-e5-base"
    RAG_TOP_K: int = 5
    RAG_CANDIDATE_K: int = 25
    CHAT_HISTORY_LIMIT: int = 12
    CHAT_SUMMARY_TRIGGER_MESSAGES: int = 24


settings = Settings()
