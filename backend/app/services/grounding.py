"""Grounded question answering.

The model never writes citations. It sees numbered excerpts and may only say which numbers it used; this module
resolves those numbers to the real paper / page / verbatim quote from the database. If the evidence is not there,
the result is an explicit "insufficient" status, not a guess.
"""
from __future__ import annotations

import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Paper
from .ollama import LLMClient, OllamaError, OllamaUnavailable, parse_json_object
from .retrieval import Hit, RetrievalResult, search
from .text import best_quote, content_terms

log = logging.getLogger("researchmind.grounding")

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sufficient": {"type": "boolean"},
        "answer": {"type": "string"},
        "used": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["sufficient", "answer", "used"],
}

SYSTEM_PROMPT = (
    "You are a careful research assistant. Answer ONLY from the numbered excerpts provided. "
    "Do not use outside knowledge. Do not write author names, paper titles, years or page numbers: "
    "refer to evidence only by excerpt number in square brackets, like [2]. "
    "Use cautious wording (\"suggests\", \"reports\"). Keep the answer under 150 words. "
    "If the excerpts do not directly answer the question, set sufficient=false and leave answer empty. "
    "Return JSON: {\"sufficient\": bool, \"answer\": string, \"used\": [excerpt numbers you relied on]}."
)

_MARKER = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


@dataclass
class AnswerResult:
    status: str  # answered | insufficient | offline | reading
    content: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def hit_passes(h: Hit, min_semantic: float, min_keyword: float, n_terms: int) -> bool:
    """Is this passage related enough to the question to be shown to the model at all?"""
    if h.semantic is not None and h.semantic >= min_semantic and h.keyword > 0:
        return True
    needed = min_keyword if n_terms >= 3 else 0.5
    return h.keyword >= needed and (n_terms < 2 or h.keyword * n_terms >= 2 - 1e-9)


def _paper_map(db: Session, ids: set[int]) -> dict[int, Paper]:
    return {p.id: p for p in db.query(Paper).filter(Paper.id.in_(ids)).all()} if ids else {}


def build_citation(n: int, h: Hit, paper: Paper | None, terms: list[str]) -> dict[str, Any]:
    return {
        "n": n,
        "chunk_id": h.chunk_id,
        "paper_id": h.paper_id,
        "paper_title": paper.title if paper else "(deleted paper)",
        "authors": paper.authors if paper else "",
        "year": paper.year if paper else None,
        "page": h.page,
        "quote": best_quote(h.text, terms),
        "score": round(h.semantic, 3) if h.semantic is not None else None,
    }


def reading_plan(hits: list[Hit], papers: dict[int, Paper], terms: list[str]) -> tuple[str, list[dict[str, Any]]]:
    """Reading mode: point the researcher at what to read and compare, instead of writing prose for them."""
    by_paper: OrderedDict[int, list[Hit]] = OrderedDict()
    for h in hits:
        by_paper.setdefault(h.paper_id, []).append(h)
    lines = ["Here is what to read and compare. I have not summarised it for you."]
    citations: list[dict[str, Any]] = []
    n = 0
    for pid, hs in by_paper.items():
        p = papers.get(pid)
        pages = sorted({h.page for h in hs})
        label = p.title if p else "(deleted paper)"
        lines.append(f"• Read {label} — pages {', '.join(map(str, pages))}.")
        for h in hs[:2]:
            n += 1
            citations.append(build_citation(n, h, p, terms))
    if len(by_paper) >= 2:
        lines.append("Compare how these papers frame the question, what setup each one reports, and whether they agree.")
    else:
        lines.append("Read the passages in context, then decide what you think they establish.")
    return "\n".join(lines), citations


def _clean_answer(answer: str, used: list[int]) -> str:
    """Keep only citation markers that refer to excerpts the model said it used."""
    allowed = set(used)

    def repl(m: re.Match[str]) -> str:
        nums = [int(x) for x in re.split(r"\s*,\s*", m.group(1))]
        keep = [n for n in nums if n in allowed]
        return "".join(f"[{n}]" for n in keep)

    return re.sub(r"\s{2,}", " ", _MARKER.sub(repl, answer)).strip()


