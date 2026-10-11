"""Analysis endpoints: extraction review, Paper Diff, contradictions, integrity checks, discovery, reading list,
prior-work audit, gap map, evaluation, and the think-first features. All are project-scoped and need sign-in."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Chunk, Decision, DecisionAlert, EvalQuestion, EvalRun, ExtractedField, Page, Paper, Prediction, ProvDocument,
    ReadingItem, SearchReceipt, Thread, utcnow,
)
from ..security import current_user
from ..services import compare, discovery, evaluation, extraction, gaps, integrity, settings_store, think
from ..services.ollama import LLMClient
from .deps import llm_dep, paper_or_404, project_or_404
from .schemas import (
    DecisionIn, DecisionPatch, DiffIn, DiscoverIn, DraftAuditIn, EvalRunIn, FieldAction, OverclaimIn, PredictionIn,
    PriorWorkIn, ProvDocIn, ProvDocPatch, ReadingIn, ReadingPatch, ReflectionIn,
)
from .serializers import job_state, paper_out

router = APIRouter(tags=["analysis"], dependencies=[Depends(current_user)])

DISCLAIMER = "Analytical estimate, not proof."


# ------------------------------------------------------------------ overview (dashboard)


@router.get("/projects/{project_id}/overview")
def overview(project_id: int, db: Session = Depends(get_db), llm: LLMClient = Depends(llm_dep)) -> dict[str, Any]:
    project = project_or_404(db, project_id)
    cfg = settings_store.get_all(db)
    papers = db.query(Paper).filter(Paper.project_id == project_id).order_by(Paper.created_at.desc()).all()
    ids = [p.id for p in papers]
    pages = db.query(func.count(Page.id)).filter(Page.paper_id.in_(ids)).scalar() if ids else 0
    fields = db.query(ExtractedField).filter(ExtractedField.paper_id.in_(ids)).all() if ids else []
    by_status: dict[str, int] = {}
    for f in fields:
        by_status[f.status] = by_status.get(f.status, 0) + 1
    extracted = [f for f in fields if f.status != "not_reported"]
    chunks = db.query(func.count(Chunk.id)).filter(Chunk.paper_id.in_(ids)).scalar() if ids else 0
    embedded = db.query(func.count(Chunk.id)).filter(Chunk.paper_id.in_(ids), Chunk.embedding.isnot(None)).scalar() if ids else 0
    conflicts = compare.find_conflicts(db, project_id, float(cfg["tolerance"]))
    reading = db.query(ReadingItem).filter(ReadingItem.project_id == project_id).order_by(ReadingItem.id.desc()).limit(5).all()
    alerts = (db.query(DecisionAlert).join(Decision, Decision.id == DecisionAlert.decision_id)
              .filter(Decision.project_id == project_id, DecisionAlert.resolved.is_(False))
              .order_by(DecisionAlert.id.desc()).limit(5).all())
    last_run = db.query(EvalRun).filter(EvalRun.project_id == project_id).order_by(EvalRun.id.desc()).limit(8).all()
    recent_thread = db.query(Thread).filter(Thread.project_id == project_id).order_by(Thread.updated_at.desc()).first()
    gap = gaps.build_gap_map(db, project_id, None) if papers else {"clusters": []}
    return {
        "project": {"id": project.id, "name": project.name, "question": project.question, "think_first": project.think_first},
        "stats": {
            "papers": len(papers), "pages": pages or 0, "fields_extracted": len(extracted),
            "awaiting_review": by_status.get("verify", 0),
        },
        "index": {"chunks": chunks or 0, "embedded": embedded or 0},
        "extraction_health": {
            "agree": by_status.get("agree", 0), "verify": by_status.get("verify", 0),
            "confirmed": by_status.get("confirmed", 0) + by_status.get("edited", 0),
            "not_reported": by_status.get("not_reported", 0),
        },
        "jobs": [{**paper_out(p), "title": p.title if job_state(p.status) != "queued" else p.filename}
                 for p in papers if job_state(p.status) in ("queued", "running", "failed")][:6],
        "recent_papers": [paper_out(p) for p in papers[:4]],
        "recent_thread": {"id": recent_thread.id, "title": recent_thread.title, "updated_at": recent_thread.updated_at.isoformat()}
        if recent_thread else None,
        "alerts": [think.alert_out(a) | {"decision_title": a.decision.title} for a in alerts],
        "contradictions": conflicts[:3],
        "contradiction_total": len(conflicts),
        "reading": [_reading_out(r) for r in reading],
        "evaluation": [{"id": r.id, "created_at": r.created_at.isoformat(), "metrics": r.metrics} for r in reversed(last_run)],
        "gaps": [{"n": c["n"], "label": c["label"], "paper_count": c["paper_count"], "statement_count": c["statement_count"]}
                 for c in gap.get("clusters", [])[:3]],
        "privacy": {"online_discovery": cfg["online_discovery"], "answer_model": cfg["answer_model"], "embed_model": cfg["embed_model"]},
    }


# ------------------------------------------------------------------ extraction review


def _field_or_404(db: Session, field_id: int) -> ExtractedField:
    f = db.get(ExtractedField, field_id)
    if not f:
        raise HTTPException(404, "Field not found")
    return f


@router.get("/papers/{paper_id}/fields")
def paper_fields(paper_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return extraction.paper_fields_out(db, paper_or_404(db, paper_id))


@router.post("/papers/{paper_id}/extract")
def rerun_extraction(paper_id: int, db: Session = Depends(get_db), llm: LLMClient = Depends(llm_dep)) -> dict[str, Any]:
    paper = paper_or_404(db, paper_id)
    info = extraction.run_for_paper(db, paper, llm)
    think.check_decisions_for_paper(db, paper)
    return {**info, **extraction.paper_fields_out(db, paper)}


@router.get("/projects/{project_id}/extraction")
def project_extraction(project_id: int, only: str | None = Query(default=None, pattern="^(verify)$"),
                       db: Session = Depends(get_db)) -> dict[str, Any]:
    """Every paper's fields in one payload for the Extraction Review screen."""
    project_or_404(db, project_id)
    out = []
    for p in db.query(Paper).filter(Paper.project_id == project_id).order_by(Paper.id).all():
        data = extraction.paper_fields_out(db, p)
        if only == "verify":
            data["fields"] = [f for f in data["fields"] if f["status"] == "verify"]
        out.append({"paper": {"id": p.id, "title": p.title, "label": compare.paper_label(p), "status": p.status}, **data})
    return {"papers": out, "disclaimer": DISCLAIMER}


