from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Paper
from ..security import current_user
from ..services.grounding import build_citation
from ..services.ollama import LLMClient
from ..services.retrieval import search
from ..services.text import content_terms
from .deps import llm_dep
from .schemas import SearchIn

router = APIRouter(tags=["search"], dependencies=[Depends(current_user)])


@router.post("/search")
def run_search(body: SearchIn, db: Session = Depends(get_db), llm: LLMClient = Depends(llm_dep)) -> dict[str, Any]:
    cfg = get_settings()
    res = search(db, body.query, body.project_id, body.k, "keyword" if body.mode == "keyword" else "semantic", llm)
    papers = {p.id: p for p in db.query(Paper).filter(Paper.id.in_({h.paper_id for h in res.hits})).all()} if res.hits else {}
    terms = res.terms or content_terms(body.query)
    keep = res.hits
    if res.mode == "semantic":
        keep = [h for h in res.hits if h.semantic is not None and h.semantic >= cfg.min_semantic_score * 0.8]
    results = [build_citation(i, h, papers.get(h.paper_id), terms) for i, h in enumerate(keep, start=1)]
    n_papers = db.query(Paper).filter(*( [Paper.project_id == body.project_id] if body.project_id else [] ), Paper.chunk_count > 0).count()
    return {
        "query": body.query,
        "requested_mode": body.mode,
        "mode": res.mode,
        "degraded": res.degraded,
        "total": len(results),
        "papers_searched": n_papers,
        "results": results,
    }
