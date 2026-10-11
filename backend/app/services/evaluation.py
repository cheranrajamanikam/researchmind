"""Evaluation harness: retrieval recall@k / MRR, citation faithfulness, refusal accuracy, extraction accuracy.

Everything here measures the real pipeline (retrieval + grounded answering), not a mock. Results are stored as
EvalRun rows so the UI can show history.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..models import EvalQuestion, EvalRun, ExtractedField, Page, Paper
from .grounding import answer_question
from .ollama import LLMClient, OllamaError, OllamaUnavailable, parse_json_object
from .retrieval import search
from .text import content_terms, coverage, tokens

EVAL_DIR = Path(__file__).resolve().parents[2] / "eval"
FAITHFUL_COVERAGE = 0.34


def load_sample_suite(db: Session, project_id: int) -> int:
    """Replace the project's gold questions with the bundled suite, mapped onto papers by title."""
    spec = json.loads((EVAL_DIR / "gold_samples.json").read_text())
    papers = db.query(Paper).filter(Paper.project_id == project_id).all()
    db.query(EvalQuestion).filter(EvalQuestion.project_id == project_id).delete()
    added = 0
    for q in spec["questions"]:
        pid = None
        if q.get("paper_title_contains"):
            pid = next((p.id for p in papers if q["paper_title_contains"].lower() in p.title.lower()), None)
            if pid is None:
                continue  # that sample paper is not in this project
        db.add(EvalQuestion(
            project_id=project_id, question=q["question"], answerable=q["answerable"], expected_paper_id=pid,
            expected_page=q.get("expected_page"), expected_snippet=q.get("expected_snippet", ""),
        ))
        added += 1
    db.commit()
    return added


def _norm(s: str) -> str:
    return " ".join(s.split()).lower()


def _page_text(db: Session, cache: dict[tuple[int, int], str], paper_id: int, page: int) -> str:
    key = (paper_id, page)
    if key not in cache:
        row = db.query(Page).filter(Page.paper_id == paper_id, Page.number == page).first()
        cache[key] = row.text if row else ""
    return cache[key]


def judge_supports(llm: LLMClient, question: str, quote: str) -> bool | None:
    try:
        raw = llm.chat_json(
            "Decide whether the excerpt contains information that helps answer the question. Return JSON {\"supports\": true|false}.",
            f"Question: {question}\n\nExcerpt: {quote}", {"type": "object", "properties": {"supports": {"type": "boolean"}}, "required": ["supports"]},
        )
    except (OllamaUnavailable, OllamaError):
        return None
    obj = parse_json_object(raw) or {}
    v = obj.get("supports")
    return v if isinstance(v, bool) else None


def run_eval(db: Session, project_id: int, llm: LLMClient | None, k: int = 10, use_judge: bool = False) -> EvalRun:
    questions = db.query(EvalQuestion).filter(EvalQuestion.project_id == project_id).order_by(EvalQuestion.id).all()
    page_cache: dict[tuple[int, int], str] = {}
    details: list[dict[str, Any]] = []
    rr: list[float] = []
    recall_hits = 0
    answerable_n = unanswerable_n = refused_correct = false_refusals = 0
    cites_total = cites_ok = 0
    retrieval_modes: set[str] = set()
    answer_modes: set[str] = set()
    judged_total = judged_yes = 0
    for q in questions:
        res = search(db, q.question, project_id, k, "hybrid", llm)
        retrieval_modes.add(res.mode)
        rank = None
        if q.answerable and q.expected_snippet:
            snippet = _norm(q.expected_snippet)
            for i, h in enumerate(res.hits, start=1):
                if (q.expected_paper_id is None or h.paper_id == q.expected_paper_id) and snippet in _norm(h.text):
                    rank = i
                    break
        ans = answer_question(db, q.question, project_id, llm)
        answer_modes.add("llm" if ans.status == "answered" else ans.status)
        refused = ans.status == "insufficient"
        valid = supported = 0
        for c in ans.citations:
            verbatim = _norm(c["quote"]) in _norm(_page_text(db, page_cache, c["paper_id"], c["page"]))
            related = coverage(content_terms(q.question), c["quote"]) >= FAITHFUL_COVERAGE or (
                q.expected_snippet and _norm(q.expected_snippet) in _norm(c["quote"]))
            valid += 1 if verbatim else 0
            ok = verbatim and related
            if ok and use_judge and llm is not None:
                j = judge_supports(llm, q.question, c["quote"])
                if j is not None:
                    judged_total += 1
                    judged_yes += 1 if j else 0
                    ok = j
            supported += 1 if ok else 0
        if q.answerable:
            answerable_n += 1
            rr.append(1.0 / rank if rank else 0.0)
            recall_hits += 1 if rank else 0
            false_refusals += 1 if refused else 0
            cites_total += len(ans.citations)
            cites_ok += supported
            passed = bool(rank) and not refused
        else:
            unanswerable_n += 1
            refused_correct += 1 if refused else 0
            passed = refused
        behavior = {"insufficient": "Refused", "answered": "Supported", "offline": "Offline excerpts", "reading": "Reading plan"}.get(ans.status, ans.status)
        details.append({
            "question": q.question, "answerable": q.answerable, "behavior": behavior, "status_raw": ans.status,
            "recall_rank": rank, "citations_valid": f"{valid}/{len(ans.citations)}" if ans.citations else "—",
            "faithfulness": round(supported / len(ans.citations), 2) if ans.citations else None,
            "result": "Pass" if passed else "Review",
        })
    metrics = {
        "k": k,
        "recall_at_k": round(recall_hits / answerable_n, 3) if answerable_n else None,
        "mrr": round(sum(rr) / len(rr), 3) if rr else None,
        "citation_faithfulness": round(cites_ok / cites_total, 3) if cites_total else None,
        "refusal_accuracy": round(refused_correct / unanswerable_n, 3) if unanswerable_n else None,
        "false_refusal_rate": round(false_refusals / answerable_n, 3) if answerable_n else None,
        "answerable": answerable_n, "unanswerable": unanswerable_n,
        "papers": db.query(Paper).filter(Paper.project_id == project_id, Paper.chunk_count > 0).count(),
        "retrieval_mode": "/".join(sorted(retrieval_modes)) or "none",
        "answer_mode": "/".join(sorted(answer_modes)) or "none",
        "judge": {"used": bool(use_judge and judged_total), "judged": judged_total, "supported": judged_yes},
        "extraction": extraction_accuracy(db, project_id),
    }
    run = EvalRun(project_id=project_id, mode=metrics["retrieval_mode"], n_questions=len(questions), metrics=metrics, details=details)
    db.add(run)
    db.commit()
    return run


