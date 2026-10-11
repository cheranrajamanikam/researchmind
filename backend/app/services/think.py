"""Think-first features: Prediction Gate, Decision Log conflict alerts, and the Provenance Log.

Design rules shared by all three:
  * Every statement shown to the user carries a paper label, page and a verbatim quote from the stored text.
  * Wording is neutral ("possibly missed", "check this reading"). Nothing is scored, accepted or rejected.
  * The Provenance Log records only what the user marks. It never inspects text for authorship.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any

from sqlalchemy.orm import Session

from ..models import Decision, DecisionAlert, Page, Paper, ProvDocument, ProvEvent, ResultRow, utcnow
from . import settings_store
from .compare import paper_diff, paper_label
from .results import norm_dataset, norm_method, norm_metric
from .text import content_terms, coverage

# ------------------------------------------------------------------ shared helpers

_NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")


def _norm_ws(s: str) -> str:
    return " ".join(s.split()).lower()


def quote_is_verbatim(db: Session, paper_id: int, page: int | None, quote: str) -> bool:
    """True when `quote` is a verbatim slice of the stored text (whitespace-normalised). Used to refuse made-up evidence."""
    needle = _norm_ws(quote)
    if not needle:
        return False
    q = db.query(Page).filter(Page.paper_id == paper_id)
    if page is not None:
        q = q.filter(Page.number == page)
    return any(needle in _norm_ws(p.text) for p in q.all())


def _rel_diff_pct(a: float, b: float) -> float:
    hi = max(abs(a), abs(b))
    return 0.0 if hi == 0 else abs(a - b) / hi * 100


# ------------------------------------------------------------------ Decision Log


def _matches(r: ResultRow, d: Decision) -> bool:
    """A blank decision field acts as a wildcard; filled fields must match after normalisation."""
    if d.method and norm_method(r.method) != norm_method(d.method):
        return False
    if d.dataset and norm_dataset(r.dataset) != norm_dataset(d.dataset):
        return False
    if d.metric and norm_metric(r.metric) != norm_metric(d.metric):
        return False
    return bool(d.method or d.dataset or d.metric)


def check_decisions_for_paper(db: Session, paper: Paper) -> list[DecisionAlert]:
    """After a paper is processed: raise an alert when it reports a different value for something a logged
    decision relied on. The alert is a prompt to re-read, not a statement that the decision was wrong."""
    tol = float(settings_store.get_all(db)["tolerance"])
    decisions = db.query(Decision).filter(Decision.project_id == paper.project_id).all()
    if not decisions:
        return []
    new_rows = db.query(ResultRow).filter(ResultRow.paper_id == paper.id).all()
    if not new_rows:
        return []
    created: list[DecisionAlert] = []
    for d in decisions:
        if db.query(DecisionAlert).filter(DecisionAlert.decision_id == d.id, DecisionAlert.paper_id == paper.id).first():
            continue
        evidence_ids = {e.get("paper_id") for e in (d.evidence or []) if e.get("paper_id")}
        base_q = db.query(ResultRow).join(Paper, Paper.id == ResultRow.paper_id).filter(
            Paper.project_id == paper.project_id, ResultRow.paper_id != paper.id)
        if evidence_ids:
            base_q = base_q.filter(ResultRow.paper_id.in_(evidence_ids))
        baseline = [r for r in base_q.all() if _matches(r, d)]
        best: tuple[float, ResultRow, ResultRow] | None = None
        for n in new_rows:
            if not _matches(n, d):
                continue
            for b in baseline:
                if norm_method(n.method) != norm_method(b.method) or norm_dataset(n.dataset) != norm_dataset(b.dataset) \
                        or norm_metric(n.metric) != norm_metric(b.metric):
                    continue
                rel = _rel_diff_pct(n.value, b.value)
                if rel > tol and (best is None or rel > best[0]):
                    best = (rel, n, b)
        if not best:
            continue
        rel, n, b = best
        base_paper = db.get(Paper, b.paper_id)
        alert = DecisionAlert(
            decision_id=d.id, paper_id=paper.id,
            message=(f"“{paper.title}” reports {n.value:g}{n.unit} for {n.method} · {n.metric} on {n.dataset}, "
                     f"while {paper_label(base_paper) if base_paper else 'an earlier paper'} reports {b.value:g}{b.unit} "
                     f"({rel:.1f}% apart). Re-read both before relying on this decision."),
            quote={"paper_id": paper.id, "label": paper_label(paper), "page": n.page, "quote": n.quote,
                   "value": f"{n.value:g}{n.unit}",
                   "baseline": {"paper_id": b.paper_id, "label": paper_label(base_paper) if base_paper else "",
                                "page": b.page, "quote": b.quote, "value": f"{b.value:g}{b.unit}"}},
        )
        db.add(alert)
        created.append(alert)
    if created:
        db.commit()
    return created


def recheck_decision(db: Session, decision: Decision) -> list[DecisionAlert]:
    """Run the conflict check for one decision across every paper already in the project."""
    out: list[DecisionAlert] = []
    for p in db.query(Paper).filter(Paper.project_id == decision.project_id).all():
        out += [a for a in check_decisions_for_paper(db, p) if a.decision_id == decision.id]
    return out


def decision_out(d: Decision, db: Session) -> dict[str, Any]:
    ev = []
    for e in d.evidence or []:
        p = db.get(Paper, e.get("paper_id")) if e.get("paper_id") else None
        ev.append({**e, "label": paper_label(p) if p else "", "paper_title": p.title if p else ""})
    return {
        "id": d.id, "project_id": d.project_id, "title": d.title, "rationale": d.rationale, "method": d.method,
        "dataset": d.dataset, "metric": d.metric, "evidence": ev, "created_at": d.created_at.isoformat(),
        "alerts": [alert_out(a) for a in sorted(d.alerts, key=lambda a: a.id)],
        "open_alerts": sum(1 for a in d.alerts if not a.resolved),
    }


def alert_out(a: DecisionAlert) -> dict[str, Any]:
    return {"id": a.id, "decision_id": a.decision_id, "paper_id": a.paper_id, "message": a.message, "quote": a.quote,
            "resolved": a.resolved, "created_at": a.created_at.isoformat()}


# ------------------------------------------------------------------ Prediction Gate


def _mentions(prediction: str, value: str) -> bool:
    pv = _norm_ws(value)
    if not pv or pv == "not reported":
        return False
    nums = _NUM.findall(value)
    if nums:
        pred_nums = {float(x) for x in _NUM.findall(prediction)}
        return any(abs(float(x) - y) < 0.051 for x in nums for y in pred_nums)
    return pv in _norm_ws(prediction) or coverage(content_terms(value), prediction) >= 0.6


def _cell_ev(label: str, paper_id: int, c: dict[str, Any]) -> dict[str, Any]:
    return {"paper_id": paper_id, "label": label, "value": c["value"], "page": c["page"], "quote": c["quote"]}


def evaluate_prediction(db: Session, project_id: int, paper_ids: list[int], prediction: str) -> dict[str, Any]:
    """Compare the user's own prediction with what the selected papers report. Returns three neutral buckets."""
    papers = [p for p in (db.get(Paper, i) for i in paper_ids) if p and p.project_id == project_id]
    tol = float(settings_store.get_all(db)["tolerance"])
    matched: list[dict[str, Any]] = []
    missed: list[dict[str, Any]] = []
    check: list[dict[str, Any]] = []
    if not papers:
        return {"matched": [], "possibly_missed": [], "check_reading": [], "papers": [], "note": NOTE_PRED}

    # 1) setup differences between the papers (dataset, split, hardware, seeds, …)
    diff = paper_diff(db, papers)
    for row in diff["rows"]:
        if not row["differs"] or row["field"] in ("Metric value",):
            continue
        evidence = [_cell_ev(p["label"], p["id"], c) for p, c in zip(diff["papers"], row["cells"], strict=True)
                    if c["status"] != "not_reported"]
        values = [e["value"] for e in evidence]
        item = {
            "statement": f"The papers report different values for {row['field'].lower()}: " + " vs ".join(values) + ".",
            "field": row["field"], "evidence": evidence,
        }
        mentioned = _mentions(prediction, row["field"]) and any(_mentions(prediction, v) for v in values) \
            or sum(1 for v in values if _mentions(prediction, v)) >= 2
        (matched if mentioned else missed).append(item)

    # 2) reported results, grouped by (method, dataset, metric)
    rows = db.query(ResultRow).filter(ResultRow.paper_id.in_([p.id for p in papers])).all()
    by_paper = {p.id: p for p in papers}
    groups: dict[tuple[str, str, str], list[ResultRow]] = {}
    for r in rows:
        groups.setdefault((norm_method(r.method), norm_dataset(r.dataset), norm_metric(r.metric)), []).append(r)
    for rs in groups.values():
        ev = [{"paper_id": r.paper_id, "label": paper_label(by_paper[r.paper_id]), "value": f"{r.value:g}{r.unit}",
               "page": r.page, "quote": r.quote} for r in rs]
        distinct_papers = {r.paper_id for r in rs}
        spread = max((_rel_diff_pct(a.value, b.value) for a in rs for b in rs if a.paper_id != b.paper_id), default=0.0)
        head = rs[0]
        label = f"{head.method} · {head.metric} on {head.dataset}"
        hit = any(_mentions(prediction, e["value"]) for e in ev)
        if len(distinct_papers) > 1 and spread > tol:
            item = {"statement": f"Reported values for {label} differ across these papers: "
                                 + " vs ".join(e["value"] for e in ev) + f" ({spread:.1f}% apart).",
                    "field": "Result", "evidence": ev}
            (matched if hit else missed).append(item)
        elif hit:
            matched.append({"statement": f"You mentioned a value that a paper reports for {label}.", "field": "Result",
                            "evidence": [e for e in ev if _mentions(prediction, e["value"])]})

    # 3) numbers in the prediction that no selected paper reports near the metric the sentence mentions
    for sent in re.split(r"(?<=[.!?])\s+", prediction.strip()):
        nums = [float(x) for x in _NUM.findall(sent)]
        if not nums:
            continue
        related = [r for r in rows if coverage(content_terms(f"{r.metric} {r.dataset} {r.method}"), sent) >= 0.34]
        if not related:
            continue
        for n in nums:
            if any(_rel_diff_pct(n, r.value) <= max(tol, 1.0) for r in related):
                continue
            nearest = min(related, key=lambda r: abs(r.value - n))
            check.append({
                "statement": f"You wrote {n:g}; the closest value these papers report is {nearest.value:g}{nearest.unit} "
                             f"for {nearest.method} · {nearest.metric} on {nearest.dataset}. Check this reading.",
                "field": "Result", "your_sentence": sent,
                "evidence": [{"paper_id": nearest.paper_id, "label": paper_label(by_paper[nearest.paper_id]),
                              "value": f"{nearest.value:g}{nearest.unit}", "page": nearest.page, "quote": nearest.quote}],
            })
    return {
        "matched": matched, "possibly_missed": missed, "check_reading": check,
        "papers": [{"id": p.id, "label": paper_label(p), "title": p.title} for p in papers], "note": NOTE_PRED,
    }


