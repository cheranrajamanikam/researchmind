"""Shared FastAPI dependencies and ownership helpers."""
from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Paper, Project, Thread, User
from ..security import current_user
from ..services.llm import get_llm
from ..services.ollama import LLMClient


def llm_dep(db: Session = Depends(get_db)) -> LLMClient:
    return get_llm(db)


def project_or_404(db: Session, project_id: int) -> Project:
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


def paper_or_404(db: Session, paper_id: int) -> Paper:
    p = db.get(Paper, paper_id)
    if not p:
        raise HTTPException(404, "Paper not found")
    return p


def thread_or_404(db: Session, thread_id: int) -> Thread:
    t = db.get(Thread, thread_id)
    if not t:
        raise HTTPException(404, "Thread not found")
    return t


__all__ = ["Depends", "User", "current_user", "get_db", "llm_dep", "paper_or_404", "project_or_404", "thread_or_404"]
