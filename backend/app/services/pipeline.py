"""PDF -> pages -> page-aware chunks -> embeddings, run in the background with visible progress."""
from __future__ import annotations

import hashlib
import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..models import Chunk, Page, Paper
from .chunking import chunk_document
from .llm import get_llm
from .ollama import OllamaError, OllamaUnavailable
from .pdf import extract_pdf
from .retrieval import VECTOR_CACHE, to_blob

log = logging.getLogger("researchmind.pipeline")

# Analysis modules register work to run once a paper is searchable (e.g. structured extraction).
PostProcess = Callable[[Session, Paper], None]
POST_PROCESS: list[tuple[str, PostProcess]] = []

EMBED_BATCH = 16
_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()


def register_post_process(name: str, fn: PostProcess) -> None:
    if all(n != name for n, _ in POST_PROCESS):
        POST_PROCESS.append((name, fn))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _set(db: Session, paper: Paper, status: str, progress: int, stage: str, detail: str = "") -> None:
    paper.status, paper.progress, paper.stage, paper.detail = status, progress, stage[:64], detail[:400]
    db.commit()


def process_paper(paper_id: int) -> None:
    """Run the whole pipeline for one paper. Never raises: failures are recorded on the paper."""
    db = SessionLocal()
    try:
        paper = db.get(Paper, paper_id)
        if not paper:
            return
        try:
            _run(db, paper)
        except Exception as e:  # noqa: BLE001 - recorded for the user, logged for us
            log.exception("processing failed for paper %s", paper_id)
            db.rollback()
            paper = db.get(Paper, paper_id)
            if paper:
                paper.status, paper.stage, paper.error = "failed", "Processing failed", str(e)[:1000]
                paper.detail, paper.progress = "Open the paper's menu and choose Retry.", 0
                db.commit()
    finally:
        db.close()


def _run(db: Session, paper: Paper) -> None:
    cfg = get_settings()
    path = Path(paper.file_path)
    paper.error = ""
    _set(db, paper, "extracting", 3, "Extracting text", "Reading the PDF")

    def on_page(i: int, total: int) -> None:
        if i == total or i % 3 == 0:
            _set(db, paper, "extracting", 3 + int(37 * i / max(total, 1)), "Extracting text", f"page {i} of {total}")

    pdf = extract_pdf(path, fallback_title=paper.title, on_page=on_page)
    total_chars = sum(len(p) for p in pdf.pages)
    paper.page_count = len(pdf.pages)
    if pdf.title and (paper.title == Path(paper.filename).stem or not paper.title):
        paper.title = pdf.title
    if pdf.authors and not paper.authors:
        paper.authors = pdf.authors
    if pdf.year and not paper.year:
        paper.year = pdf.year
    db.query(Page).filter(Page.paper_id == paper.id).delete()
    db.query(Chunk).filter(Chunk.paper_id == paper.id).delete()
    db.commit()
    if total_chars < 40:
        _set(
            db, paper, "no_text", 100, "No extractable text",
            "This looks like a scanned PDF. ResearchMind does not do OCR yet; try a text-based PDF.",
        )
        return
    for i, text in enumerate(pdf.pages, start=1):
        db.add(Page(paper_id=paper.id, number=i, text=text))
    db.commit()

    _set(db, paper, "chunking", 42, "Splitting into passages", "")
    specs = chunk_document(pdf.pages, cfg.chunk_chars, cfg.chunk_overlap)
    chunks = [Chunk(paper_id=paper.id, page_number=s.page_number, idx=s.idx, text=s.text) for s in specs]
    db.add_all(chunks)
    paper.chunk_count = len(chunks)
    paper.embedded_count = 0
    db.commit()
    VECTOR_CACHE.bump()

    llm = get_llm(db)
    done = 0
    keyword_only_reason = ""
    for start in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[start : start + EMBED_BATCH]
        try:
            vecs = llm.embed([c.text for c in batch])
        except OllamaUnavailable:
            keyword_only_reason = "Ollama was not reachable, so only keyword search is available. Use Reindex once it is running."
            break
        except OllamaError as e:
            keyword_only_reason = f"Embedding failed ({e}). Keyword search works; fix the model and use Reindex."
            break
        for c, v in zip(batch, vecs, strict=True):
            c.embedding, c.embedding_model = to_blob(v), llm.embed_model
        done += len(batch)
        paper.embedded_count = done
        _set(db, paper, "embedding", 50 + int(45 * done / max(len(chunks), 1)), "Building semantic index", f"{done} of {len(chunks)} passages")
    db.commit()
    VECTOR_CACHE.bump()

    if keyword_only_reason:
        _set(db, paper, "ready_keyword_only", 100, "Ready (keyword search only)", keyword_only_reason)
    else:
        _set(db, paper, "ready", 100, "Ready", f"{len(chunks)} passages indexed")

    for name, fn in list(POST_PROCESS):
        try:
            fn(db, paper)
        except Exception:  # noqa: BLE001 - analysis must never break a searchable paper
            log.exception("post-process %s failed for paper %s", name, paper.id)
            db.rollback()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rm-pipeline")
        return _executor


def enqueue(paper_id: int) -> None:
    if get_settings().process_inline:
        process_paper(paper_id)
    else:
        _get_executor().submit(process_paper, paper_id)


def resume_pending() -> int:
    """After a restart, anything that was mid-pipeline is re-queued (its progress is not trustworthy)."""
    db = SessionLocal()
    try:
        ids = [
            p.id
            for p in db.query(Paper).filter(Paper.status.in_(["queued", "extracting", "chunking", "embedding"])).all()
        ]
    finally:
        db.close()
    for pid in ids:
        enqueue(pid)
    return len(ids)


def shutdown() -> None:
    global _executor
    with _lock:
        if _executor:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None