NOTE_PRED = ("Analytical estimate, not proof. This compares your wording with values extracted from the selected papers; "
             "it can miss paraphrases. Read the quoted passages and decide for yourself.")


# ------------------------------------------------------------------ Provenance Log


def _words(s: str) -> int:
    return len(s.split())


def clean_marks(content: str, marks: list[dict[str, int]]) -> list[dict[str, Any]]:
    """Keep only marks inside the text, recompute their text from the content, merge overlaps."""
    spans = sorted((max(0, int(m["start"])), min(len(content), int(m["end"]))) for m in marks)
    merged: list[list[int]] = []
    for s, e in spans:
        if e <= s:
            continue
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [{"start": s, "end": e, "text": content[s:e]} for s, e in merged]


def create_document(db: Session, project_id: int, title: str, content: str) -> ProvDocument:
    doc = ProvDocument(project_id=project_id, title=title.strip() or "Untitled notes", content=content, marks=[])
    db.add(doc)
    db.flush()
    db.add(ProvEvent(document_id=doc.id, kind="created", passage="", words=_words(content)))
    db.commit()
    return doc


def update_document(db: Session, doc: ProvDocument, title: str | None, content: str | None,
                    marks: list[dict[str, int]] | None) -> ProvDocument:
    old_marks = {(m["start"], m["end"], m["text"]) for m in (doc.marks or [])}
    if title is not None and title.strip():
        doc.title = title.strip()
    content_changed = content is not None and content != doc.content
    if content_changed:
        delta = _words(content) - _words(doc.content)  # type: ignore[arg-type]
        doc.content = content  # type: ignore[assignment]
        db.add(ProvEvent(document_id=doc.id, kind="edited", passage="", words=abs(delta)))
    new_marks_in = marks if marks is not None else [{"start": m["start"], "end": m["end"]} for m in (doc.marks or [])]
    new_marks = clean_marks(doc.content, new_marks_in)
    new_set = {(m["start"], m["end"], m["text"]) for m in new_marks}
    if marks is not None or content_changed:
        for s, e, t in sorted(new_set - old_marks):
            db.add(ProvEvent(document_id=doc.id, kind="ai_marked", passage=t, words=_words(t)))
        if marks is not None:
            for s, e, t in sorted(old_marks - new_set):
                db.add(ProvEvent(document_id=doc.id, kind="ai_unmarked", passage=t, words=_words(t)))
        doc.marks = new_marks
    doc.updated_at = utcnow()
    db.commit()
    return doc


