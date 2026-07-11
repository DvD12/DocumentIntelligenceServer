from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Values come from env vars / .env only."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    mcp_api_key: str = "change-me"
    ui_password: str = "change-me"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    db_path: str = "data/metadata.db"
    embed_model: str = "text-embedding-3-small"
    embed_dim: int = 1536
    chunk_tokens: int = 450
    chunk_overlap: float = 0.15


@lru_cache
def get_settings() -> Settings:
    return Settings()