@router.patch("/fields/{field_id}")
def review_field(field_id: int, body: FieldAction, db: Session = Depends(get_db)) -> dict[str, Any]:
    f = _field_or_404(db, field_id)
    if body.action == "confirm":
        if not f.value:
            raise HTTPException(422, "There is no value to confirm. Edit it first or reject it.")
        f.status = "confirmed"
    elif body.action == "reject":
        f.status = "rejected"
    elif body.action == "edit":
        if not (body.value and body.value.strip()):
            raise HTTPException(422, "Enter the corrected value.")
        f.value, f.status = body.value.strip(), "edited"
    else:  # reset: return to the automatic result
        f.status = "verify"
    f.updated_at = utcnow()
    db.commit()
    paper = db.get(Paper, f.paper_id)
    return extraction.paper_fields_out(db, paper)  # type: ignore[arg-type]


# ------------------------------------------------------------------ diff + contradictions


@router.post("/projects/{project_id}/diff")
def diff(project_id: int, body: DiffIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    project_or_404(db, project_id)
    papers = [p for p in (db.get(Paper, i) for i in dict.fromkeys(body.paper_ids)) if p and p.project_id == project_id]
    if len(papers) < 2:
        raise HTTPException(422, "Choose at least two papers from this project.")
    return {**compare.paper_diff(db, papers), "disclaimer": DISCLAIMER}


@router.get("/projects/{project_id}/contradictions")
def contradictions(project_id: int, tolerance: float | None = Query(default=None, ge=0, le=50),
                   db: Session = Depends(get_db)) -> dict[str, Any]:
    project_or_404(db, project_id)
    tol = tolerance if tolerance is not None else float(settings_store.get_all(db)["tolerance"])
    items = compare.find_conflicts(db, project_id, tol)
    return {
        "tolerance": tol, "items": items, "disclaimer": DISCLAIMER,
        "note": "Pairs where method, dataset and metric match but the reported values differ beyond the tolerance. "
                "Reasons listed are possibilities, not conclusions.",
    }


# ------------------------------------------------------------------ writing-integrity checks


@router.get("/papers/{paper_id}/numeric")
def numeric(paper_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {**integrity.numeric_consistency(db, paper_or_404(db, paper_id)), "disclaimer": DISCLAIMER}


@router.get("/papers/{paper_id}/reproducibility")
def repro(paper_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {**integrity.reproducibility(db, paper_or_404(db, paper_id)), "disclaimer": DISCLAIMER}


@router.post("/projects/{project_id}/overclaim")
def overclaim(project_id: int, body: OverclaimIn, db: Session = Depends(get_db), llm: LLMClient = Depends(llm_dep)) -> dict[str, Any]:
    project_or_404(db, project_id)
    return {**integrity.overclaim_review(db, project_id, body.text, llm), "disclaimer": DISCLAIMER}


@router.get("/projects/{project_id}/citation-audit")
def citation_audit(project_id: int, db: Session = Depends(get_db), llm: LLMClient = Depends(llm_dep)) -> dict[str, Any]:
    project_or_404(db, project_id)
    return {"items": integrity.library_citation_audit(db, project_id, llm), "disclaimer": DISCLAIMER,
            "note": "Evidence side by side. No verdict is given on whether the citation is right."}


@router.post("/projects/{project_id}/citation-audit")
def draft_audit(project_id: int, body: DraftAuditIn, db: Session = Depends(get_db), llm: LLMClient = Depends(llm_dep)) -> dict[str, Any]:
    project_or_404(db, project_id)
    return {"items": integrity.draft_citation_audit(db, project_id, body.text, body.mapping, llm), "disclaimer": DISCLAIMER,
            "note": "Evidence side by side. No verdict is given on whether the citation is right."}


# ------------------------------------------------------------------ discovery, receipts, reading list, prior work


def _online(db: Session) -> bool:
    return bool(settings_store.get_all(db)["online_discovery"])


@router.post("/projects/{project_id}/discover")
def discover(project_id: int, body: DiscoverIn, db: Session = Depends(get_db), llm: LLMClient = Depends(llm_dep)) -> dict[str, Any]:
    """Only short search queries ever leave the machine, and only when Online discovery is switched on in Settings."""
    project_or_404(db, project_id)
    return {**discovery.run_discovery(db, project_id, body.text, body.queries, _online(db), llm), "disclaimer": DISCLAIMER}


@router.post("/projects/{project_id}/prior-work")
def prior_work(project_id: int, body: PriorWorkIn, db: Session = Depends(get_db), llm: LLMClient = Depends(llm_dep)) -> dict[str, Any]:
    project_or_404(db, project_id)
    return {**discovery.prior_work(db, project_id, body.idea, _online(db), llm), "disclaimer": DISCLAIMER}


@router.get("/projects/{project_id}/receipts")
def receipts(project_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    project_or_404(db, project_id)
    rows = db.query(SearchReceipt).filter(SearchReceipt.project_id == project_id).order_by(SearchReceipt.id.desc()).limit(50).all()
    return [{**discovery.receipt_out(r), "results": r.results[:0]} | {"result_count": len(r.results)} for r in rows]


@router.get("/receipts/{receipt_id}")
def receipt(receipt_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    r = db.get(SearchReceipt, receipt_id)
    if not r:
        raise HTTPException(404, "Receipt not found")
    return discovery.receipt_out(r)


def _reading_out(r: ReadingItem) -> dict[str, Any]:
    return {"id": r.id, "project_id": r.project_id, "title": r.title, "authors": r.authors, "year": r.year, "venue": r.venue,
            "url": r.url, "why": r.why, "tags": r.tags or [], "status": r.status, "note": r.note, "paper_id": r.paper_id,
            "created_at": r.created_at.isoformat()}


@router.get("/projects/{project_id}/reading")
def reading_list(project_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    project_or_404(db, project_id)
    return [_reading_out(r) for r in db.query(ReadingItem).filter(ReadingItem.project_id == project_id).order_by(ReadingItem.id.desc()).all()]


@router.post("/projects/{project_id}/reading", status_code=201)
def add_reading(project_id: int, body: ReadingIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    project_or_404(db, project_id)
    dup = db.query(ReadingItem).filter(ReadingItem.project_id == project_id,
                                       func.lower(ReadingItem.title) == body.title.strip().lower()).first()
    if dup:
        return _reading_out(dup)  # saving twice is harmless
    item = ReadingItem(project_id=project_id, **{**body.model_dump(), "title": body.title.strip()})
    db.add(item)
    db.commit()
    return _reading_out(item)


@router.patch("/reading/{item_id}")
def patch_reading(item_id: int, body: ReadingPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.get(ReadingItem, item_id)
    if not item:
        raise HTTPException(404, "Reading list item not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(item, k, v)
    db.commit()
    return _reading_out(item)


@router.delete("/reading/{item_id}", status_code=204)
def delete_reading(item_id: int, db: Session = Depends(get_db)) -> None:
    item = db.get(ReadingItem, item_id)
    if not item:
        raise HTTPException(404, "Reading list item not found")
    db.delete(item)
    db.commit()


# ------------------------------------------------------------------ gap map


@router.get("/projects/{project_id}/gaps")
def gap_map(project_id: int, threshold: float | None = Query(default=None, ge=0.05, le=0.95),
            db: Session = Depends(get_db), llm: LLMClient = Depends(llm_dep)) -> dict[str, Any]:
    project_or_404(db, project_id)
    return {**gaps.build_gap_map(db, project_id, llm, threshold), "disclaimer": DISCLAIMER,
            "label": "Candidate gaps for you to evaluate"}


# ------------------------------------------------------------------ evaluation


@router.post("/projects/{project_id}/eval/samples")
def load_samples(project_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    project_or_404(db, project_id)
    n = evaluation.load_sample_suite(db, project_id)
    if n == 0:
        raise HTTPException(409, "None of the bundled sample papers are in this project. Create them with `python -m eval.samples ./sample_papers` (run inside backend/) and upload those four PDFs.")
    return {"questions": n}


@router.get("/projects/{project_id}/eval/questions")
def eval_questions(project_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    project_or_404(db, project_id)
    n = db.query(func.count(EvalQuestion.id)).filter(EvalQuestion.project_id == project_id).scalar()
    return {"count": n or 0}


@router.post("/projects/{project_id}/eval/run")
def run_evaluation(project_id: int, body: EvalRunIn, db: Session = Depends(get_db), llm: LLMClient = Depends(llm_dep)) -> dict[str, Any]:
    project_or_404(db, project_id)
    if not db.query(EvalQuestion).filter(EvalQuestion.project_id == project_id).count():
        raise HTTPException(409, "This project has no evaluation questions yet. Load the sample suite or add your own gold set.")
    return evaluation.run_out(evaluation.run_eval(db, project_id, llm, body.k, body.use_judge))


@router.get("/projects/{project_id}/eval/runs")
def eval_runs(project_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    project_or_404(db, project_id)
    return [evaluation.run_out(r, with_details=False)
            for r in db.query(EvalRun).filter(EvalRun.project_id == project_id).order_by(EvalRun.id.desc()).limit(30).all()]


@router.get("/eval/runs/{run_id}")
def eval_run(run_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    r = db.get(EvalRun, run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    return evaluation.run_out(r)


@router.get("/eval/runs/{run_id}/report.md", response_class=PlainTextResponse)
def eval_report(run_id: int, db: Session = Depends(get_db)) -> str:
    r = db.get(EvalRun, run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    return evaluation.to_markdown(evaluation.run_out(r))


# ------------------------------------------------------------------ decision log


def _decision_or_404(db: Session, decision_id: int) -> Decision:
    d = db.get(Decision, decision_id)
    if not d:
        raise HTTPException(404, "Decision not found")
    return d


def _validated_evidence(db: Session, project_id: int, body: DecisionIn) -> list[dict[str, Any]]:
    out = []
    for e in body.evidence:
        paper = db.get(Paper, e.paper_id)
        if not paper or paper.project_id != project_id:
            raise HTTPException(422, f"Paper {e.paper_id} is not in this project.")
        if not think.quote_is_verbatim(db, e.paper_id, e.page, e.quote):
            raise HTTPException(422, "A linked quote was not found on that page of the paper. Evidence must be copied from the paper text.")
        out.append(e.model_dump())
    return out


@router.get("/projects/{project_id}/decisions")
def list_decisions(project_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    project_or_404(db, project_id)
    return [think.decision_out(d, db) for d in db.query(Decision).filter(Decision.project_id == project_id).order_by(Decision.id.desc()).all()]


@router.post("/projects/{project_id}/decisions", status_code=201)
def add_decision(project_id: int, body: DecisionIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    project_or_404(db, project_id)
    d = Decision(project_id=project_id, title=body.title.strip(), rationale=body.rationale.strip(), method=body.method.strip(),
                 dataset=body.dataset.strip(), metric=body.metric.strip(), evidence=_validated_evidence(db, project_id, body))
    db.add(d)
    db.commit()
    think.recheck_decision(db, d)
    db.refresh(d)
    return think.decision_out(d, db)


@router.patch("/decisions/{decision_id}")
def patch_decision(decision_id: int, body: DecisionPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    d = _decision_or_404(db, decision_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(d, k, v.strip())
    db.commit()
    think.recheck_decision(db, d)
    db.refresh(d)
    return think.decision_out(d, db)


@router.delete("/decisions/{decision_id}", status_code=204)
def delete_decision(decision_id: int, db: Session = Depends(get_db)) -> None:
    db.delete(_decision_or_404(db, decision_id))
    db.commit()


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    a = db.get(DecisionAlert, alert_id)
    if not a:
        raise HTTPException(404, "Alert not found")
    a.resolved = True
    db.commit()
    return think.alert_out(a)


# ------------------------------------------------------------------ prediction gate


@router.post("/projects/{project_id}/predictions", status_code=201)
def make_prediction(project_id: int, body: PredictionIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    project_or_404(db, project_id)
    result = think.evaluate_prediction(db, project_id, body.paper_ids, body.prediction)
    if not result["papers"]:
        raise HTTPException(422, "Choose papers from this project.")
    row = Prediction(project_id=project_id, paper_ids=[p["id"] for p in result["papers"]], prediction=body.prediction.strip(), result=result)
    db.add(row)
    db.commit()
    return {"id": row.id, "created_at": row.created_at.isoformat(), "prediction": row.prediction, **result}


@router.get("/projects/{project_id}/predictions")
def list_predictions(project_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    project_or_404(db, project_id)
    rows = db.query(Prediction).filter(Prediction.project_id == project_id).order_by(Prediction.id.desc()).limit(30).all()
    return [{"id": r.id, "created_at": r.created_at.isoformat(), "prediction": r.prediction, "paper_ids": r.paper_ids,
             "counts": {k: len(r.result.get(k, [])) for k in ("matched", "possibly_missed", "check_reading")}} for r in rows]


@router.patch("/predictions/{prediction_id}")
def save_reflection(prediction_id: int, body: ReflectionIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    r = db.get(Prediction, prediction_id)
    if not r:
        raise HTTPException(404, "Prediction not found")
    r.reflection = body.reflection.strip()
    db.commit()
    return {"id": r.id, "reflection": r.reflection}


@router.get("/predictions/{prediction_id}")
def get_prediction(prediction_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    r = db.get(Prediction, prediction_id)
    if not r:
        raise HTTPException(404, "Prediction not found")
    return {"id": r.id, "created_at": r.created_at.isoformat(), "prediction": r.prediction, "reflection": r.reflection, **r.result}


# ------------------------------------------------------------------ provenance log


def _doc_or_404(db: Session, doc_id: int) -> ProvDocument:
    d = db.get(ProvDocument, doc_id)
    if not d:
        raise HTTPException(404, "Document not found")
    return d


@router.get("/projects/{project_id}/provenance")
def list_docs(project_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    project_or_404(db, project_id)
    docs = db.query(ProvDocument).filter(ProvDocument.project_id == project_id).order_by(ProvDocument.updated_at.desc()).all()
    return [think.document_out(d) | {"content": "", "marks": []} for d in docs]


@router.post("/projects/{project_id}/provenance", status_code=201)
def create_doc(project_id: int, body: ProvDocIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    project_or_404(db, project_id)
    return think.document_out(think.create_document(db, project_id, body.title, body.content), True, db)


@router.get("/provenance/{doc_id}")
def get_doc(doc_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return think.document_out(_doc_or_404(db, doc_id), True, db)


@router.patch("/provenance/{doc_id}")
def patch_doc(doc_id: int, body: ProvDocPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    doc = _doc_or_404(db, doc_id)
    marks = [m.model_dump() for m in body.marks] if body.marks is not None else None
    think.update_document(db, doc, body.title, body.content, marks)
    return think.document_out(doc, True, db)


@router.delete("/provenance/{doc_id}", status_code=204)
def delete_doc(doc_id: int, db: Session = Depends(get_db)) -> None:
    db.delete(_doc_or_404(db, doc_id))
    db.commit()


@router.get("/provenance/{doc_id}/export.csv", response_class=PlainTextResponse)
def export_csv(doc_id: int, db: Session = Depends(get_db)) -> PlainTextResponse:
    doc = _doc_or_404(db, doc_id)
    return PlainTextResponse(think.export_events_csv(db, doc), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="provenance-{doc.id}.csv"'})


@router.get("/provenance/{doc_id}/export.json")
def export_json(doc_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return think.document_out(_doc_or_404(db, doc_id), True, db)