def document_out(doc: ProvDocument, with_events: bool = False, db: Session | None = None) -> dict[str, Any]:
    total = _words(doc.content)
    marked = sum(_words(m["text"]) for m in (doc.marks or []))
    out: dict[str, Any] = {
        "id": doc.id, "project_id": doc.project_id, "title": doc.title, "content": doc.content, "marks": doc.marks or [],
        "words": total, "marked_words": marked, "updated_at": doc.updated_at.isoformat(),
        "created_at": doc.created_at.isoformat(),
        "note": "This tool records your own marking. It does not detect AI text.",
    }
    if with_events and db is not None:
        out["events"] = [event_out(e) for e in db.query(ProvEvent).filter(ProvEvent.document_id == doc.id)
                         .order_by(ProvEvent.id.desc()).all()]
    return out


def event_out(e: ProvEvent) -> dict[str, Any]:
    return {"id": e.id, "kind": e.kind, "passage": e.passage, "words": e.words, "created_at": e.created_at.isoformat()}


def export_events_csv(db: Session, doc: ProvDocument) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp", "event", "words", "passage"])
    for e in db.query(ProvEvent).filter(ProvEvent.document_id == doc.id).order_by(ProvEvent.id).all():
        w.writerow([e.created_at.isoformat(), e.kind, e.words, e.passage.replace("\n", " ")])
    return buf.getvalue()