def parse_model_answer(raw: str, n_excerpts: int) -> tuple[bool, str, list[int]] | None:
    obj = parse_json_object(raw)
    if obj is None:
        return None
    sufficient = obj.get("sufficient")
    answer = obj.get("answer")
    used_raw = obj.get("used")
    if not isinstance(sufficient, bool) or not isinstance(answer, str) or not isinstance(used_raw, list):
        return None
    used: list[int] = []
    for u in used_raw:
        if isinstance(u, int) and not isinstance(u, bool) and 1 <= u <= n_excerpts and u not in used:
            used.append(u)
    # Markers in the answer count as "used" too, but only if they are real excerpt numbers.
    for m in _MARKER.finditer(answer):
        for x in re.split(r"\s*,\s*", m.group(1)):
            xi = int(x)
            if 1 <= xi <= n_excerpts and xi not in used:
                used.append(xi)
    return sufficient, answer.strip(), sorted(used)


def answer_question(
    db: Session,
    question: str,
    project_id: int,
    llm: LLMClient | None,
    reading_mode: bool = False,
    history: list[tuple[str, str]] | None = None,
) -> AnswerResult:
    cfg = get_settings()
    t0 = time.time()
    n_papers = db.query(Paper).filter(Paper.project_id == project_id, Paper.chunk_count > 0).count()
    result: RetrievalResult = search(db, question, project_id, cfg.retrieve_k, "hybrid", llm)
    terms = result.terms or content_terms(question)
    good = [h for h in result.hits if hit_passes(h, cfg.min_semantic_score, cfg.min_keyword_coverage, len(terms))]
    meta: dict[str, Any] = {
        "retrieval_mode": result.mode,
        "degraded": result.degraded,
        "papers_searched": n_papers,
        "passages_considered": len(result.hits),
        "passages_used": len(good),
        "terms": terms,
    }
    if not good:
        meta["took_s"] = round(time.time() - t0, 2)
        return AnswerResult(
            "insufficient",
            "Your library does not contain passages that answer this question.",
            [],
            meta,
        )
    good = good[:6]
    papers = _paper_map(db, {h.paper_id for h in good})

    if reading_mode:
        text, cites = reading_plan(good, papers, terms)
        meta["took_s"] = round(time.time() - t0, 2)
        return AnswerResult("reading", text, cites, meta)

    excerpt_block = "\n\n".join(f"[{i}] {h.text}" for i, h in enumerate(good, start=1))
    user_prompt = f"Question: {question}\n\nExcerpts:\n{excerpt_block}"
    if llm is None:
        return _offline(good, papers, terms, meta, t0)
    parsed: tuple[bool, str, list[int]] | None = None
    try:
        for attempt in range(2):
            raw = llm.chat_json(SYSTEM_PROMPT, user_prompt if attempt == 0 else user_prompt + "\n\nReturn valid JSON only.", ANSWER_SCHEMA)
            parsed = parse_model_answer(raw, len(good))
            if parsed:
                break
    except OllamaUnavailable:
        return _offline(good, papers, terms, meta, t0)
    except OllamaError as e:
        meta["error"] = str(e)
        return _offline(good, papers, terms, meta, t0, reason=str(e))

    meta["model"] = llm.answer_model
    meta["took_s"] = round(time.time() - t0, 2)
    if not parsed:
        meta["error"] = "The model did not return a usable answer."
        return _offline(good, papers, terms, meta, t0, reason="The model did not return a usable answer.")
    sufficient, answer, used = parsed
    if not sufficient or not answer or not used:
        return AnswerResult(
            "insufficient",
            "Your library does not contain passages that directly answer this question.",
            [],
            {**meta, "related_passages": len(good)},
        )
    answer = _clean_answer(answer, used)
    cites = [build_citation(n, good[n - 1], papers.get(good[n - 1].paper_id), terms) for n in used]
    return AnswerResult("answered", answer, cites, meta)


def _offline(
    good: list[Hit], papers: dict[int, Paper], terms: list[str], meta: dict[str, Any], t0: float, reason: str = ""
) -> AnswerResult:
    cites = [build_citation(i, h, papers.get(h.paper_id), terms) for i, h in enumerate(good[:4], start=1)]
    meta["took_s"] = round(time.time() - t0, 2)
    msg = reason or "Ollama is not reachable, so I cannot write an answer."
    return AnswerResult(
        "offline",
        f"{msg} These are the passages from your library that match your question; read them directly.",
        cites,
        meta,
    )
