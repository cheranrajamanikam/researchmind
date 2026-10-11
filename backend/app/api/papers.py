"""Paper upload, listing, viewer data, retry/reindex and deletion."""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Chunk, Page, Paper
from ..security import current_user
from ..services import pipeline
from ..services.retrieval import VECTOR_CACHE
from .deps import paper_or_404, project_or_404
from .serializers import job_state, paper_out

log = logging.getLogger("researchmind.papers")
router = APIRouter(tags=["papers"], dependencies=[Depends(current_user)])


def delete_paper_files(db: Session, paper: Paper) -> None:
    """Remove a paper's stored file and every row derived from it (keeps the FTS index in sync)."""
    from ..models import ExtractedField, ResultRow

    db.query(ExtractedField).filter(ExtractedField.paper_id == paper.id).delete()
    db.query(ResultRow).filter(ResultRow.paper_id == paper.id).delete()
    db.query(Chunk).filter(Chunk.paper_id == paper.id).delete()  # fires FTS delete triggers
    db.query(Page).filter(Page.paper_id == paper.id).delete()
    try:
        Path(paper.file_path).unlink(missing_ok=True)
    except OSError:
        log.warning("could not remove file %s", paper.file_path)
    db.delete(paper)
    db.flush()
    VECTOR_CACHE.bump()


@router.post("/projects/{project_id}/papers", status_code=201)
async def upload_papers(project_id: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db)) -> dict:
    cfg = get_settings()
    project_or_404(db, project_id)
    created: list[dict] = []
    rejected: list[dict] = []
    limit = cfg.max_upload_mb * 1024 * 1024
    for f in files:
        name = Path(f.filename or "paper.pdf").name
        if not name.lower().endswith(".pdf"):
            rejected.append({"filename": name, "reason": "Only PDF files are supported."})
            continue
        dest = cfg.papers_dir / f"{uuid.uuid4().hex}.pdf"
        size = 0
        head = b""
        too_big = False
        with dest.open("wb") as out:
            while chunk := await f.read(1 << 20):
                if not head:
                    head = chunk[:5]
                size += len(chunk)
                if size > limit:
                    too_big = True
                    break
                out.write(chunk)
        if too_big or head != b"%PDF-" or size == 0:
            dest.unlink(missing_ok=True)
            reason = f"Larger than {cfg.max_upload_mb} MB." if too_big else "This file is not a valid PDF."
            rejected.append({"filename": name, "reason": reason})
            continue
        digest = pipeline.sha256_file(dest)
        existing = db.query(Paper).filter(Paper.project_id == project_id, Paper.sha256 == digest).first()
        if existing:
            dest.unlink(missing_ok=True)
            rejected.append({"filename": name, "reason": f"Already in this project as “{existing.title}”.", "paper_id": existing.id})
            continue
        paper = Paper(
            project_id=project_id, title=Path(name).stem, filename=name, file_path=str(dest), sha256=digest,
            status="queued", stage="Waiting for a processing slot",
        )
        db.add(paper)
        db.commit()
        created.append(paper_out(paper))
        pipeline.enqueue(paper.id)
    db.expire_all()
    created = [paper_out(db.get(Paper, c["id"])) for c in created]  # reflect inline processing results
    return {"papers": created, "rejected": rejected}


@router.get("/papers")
def list_papers(project_id: int | None = None, status: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    q = db.query(Paper)
    if project_id:
        q = q.filter(Paper.project_id == project_id)
    if status:
        q = q.filter(Paper.status == status)
    return [paper_out(p) for p in q.order_by(Paper.created_at.desc()).all()]


@router.get("/jobs")
def list_jobs(project_id: int | None = None, db: Session = Depends(get_db)) -> list[dict]:
    """Papers that are queued, running, or recently finished/failed: drives every progress widget."""
    q = db.query(Paper)
    if project_id:
        q = q.filter(Paper.project_id == project_id)
    rows = q.order_by(Paper.created_at.desc()).limit(40).all()
    return [
        {**paper_out(p), "title": p.title if job_state(p.status) != "queued" else p.filename}
        for p in rows
    ]


@router.get("/papers/{paper_id}")
def get_paper(paper_id: int, db: Session = Depends(get_db)) -> dict:
    return paper_out(paper_or_404(db, paper_id))


@router.get("/papers/{paper_id}/pages")
def get_pages(paper_id: int, db: Session = Depends(get_db)) -> list[dict]:
    paper_or_404(db, paper_id)
    return [
        {"number": p.number, "text": p.text}
        for p in db.query(Page).filter(Page.paper_id == paper_id).order_by(Page.number).all()
    ]


@router.get("/papers/{paper_id}/file")
def get_file(paper_id: int, db: Session = Depends(get_db)) -> FileResponse:
    paper = paper_or_404(db, paper_id)
    path = Path(paper.file_path)
    if not path.exists():
        raise HTTPException(404, "The stored PDF file is missing from disk.")
    return FileResponse(path, media_type="application/pdf", filename=paper.filename, content_disposition_type="inline")


@router.post("/papers/{paper_id}/retry")
def retry(paper_id: int, db: Session = Depends(get_db)) -> dict:
    paper = paper_or_404(db, paper_id)
    paper.status, paper.progress, paper.stage, paper.error, paper.detail = "queued", 0, "Waiting for a processing slot", "", ""
    db.commit()
    pipeline.enqueue(paper.id)
    db.expire_all()
    return paper_out(db.get(Paper, paper_id))


@router.post("/papers/{paper_id}/reindex")
def reindex(paper_id: int, db: Session = Depends(get_db)) -> dict:
    """Re-run the pipeline (e.g. after Ollama was offline during upload)."""
    return retry(paper_id, db)


@router.delete("/papers/{paper_id}", status_code=204)
def delete_paper(paper_id: int, db: Session = Depends(get_db)) -> None:
    paper = paper_or_404(db, paper_id)
    delete_paper_files(db, paper)
    db.commit()
