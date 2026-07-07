"""
Centralized configuration for the Vignan IIT RAG chatbot.

All tunables are read from environment variables (or a local `.env` file)
so the same code can run in dev/staging/prod without edits.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    # ---- Site to crawl ----
    base_url: str = "https://vignaniit.edu.in"
    max_pages: int = 300
    crawl_depth: int = 6
    request_timeout_ms: int = 20000

    # ---- Vector store ----
    chroma_db_dir: str = "../data/chroma_db"
    collection_name: str = "vignaniit_site"

    # ---- Embeddings / chunking ----
    embedding_model: str = "all-MiniLM-L6-v2"
    chunk_size_words: int = 350
    chunk_overlap_words: int = 60
    top_k: int = 5

    # ---- LLM ----
    llm_provider: str = "openai"  # "openai" | "gemini"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"

    # ---- API ----
    cors_origins: str = "*"

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — import this everywhere instead of
    instantiating Settings() directly, so env is parsed only once."""
    return Settings()
