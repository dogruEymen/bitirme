from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    MODEL_NAME: str = "gemma2:2b"

    class Config:
        env_file = ".env"


settings = Settings()
