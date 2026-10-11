"""LLM client factory. Tests (and offline mode) can swap the factory without touching call sites."""
from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from . import settings_store
from .ollama import LLMClient, OllamaClient

LLMFactory = Callable[[Session], LLMClient]


def _default_factory(db: Session) -> LLMClient:
    cfg = settings_store.get_all(db)
    return OllamaClient(cfg["ollama_url"], cfg["answer_model"], cfg["embed_model"])


_factory: LLMFactory = _default_factory


def set_llm_factory(factory: LLMFactory | None) -> None:
    global _factory
    _factory = factory or _default_factory


def get_llm(db: Session) -> LLMClient:
    return _factory(db)
