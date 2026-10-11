"""Application configuration, loaded from environment / .env (never hardcoded secrets)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT_DIR / ".env"), env_prefix="RM_", extra="ignore")

    data_dir: Path = ROOT_DIR / "data"
    database_url: str | None = None  # defaults to sqlite file in data_dir
    secret_key: str | None = None  # generated into data_dir/.secret on first run if unset
    token_ttl_hours: int = 24 * 14

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    frontend_dist: Path = ROOT_DIR / "frontend" / "dist"

    # Ollama defaults (user-editable afterwards in Settings; stored in the database)
    ollama_url: str = "http://localhost:11434"
    answer_model: str = "qwen2.5:7b"
    embed_model: str = "nomic-embed-text"

    # Pipeline
    max_upload_mb: int = 100
    chunk_chars: int = 900
    chunk_overlap: int = 150
    process_inline: bool = False  # tests set this to run the pipeline synchronously

    # Retrieval / grounding
    retrieve_k: int = 8
    min_semantic_score: float = 0.35
    min_keyword_coverage: float = 0.34

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{(self.data_dir / 'researchmind.db').as_posix()}"

    @property
    def papers_dir(self) -> Path:
        return self.data_dir / "papers"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.papers_dir.mkdir(parents=True, exist_ok=True)
    return s
