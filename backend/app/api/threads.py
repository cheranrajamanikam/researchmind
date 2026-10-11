"""Research threads (saved conversations) and the Copilot, both backed by the grounded Q&A service."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Message, Thread, utcnow
from ..security import current_user
from ..services.grounding import answer_question
from ..services.ollama import LLMClient
from .deps import llm_dep, project_or_404, thread_or_404
from .schemas import AskIn, CopilotIn, ThreadIn, ThreadPatch
from .serializers import message_out, thread_out

router = APIRouter(tags=["threads"], dependencies=[Depends(current_user)])

COPILOT_TITLE = "Copilot questions"


def _ask(db: Session, thread: Thread, content: str, reading_mode: bool, llm: LLMClient) -> dict:
    history = [(m.role, m.content) for m in thread.messages[-6:]]
    user_msg = Message(thread_id=thread.id, role="user", content=content.strip(), status="answered")
    db.add(user_msg)
    db.flush()
    result = answer_question(db, content.strip(), thread.project_id, llm, reading_mode, history)
    assistant = Message(
        thread_id=thread.id, role="assistant", content=result.content, status=result.status,
        citations=result.citations, meta={**result.meta, "reading_mode": reading_mode},
    )
    db.add(assistant)
    if thread.title in ("New thread", "") or thread.title == "New thread":
        thread.title = content.strip()[:80]
    thread.updated_at = utcnow()
    db.commit()
    return {"user": message_out(user_msg), "assistant": message_out(assistant)}


@router.get("/threads")
def list_threads(project_id: int | None = None, db: Session = Depends(get_db)) -> list[dict]:
    q = db.query(Thread)
    if project_id:
        q = q.filter(Thread.project_id == project_id)
    return [thread_out(t) for t in q.order_by(Thread.updated_at.desc()).all()]


@router.post("/threads", status_code=201)
def create_thread(body: ThreadIn, db: Session = Depends(get_db)) -> dict:
    project_or_404(db, body.project_id)
    t = Thread(project_id=body.project_id, title=body.title.strip() or "New thread")
    db.add(t)
    db.commit()
    return thread_out(t, with_messages=True)


@router.get("/threads/{thread_id}")
def get_thread(thread_id: int, db: Session = Depends(get_db)) -> dict:
    return thread_out(thread_or_404(db, thread_id), with_messages=True)


@router.patch("/threads/{thread_id}")
def patch_thread(thread_id: int, body: ThreadPatch, db: Session = Depends(get_db)) -> dict:
    t = thread_or_404(db, thread_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(t, k, v)
    db.commit()
    return thread_out(t)


@router.delete("/threads/{thread_id}", status_code=204)
def delete_thread(thread_id: int, db: Session = Depends(get_db)) -> None:
    db.delete(thread_or_404(db, thread_id))
    db.commit()


@router.post("/threads/{thread_id}/messages")
def ask_in_thread(thread_id: int, body: AskIn, db: Session = Depends(get_db), llm: LLMClient = Depends(llm_dep)) -> dict:
    return _ask(db, thread_or_404(db, thread_id), body.content, body.reading_mode, llm)


@router.post("/copilot/ask")
def copilot_ask(body: CopilotIn, db: Session = Depends(get_db), llm: LLMClient = Depends(llm_dep)) -> dict:
    project_or_404(db, body.project_id)
    thread = db.query(Thread).filter(Thread.project_id == body.project_id, Thread.title == COPILOT_TITLE).first()
    if not thread:
        thread = Thread(project_id=body.project_id, title=COPILOT_TITLE)
        db.add(thread)
        db.commit()
    out = _ask(db, thread, body.question, body.reading_mode, llm)
    out["thread_id"] = thread.id
    return out
