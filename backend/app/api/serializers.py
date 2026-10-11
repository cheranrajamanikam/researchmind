"""Turn ORM rows into the JSON shapes the frontend consumes."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..models import Message, Paper, Project, Thread

RUNNING = {"extracting", "chunking", "embedding"}
DONE = {"ready", "ready_keyword_only"}
FAILED = {"failed", "no_text"}


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def job_state(status: str) -> str:
    if status in RUNNING:
        return "running"
    if status in DONE:
        return "done"
    if status in FAILED:
        return "failed"
    return "queued"


def paper_out(p: Paper) -> dict[str, Any]:
    return {
        "id": p.id,
        "project_id": p.project_id,
        "title": p.title,
        "authors": p.authors,
        "year": p.year,
        "venue": p.venue,
        "filename": p.filename,
        "page_count": p.page_count,
        "status": p.status,
        "job_state": job_state(p.status),
        "stage": p.stage,
        "progress": p.progress,
        "detail": p.detail,
        "error": p.error,
        "chunk_count": p.chunk_count,
        "embedded_count": p.embedded_count,
        "created_at": iso(p.created_at),
    }


def project_out(p: Project, papers: int = 0, threads: int = 0) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "question": p.question,
        "think_first": p.think_first,
        "paper_count": papers,
        "thread_count": threads,
        "created_at": iso(p.created_at),
        "updated_at": iso(p.updated_at),
    }


def message_out(m: Message) -> dict[str, Any]:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "status": m.status,
        "citations": m.citations or [],
        "meta": m.meta or {},
        "created_at": iso(m.created_at),
    }


def thread_out(t: Thread, with_messages: bool = False) -> dict[str, Any]:
    msgs = t.messages
    last_assistant = next((m for m in reversed(msgs) if m.role == "assistant"), None)
    out: dict[str, Any] = {
        "id": t.id,
        "project_id": t.project_id,
        "title": t.title,
        "starred": t.starred,
        "message_count": len(msgs),
        "last_status": last_assistant.status if last_assistant else None,
        "last_citations": len(last_assistant.citations or []) if last_assistant else 0,
        "created_at": iso(t.created_at),
        "updated_at": iso(t.updated_at),
    }
    if with_messages:
        out["messages"] = [message_out(m) for m in msgs]
    return out
