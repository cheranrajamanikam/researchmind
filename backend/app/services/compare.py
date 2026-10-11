"""Paper Diff and Contradiction finder. Deterministic, quote-backed, and deliberately cautious in wording."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from ..models import ExtractedField, Paper, ResultRow
from .extraction import FIELD_NAMES, norm_value
from .results import norm_dataset, norm_method, norm_metric

DIFF_FIELDS = ["Method", "Dataset", "Split", "Model", "Conditions", "Metric", "Metric value", "Hyperparameters", "Hardware", "Seeds", "Code link"]
SETUP_FIELDS = ["Split", "Model", "Conditions", "Hyperparameters", "Hardware", "Seeds"]

REASONS = {
    "Model": "Different retriever or generator checkpoint",
    "Conditions": "Different retrieval depth or other run condition",
    "Seeds": "Different number of random seeds, so run-to-run variance may differ",
    "Hardware": "Different hardware or runtime",
    "Split": "Different data split or evaluation subset",
    "Hyperparameters": "Different hyperparameters such as learning rate or batch size",
}


def _label(p: Paper) -> str:
    """Short citation-style label, e.g. "Rowan et al. · 2024"."""
    authors = [a.strip() for a in re.split(r",|;| and ", p.authors or "") if a.strip()]
    year = p.year or "n.d."
    if not authors:
        return f"{' '.join(p.title.split()[:3])} · {year}"
    surname = authors[0].split()[-1]
    return f"{surname} et al. · {year}" if len(authors) > 1 else f"{surname} · {year}"


def paper_label(p: Paper) -> str:
    return _label(p)


def _field_map(db: Session, paper_id: int) -> dict[str, ExtractedField]:
    return {f.name: f for f in db.query(ExtractedField).filter(ExtractedField.paper_id == paper_id).all()}


def _cell(f: ExtractedField | None) -> dict[str, Any]:
    if not f or f.status in ("not_reported", "rejected") or not f.value:
        return {"value": "Not reported", "quote": "", "page": None, "status": "not_reported", "field_id": f.id if f else None}
    return {"value": f.value, "quote": f.quote, "page": f.page, "status": f.status, "field_id": f.id}


def paper_diff(db: Session, papers: list[Paper]) -> dict[str, Any]:
    maps = {p.id: _field_map(db, p.id) for p in papers}
    rows: list[dict[str, Any]] = []
    for name in DIFF_FIELDS:
        cells = [_cell(maps[p.id].get(name)) for p in papers]
        present = {norm_value(c["value"]) for c in cells if c["status"] != "not_reported"}
        missing = [c["status"] == "not_reported" for c in cells]
        rows.append({
            "field": name,
            "cells": cells,
            "differs": len(present) > 1,
            "has_missing": any(missing) and not all(missing),
        })
    return {
        "papers": [{"id": p.id, "title": p.title, "label": paper_label(p), "year": p.year} for p in papers],
        "rows": rows,
        "note": "Highlighting marks a difference between reported values. It does not indicate which paper is better.",
    }


def _conflict_key(r: ResultRow) -> tuple[str, str, str]:
    return norm_method(r.method), norm_dataset(r.dataset), norm_metric(r.metric)


def find_conflicts(db: Session, project_id: int, tolerance_pct: float) -> list[dict[str, Any]]:
    papers = {p.id: p for p in db.query(Paper).filter(Paper.project_id == project_id).all()}
    if not papers:
        return []
    rows = db.query(ResultRow).filter(ResultRow.paper_id.in_(list(papers))).all()
    groups: dict[tuple[str, str, str], list[ResultRow]] = {}
    for r in rows:
        groups.setdefault(_conflict_key(r), []).append(r)
    maps: dict[int, dict[str, ExtractedField]] = {}
    out: list[dict[str, Any]] = []
    for key, rs in groups.items():
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = rs[i], rs[j]
                if a.paper_id == b.paper_id:
                    continue
                hi = max(abs(a.value), abs(b.value))
                if hi == 0:
                    continue
                rel = abs(a.value - b.value) / hi * 100
                if rel <= tolerance_pct:
                    continue
                for pid in (a.paper_id, b.paper_id):
                    maps.setdefault(pid, _field_map(db, pid))
                diffs = []
                for name in SETUP_FIELDS:
                    ca, cb = _cell(maps[a.paper_id].get(name)), _cell(maps[b.paper_id].get(name))
                    if norm_value(ca["value"]) != norm_value(cb["value"]):
                        diffs.append({"field": name, "a": ca["value"], "b": cb["value"],
                                      "a_page": ca["page"], "b_page": cb["page"]})
                reasons = [REASONS[d["field"]] for d in diffs if d["field"] in REASONS]
                out.append({
                    "key": {"method": a.method, "dataset": a.dataset, "metric": a.metric},
                    "title": f"{a.dataset} · {a.metric}",
                    "relative_difference_pct": round(rel, 1),
                    "a": _side(a, papers[a.paper_id]),
                    "b": _side(b, papers[b.paper_id]),
                    "setup_differences": diffs,
                    "possible_reasons": reasons or ["No setup difference was extracted for either paper; check the full papers."],
                    "candidate_experiment": candidate_experiment(a, diffs),
                })
    out.sort(key=lambda c: -c["relative_difference_pct"])
    for n, c in enumerate(out, start=1):
        c["n"] = n
    return out


def _side(r: ResultRow, p: Paper) -> dict[str, Any]:
    return {
        "paper_id": p.id, "paper_title": p.title, "label": paper_label(p), "value": r.value, "unit": r.unit,
        "display": f"{r.value:g}{r.unit}", "quote": r.quote, "page": r.page, "method": r.method,
    }


def candidate_experiment(r: ResultRow, diffs: list[dict[str, Any]]) -> str:
    fields = [d["field"].lower() for d in diffs]
    what = ", ".join(fields) if fields else "every reported setting"
    return (
        f"Run {r.method} on {r.dataset} under one frozen configuration, changing one of ({what}) at a time, "
        f"and report {r.metric} as mean ± standard deviation over at least five seeds."
    )
