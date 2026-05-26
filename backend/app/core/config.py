from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gemma4"

    class Config:
        env_file = ".env"


settings = Settings()