# ---------------------------------------------------------------- extraction accuracy


def gold_match(name: str, got: str, expected: str) -> bool:
    if not got:
        return False
    if name in ("Metric value", "Seeds"):
        a, b = re.search(r"\d+(?:\.\d+)?", got), re.search(r"\d+(?:\.\d+)?", expected)
        return bool(a and b and float(a.group()) == float(b.group()))
    tg, te = set(tokens(got)), set(tokens(expected))
    return bool(te) and te <= tg


def extraction_accuracy(db: Session, project_id: int) -> dict[str, Any] | None:
    path = EVAL_DIR / "gold_fields.json"
    if not path.exists():
        return None
    gold = json.loads(path.read_text())["papers"]
    papers = db.query(Paper).filter(Paper.project_id == project_id).all()
    per_field: dict[str, list[bool]] = {}
    n_papers = 0
    for key, expected in gold.items():
        paper = next((p for p in papers if key.lower() in p.title.lower()), None)
        if not paper:
            continue
        n_papers += 1
        fields = {f.name: f for f in db.query(ExtractedField).filter(ExtractedField.paper_id == paper.id).all()}
        for name, exp in expected.items():
            f = fields.get(name)
            got = f.value if f and f.status not in ("rejected", "not_reported") else ""
            per_field.setdefault(name, []).append(gold_match(name, got, exp))
    if not per_field:
        return None
    flat = [x for v in per_field.values() for x in v]
    return {
        "overall": round(sum(flat) / len(flat), 3), "n_fields": len(flat), "n_papers": n_papers,
        "by_field": {k: round(sum(v) / len(v), 3) for k, v in per_field.items()},
    }


def run_out(r: EvalRun, with_details: bool = True) -> dict[str, Any]:
    out = {"id": r.id, "project_id": r.project_id, "created_at": r.created_at.isoformat(), "mode": r.mode,
           "n_questions": r.n_questions, "metrics": r.metrics}
    if with_details:
        out["details"] = r.details
    return out


def to_markdown(run: dict[str, Any]) -> str:
    m = run["metrics"]
    pct = lambda v: "n/a" if v is None else f"{v * 100:.1f}%"  # noqa: E731
    lines = [
        "# ResearchMind evaluation report", "",
        f"- Run: {run['created_at']}", f"- Questions: {run['n_questions']} ({m['answerable']} answerable, {m['unanswerable']} unanswerable) over {m['papers']} papers",
        f"- Retrieval mode: {m['retrieval_mode']} · Answer mode: {m['answer_mode']}", "",
        "| Metric | Value |", "|---|---|",
        f"| Recall@{m['k']} | {pct(m['recall_at_k'])} |", f"| MRR | {m['mrr'] if m['mrr'] is not None else 'n/a'} |",
        f"| Citation faithfulness | {pct(m['citation_faithfulness'])} |", f"| Refusal accuracy (unanswerable) | {pct(m['refusal_accuracy'])} |",
        f"| False refusal rate (answerable) | {pct(m['false_refusal_rate'])} |",
    ]
    ex = m.get("extraction")
    if ex:
        lines += [f"| Extraction accuracy (n={ex['n_fields']} labelled fields) | {pct(ex['overall'])} |"]
    lines += ["", "## Per-question results", "", "| Question | Behaviour | Recall rank | Citations valid | Faithfulness | Result |", "|---|---|---|---|---|---|"]
    for d in run["details"]:
        f = "—" if d["faithfulness"] is None else f"{d['faithfulness']:.2f}"
        lines.append(f"| {d['question']} | {d['behavior']} | {d['recall_rank'] or '—'} | {d['citations_valid']} | {f} | {d['result']} |")
    return "\n".join(lines) + "\n"
