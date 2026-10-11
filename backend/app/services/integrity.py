"""Writing-integrity checks. Rule-based first; every finding quotes the source text and none assigns a verdict."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from ..models import ExtractedField, Page, Paper, ResultRow
from .compare import paper_label
from .grounding import build_citation
from .ollama import LLMClient
from .results import norm_dataset, norm_method, norm_metric, parse_paper_claims
from .retrieval import Hit, search
from .text import best_quote, content_terms, coverage, split_sentences
from pathlib import Path

# ---------------------------------------------------------------- numeric consistency


def numeric_consistency(db: Session, paper: Paper) -> dict[str, Any]:
    pages = [p.text for p in db.query(Page).filter(Page.paper_id == paper.id).order_by(Page.number).all()]
    claims = parse_paper_claims(Path(paper.file_path), pages)
    groups: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
    for c in claims:
        groups[(norm_method(c.method), norm_dataset(c.dataset), norm_metric(c.metric))].append(c)
    mismatches: list[dict[str, Any]] = []
    for (_, _, _), cs in groups.items():
        distinct = sorted({round(c.value, 4) for c in cs})
        if len(distinct) < 2:
            continue
        cs_sorted = sorted(cs, key=lambda c: (c.page, c.section))
        first = cs_sorted[0]
        other = next(c for c in cs_sorted[1:] if round(c.value, 4) != round(first.value, 4))
        mismatches.append({
            "label": f"{first.method} · {first.metric} on {first.dataset}",
            "metric": first.metric,
            "summary": f"The paper states {first.value:g}{first.unit} in one place and {other.value:g}{other.unit} in another for the same method, dataset and metric.",
            "a": {"value": f"{first.value:g}{first.unit}", "section": first.section or "Text", "page": first.page, "quote": first.quote, "source": first.source},
            "b": {"value": f"{other.value:g}{other.unit}", "section": other.section or "Text", "page": other.page, "quote": other.quote, "source": other.source},
        })
    return {
        "paper_id": paper.id,
        "title": paper.title,
        "mentions_checked": len(claims),
        "mismatches": mismatches,
        "note": "A mismatch is a candidate to verify manually, not a finding of error.",
    }


# ---------------------------------------------------------------- reproducibility

REPRO_ITEMS = [
    ("Dataset and split", ["Dataset", "Split"]),
    ("Primary metric", ["Metric"]),
    ("Model checkpoint", ["Model"]),
    ("Hyperparameters", ["Hyperparameters"]),
    ("Random seeds", ["Seeds"]),
    ("Hardware", ["Hardware"]),
    ("Code and artifacts", ["Code link"]),
    ("Limitations discussed", ["Limitations"]),
]


def reproducibility(db: Session, paper: Paper) -> dict[str, Any]:
    fields = {f.name: f for f in db.query(ExtractedField).filter(ExtractedField.paper_id == paper.id).all()}

    def present(name: str) -> ExtractedField | None:
        f = fields.get(name)
        return f if f and f.status not in ("not_reported", "rejected") and f.value else None

    items = []
    for label, names in REPRO_ITEMS:
        found = [present(n) for n in names]
        got = [f for f in found if f]
        if label == "Hyperparameters" and got:
            n_hp = len(re.findall(r"learning rate|batch size|epoch|optimi[sz]er|scheduler|weight decay|dropout", got[0].value, re.I))
            status = "reported" if n_hp >= 2 else "partial"
        elif len(got) == len(names):
            status = "reported"
        elif got:
            status = "partial"
        else:
            status = "missing"
        first = got[0] if got else None
        items.append({
            "item": label, "status": status,
            "detail": "; ".join(f.value for f in got) if got else "No supporting passage located",
            "page": first.page if first else None, "quote": first.quote if first else "",
        })
    counts = {s: sum(1 for i in items if i["status"] == s) for s in ("reported", "partial", "missing")}
    return {
        "paper_id": paper.id, "title": paper.title, "items": items, "counts": counts,
        "note": "“Not located” means the analysis did not find supporting text. Verify the paper and its supplements manually.",
    }


# ---------------------------------------------------------------- overclaim

STRONG_TERMS: list[tuple[str, str, str]] = [
    # (regex, kind, suggested qualifier)
    (r"\balways\b", "universal", "often / in our experiments"),
    (r"\bnever\b", "universal", "rarely / in the settings we tested"),
    (r"\b(?:all|every)\s+(?:datasets?|models?|domains?|model sizes|settings|tasks)\b", "universal", "the datasets and models we tested"),
    (r"\bacross all\b", "universal", "across the settings we tested"),
    (r"\b(?:prove[sd]?|proven|proof)\b", "certainty", "suggests / is consistent with"),
    (r"\b(?:definitive(?:ly)?|conclusive(?:ly)?|undeniabl[ey]|clearly demonstrates?)\b", "certainty", "suggests"),
    (r"\bguarantee[sd]?\b", "certainty", "is expected to"),
    (r"\beliminat(?:e|es|ed|ing)\b", "absolute", "reduces"),
    (r"\bsolv(?:e|es|ed|ing)\b", "absolute", "improves on"),
    (r"\bstate[- ]of[- ]the[- ]art\b", "comparative", "competitive with the baselines we compared"),
    (r"\boutperforms?\s+all\b", "comparative", "outperforms the baselines we tested"),
    (r"\bsignificantly\b", "statistical", "(only if a significance test is reported)"),
    (r"\bgeneraliz(?:e|es|ed)\b", "universal", "transfers to the datasets we tested"),
    (r"\b100\s?%", "absolute", "the exact measured value"),
]
QUESTIONS = {
    "universal": ["Does your evidence cover every dataset, model size and domain this sentence claims?", "Could a condition such as retrieval relevance or data size qualify the statement?"],
    "certainty": ["Is there a test or replication that supports ‘proves’, or does the evidence only suggest it?"],
    "absolute": ["Do your results show the effect disappears entirely, or that it shrinks?"],
    "comparative": ["Which baselines, datasets and years does ‘state of the art’ refer to, and are they all in your tables?"],
    "statistical": ["Did you run a significance test, and is the test and p-value reported next to this claim?"],
}
_SIG_RE = re.compile(r"\bp\s*[<=]\s*0?\.\d+|confidence interval|standard deviation|std\b|±|significance test|t-test|bootstrap", re.I)


def overclaim_review(db: Session, project_id: int, text: str, llm: LLMClient | None) -> dict[str, Any]:
    sentences = _spans(text)
    findings: list[dict[str, Any]] = []
    for start, end, sent in sentences:
        hits = []
        for rx, kind, suggestion in STRONG_TERMS:
            for m in re.finditer(rx, sent, re.I):
                hits.append({"term": m.group(0), "kind": kind, "qualifier": suggestion})
        if not hits:
            continue
        res = search(db, sent, project_id, 4, "hybrid", llm)
        papers = {p.id: p for p in db.query(Paper).filter(Paper.id.in_({h.paper_id for h in res.hits})).all()} if res.hits else {}
        terms = res.terms or content_terms(sent)
        evidence = [build_citation(i, h, papers.get(h.paper_id), terms) for i, h in enumerate(res.hits[:3], start=1)]
        retrieved_papers = {h.paper_id for h in res.hits}
        facts = _facts(db, project_id, sent, retrieved_papers, [h.text for h in res.hits])
        kinds = list(dict.fromkeys(h["kind"] for h in hits))
        findings.append({
            "start": start, "end": end, "sentence": sent, "wording": hits, "evidence": evidence, "facts": facts,
            "questions": [q for k in kinds for q in QUESTIONS.get(k, [])][:4],
        })
    return {
        "findings": findings,
        "sentences_checked": len(sentences),
        "note": "No score or verdict is assigned. Strong wording is compared with what your library can show; you decide what to claim.",
    }


def _spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    pos = 0
    for sent in split_sentences(text):
        i = text.find(sent, pos)
        if i < 0:
            continue
        spans.append((i, i + len(sent), sent))
        pos = i + len(sent)
    return spans


def _facts(db: Session, project_id: int, sentence: str, paper_ids: set[int], passages: list[str]) -> list[dict[str, str]]:
    facts = [{"label": "Papers in your library with related passages", "value": str(len(paper_ids))}]
    if paper_ids:
        datasets = {
            norm_dataset(r.dataset)
            for r in db.query(ResultRow).filter(ResultRow.paper_id.in_(list(paper_ids))).all()
        }
        facts.append({"label": "Distinct datasets in their reported results", "value": str(len(datasets)) if datasets else "none parsed"})
        seeds = [f for f in db.query(ExtractedField).filter(ExtractedField.paper_id.in_(list(paper_ids)), ExtractedField.name == "Seeds").all() if f.value]
        if seeds:
            facts.append({"label": "Seed counts reported", "value": ", ".join(sorted({f.value for f in seeds}))})
    facts.append({"label": "Significance testing in related passages", "value": "mentioned" if any(_SIG_RE.search(p) for p in passages) else "not found"})
    return facts


# ---------------------------------------------------------------- citation audit

_CITE_AUTHOR_YEAR = re.compile(r"\b([A-Z][A-Za-z\-']+)(?:\s+et\s+al\.?|\s+and\s+[A-Z][A-Za-z\-']+|\s*&\s*[A-Z][A-Za-z\-']+)?[,\s]*\(?\s*((?:19|20)\d{2})\s*\)?")
_CITE_NUMERIC = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def _surname_year(p: Paper) -> tuple[str, int | None]:
    first = [a.strip() for a in re.split(r",|;| and ", p.authors or "") if a.strip()]
    return (first[0].split()[-1].lower() if first else ""), p.year


def _best_passage(db: Session, paper: Paper, sentence: str, llm: LLMClient | None) -> dict[str, Any] | None:
    terms = content_terms(re.sub(_CITE_NUMERIC, " ", sentence))
    res = search(db, " ".join(terms) or sentence, paper.project_id, 10, "hybrid", llm)
    hits = [h for h in res.hits if h.paper_id == paper.id]
    if not hits:  # fall back to scanning the cited paper's own chunks directly
        from ..models import Chunk
        chunks = db.query(Chunk).filter(Chunk.paper_id == paper.id).all()
        hits = [Hit(c.id, c.paper_id, c.page_number, c.text, keyword=coverage(terms, c.text)) for c in chunks]
        hits.sort(key=lambda h: -h.keyword)
    if not hits:
        return None
    top = hits[0]
    return {**build_citation(1, top, paper, terms), "term_overlap": round(coverage(terms, top.text), 2)}


def _overlap_label(overlap: float) -> str:
    return "High term overlap" if overlap >= 0.5 else "Low term overlap, read the passage"


def library_citation_audit(db: Session, project_id: int, llm: LLMClient | None) -> list[dict[str, Any]]:
    """Where one library paper cites another (author + year in its text), show the citing sentence next to
    the cited paper's most relevant passage."""
    papers = db.query(Paper).filter(Paper.project_id == project_id).all()
    out: list[dict[str, Any]] = []
    for citing in papers:
        for page in db.query(Page).filter(Page.paper_id == citing.id).order_by(Page.number).all():
            for sent in split_sentences(page.text):
                for m in _CITE_AUTHOR_YEAR.finditer(sent):
                    surname, year = m.group(1).lower(), int(m.group(2))
                    for cited in papers:
                        if cited.id == citing.id:
                            continue
                        cs, cy = _surname_year(cited)
                        if cs == surname and cy == year:
                            passage = _best_passage(db, cited, sent, llm)
                            if passage:
                                out.append(_audit_row(citing, cited, sent, page.number, passage, m.group(0)))
    return out


