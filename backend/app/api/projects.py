from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Paper, Project, Thread
from ..security import current_user
from .deps import project_or_404
from .schemas import ProjectIn, ProjectPatch
from .serializers import project_out

router = APIRouter(prefix="/projects", tags=["projects"], dependencies=[Depends(current_user)])


def _counts(db: Session) -> tuple[dict[int, int], dict[int, int]]:
    papers = dict(db.query(Paper.project_id, func.count(Paper.id)).group_by(Paper.project_id).all())
    threads = dict(db.query(Thread.project_id, func.count(Thread.id)).group_by(Thread.project_id).all())
    return papers, threads


@router.get("")
def list_projects(db: Session = Depends(get_db)) -> list[dict]:
    papers, threads = _counts(db)
    rows = db.query(Project).order_by(Project.updated_at.desc()).all()
    return [project_out(p, papers.get(p.id, 0), threads.get(p.id, 0)) for p in rows]


@router.post("", status_code=201)
def create_project(body: ProjectIn, db: Session = Depends(get_db)) -> dict:
    p = Project(name=body.name.strip(), question=body.question.strip())
    db.add(p)
    db.commit()
    return project_out(p)


@router.get("/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)) -> dict:
    p = project_or_404(db, project_id)
    papers, threads = _counts(db)
    return project_out(p, papers.get(p.id, 0), threads.get(p.id, 0))


@router.patch("/{project_id}")
def patch_project(project_id: int, body: ProjectPatch, db: Session = Depends(get_db)) -> dict:
    p = project_or_404(db, project_id)
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(p, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    papers, threads = _counts(db)
    return project_out(p, papers.get(p.id, 0), threads.get(p.id, 0))


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)) -> None:
    from .papers import delete_paper_files

    p = project_or_404(db, project_id)
    for paper in list(p.papers):
        delete_paper_files(db, paper)
    db.delete(p)
    db.commit()