def draft_citation_audit(db: Session, project_id: int, text: str, mapping: dict[str, int], llm: LLMClient | None) -> list[dict[str, Any]]:
    papers = {p.id: p for p in db.query(Paper).filter(Paper.project_id == project_id).all()}
    out: list[dict[str, Any]] = []
    for ordinal, (_, _, sent) in enumerate(_spans(text), start=1):
        targets: list[tuple[Paper, str]] = []
        for m in _CITE_NUMERIC.finditer(sent):
            for num in re.split(r"\s*,\s*", m.group(1)):
                pid = mapping.get(num)
                if pid and pid in papers:
                    targets.append((papers[pid], f"[{num}]"))
        for m in _CITE_AUTHOR_YEAR.finditer(sent):
            for p in papers.values():
                if _surname_year(p) == (m.group(1).lower(), int(m.group(2))):
                    targets.append((p, m.group(0)))
        for cited, marker in targets:
            passage = _best_passage(db, cited, sent, llm)
            if passage:
                out.append({
                    "marker": marker, "citing_sentence": sent, "location": f"Draft, sentence {ordinal}",
                    "cited": {"paper_id": cited.id, "label": paper_label(cited), "title": cited.title},
                    "passage": passage, "overlap_label": _overlap_label(passage["term_overlap"]),
                })
    return out


def _audit_row(citing: Paper, cited: Paper, sent: str, page: int, passage: dict[str, Any], marker: str) -> dict[str, Any]:
    return {
        "marker": marker, "citing_sentence": sent, "location": f"{paper_label(citing)} · p. {page}",
        "citing_paper": {"paper_id": citing.id, "title": citing.title},
        "cited": {"paper_id": cited.id, "label": paper_label(cited), "title": cited.title},
        "passage": passage, "overlap_label": _overlap_label(passage["term_overlap"]),
    }
