"""Reference discovery + prior-work audit.

Privacy contract: uploaded paper text never leaves the machine. When online discovery is enabled, only short
generated search queries (<= 100 chars) are sent to OpenAlex / Semantic Scholar / arXiv. Every run writes a receipt
saying what was searched, what was not, and what came back. No supports/contradicts verdicts, no novelty score.
"""
from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
import numpy as np
from sqlalchemy.orm import Session

from ..models import Paper, SearchReceipt
from .compare import paper_label
from .ollama import LLMClient, OllamaError, OllamaUnavailable, parse_json_object
from .results import DATASET_LEXICON
from .retrieval import search
from .text import best_quote, content_terms, coverage, split_sentences

log = logging.getLogger("researchmind.discovery")

EXTERNAL_SOURCES = ["OpenAlex", "Semantic Scholar", "arXiv"]
ALWAYS_NOT_SEARCHED = ["Scopus", "Web of Science", "ProQuest Dissertations", "Google Scholar", "Patent databases"]
MAX_QUERY_CHARS = 100
LOCAL = "Your local library"

# Tests replace this with an httpx.MockTransport; production leaves it None (real network).
_transport: httpx.BaseTransport | None = None
_cache: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}
CACHE_TTL = 3600


@dataclass
class Candidate:
    title: str
    authors: str = ""
    year: int | None = None
    venue: str = ""
    url: str = ""
    abstract: str = ""
    source: str = ""
    citations: int | None = None
    doi: str = ""
    paper_id: int | None = None
    page: int | None = None
    why: str = ""
    why_source: str = ""
    tags: list[str] = field(default_factory=list)
    score: float = 0.0


# ------------------------------------------------------------------ queries

QUERY_SCHEMA = {"type": "object", "properties": {"queries": {"type": "array", "items": {"type": "string"}}}, "required": ["queries"]}


def clean_query(q: str) -> str:
    q = re.sub(r"\s+", " ", re.sub(r"[\r\n\t]", " ", q)).strip().strip("\"'")
    return q[:MAX_QUERY_CHARS].rsplit(" ", 1)[0] if len(q) > MAX_QUERY_CHARS else q


def fallback_queries(text: str) -> list[str]:
    terms = content_terms(text)
    # use original (unstemmed) words in order of appearance for readable queries
    words = []
    for w in re.findall(r"[A-Za-z][A-Za-z\-]+", text):
        lw = w.lower()
        if content_terms(lw) and lw not in words:
            words.append(lw)
    if not words:
        return [clean_query(text)] if text.strip() else []
    qs = [" ".join(words[:5])]
    if len(words) > 5:
        qs.append(" ".join(words[3:8]))
    if len(words) > 8:
        qs.append(" ".join(words[:2] + words[-3:]))
    return list(dict.fromkeys(clean_query(q) for q in qs if q))[:5]


def generate_queries(llm: LLMClient | None, text: str) -> list[str]:
    if llm is not None:
        try:
            raw = llm.chat_json(
                "Write 3 to 5 short academic search queries (max 8 words each) that would find papers related to the user's text. "
                "Use only terms from the text. Return JSON {\"queries\": [...]}.",
                text[:1500], QUERY_SCHEMA,
            )
            obj = parse_json_object(raw) or {}
            qs = [clean_query(q) for q in obj.get("queries", []) if isinstance(q, str) and q.strip()]
            qs = list(dict.fromkeys(q for q in qs if q))[:5]
            if len(qs) >= 2:
                return qs
        except (OllamaUnavailable, OllamaError):
            pass
    return fallback_queries(text)


# ------------------------------------------------------------------ external sources


def _client() -> httpx.Client:
    return httpx.Client(timeout=8.0, transport=_transport, headers={"User-Agent": "ResearchMind/1.0 (local research tool)"})


def _abstract_from_inverted(idx: dict[str, list[int]] | None) -> str:
    if not idx:
        return ""
    words: dict[int, str] = {}
    for w, positions in idx.items():
        for p in positions:
            words[p] = w
    return " ".join(words[i] for i in sorted(words))


def fetch_openalex(c: httpx.Client, q: str) -> list[Candidate]:
    r = c.get("https://api.openalex.org/works", params={"search": q, "per-page": 10})
    r.raise_for_status()
    out = []
    for w in r.json().get("results", []):
        loc = (w.get("primary_location") or {}).get("source") or {}
        out.append(Candidate(
            title=w.get("title") or w.get("display_name") or "", year=w.get("publication_year"),
            authors=", ".join(a["author"]["display_name"] for a in (w.get("authorships") or [])[:4] if a.get("author")),
            venue=loc.get("display_name") or "", url=w.get("doi") or w.get("id") or "",
            abstract=_abstract_from_inverted(w.get("abstract_inverted_index")), source="OpenAlex",
            citations=w.get("cited_by_count"), doi=(w.get("doi") or "").lower(),
        ))
    return out


def fetch_semantic_scholar(c: httpx.Client, q: str) -> list[Candidate]:
    r = c.get("https://api.semanticscholar.org/graph/v1/paper/search",
              params={"query": q, "limit": 10, "fields": "title,authors,year,venue,abstract,url,externalIds,citationCount"})
    r.raise_for_status()
    out = []
    for w in r.json().get("data", []):
        out.append(Candidate(
            title=w.get("title") or "", year=w.get("year"),
            authors=", ".join(a.get("name", "") for a in (w.get("authors") or [])[:4]),
            venue=w.get("venue") or "", url=w.get("url") or "", abstract=w.get("abstract") or "",
            source="Semantic Scholar", citations=w.get("citationCount"),
            doi=("https://doi.org/" + w["externalIds"]["DOI"].lower()) if (w.get("externalIds") or {}).get("DOI") else "",
        ))
    return out


def fetch_arxiv(c: httpx.Client, q: str) -> list[Candidate]:
    r = c.get("http://export.arxiv.org/api/query", params={"search_query": f"all:{q}", "max_results": 10})
    r.raise_for_status()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(r.text)
    out = []
    for e in root.findall("a:entry", ns):
        published = (e.findtext("a:published", default="", namespaces=ns) or "")[:4]
        out.append(Candidate(
            title=" ".join((e.findtext("a:title", default="", namespaces=ns) or "").split()),
            authors=", ".join((a.findtext("a:name", default="", namespaces=ns) or "") for a in e.findall("a:author", ns)[:4]),
            year=int(published) if published.isdigit() else None, venue="arXiv",
            url=e.findtext("a:id", default="", namespaces=ns) or "",
            abstract=" ".join((e.findtext("a:summary", default="", namespaces=ns) or "").split()), source="arXiv",
        ))
    return out


FETCHERS = {"OpenAlex": fetch_openalex, "Semantic Scholar": fetch_semantic_scholar, "arXiv": fetch_arxiv}


def query_external(queries: list[str]) -> tuple[list[Candidate], dict[str, dict[str, Any]]]:
    """Returns candidates + per-source status. Network problems degrade gracefully and are recorded in the receipt."""
    cands: list[Candidate] = []
    status: dict[str, dict[str, Any]] = {s: {"ok": 0, "failed": 0, "reason": ""} for s in EXTERNAL_SOURCES}
    with _client() as c:
        for src, fn in FETCHERS.items():
            for q in queries:
                key = (src, q.lower())
                hit = _cache.get(key)
                if hit and time.time() - hit[0] < CACHE_TTL:
                    cands.extend(Candidate(**d) for d in hit[1])
                    status[src]["ok"] += 1
                    continue
                try:
                    got = fn(c, q)
                    _cache[key] = (time.time(), [g.__dict__ for g in got])
                    cands.extend(got)
                    status[src]["ok"] += 1
                except httpx.HTTPStatusError as e:
                    status[src]["failed"] += 1
                    status[src]["reason"] = "rate limited" if e.response.status_code == 429 else f"HTTP {e.response.status_code}"
                    if e.response.status_code == 429:
                        break  # stop hammering a source that is rate limiting us
                except (httpx.HTTPError, ET.ParseError, ValueError, KeyError) as e:
                    status[src]["failed"] += 1
                    status[src]["reason"] = type(e).__name__
    return cands, status


# ------------------------------------------------------------------ ranking helpers


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def dedupe(cands: list[Candidate]) -> list[Candidate]:
    seen: dict[str, Candidate] = {}
    for c in cands:
        if not c.title:
            continue
        key = c.doi or norm_title(c.title)
        prev = seen.get(key) or seen.get(norm_title(c.title))
        if prev is None:
            seen[key] = c
            seen[norm_title(c.title)] = c
        elif len(c.abstract) > len(prev.abstract):
            prev.abstract = c.abstract
    uniq: list[Candidate] = []
    ids: set[int] = set()
    for c in seen.values():
        if id(c) not in ids:
            ids.add(id(c))
            uniq.append(c)
    return uniq


def why_sentence(abstract: str, claim_terms: list[str]) -> str:
    sents = split_sentences(abstract)
    if not sents:
        return ""
    scored = sorted(((coverage(claim_terms, s), -i, s) for i, s in enumerate(sents)), reverse=True)
    return scored[0][2] if scored[0][0] > 0 else ""


def tag(c: Candidate, now_year: int) -> list[str]:
    tags: list[str] = []
    text = f"{c.title}. {c.abstract}".lower()
    if (c.citations or 0) >= 1000 or ((c.citations or 0) >= 300 and c.year and c.year <= now_year - 5):
        tags.append("foundational")
    if c.year and c.year >= now_year - 2:
        tags.append("recent")
    if re.search(r"\bbenchmark", text):
        tags.append("benchmark")
    if re.search(r"we (?:introduce|release|present|construct|build) (?:a|an|the)? ?(?:new )?(?:dataset|corpus)|new dataset|a dataset of", text):
        tags.append("dataset")
    if re.search(r"we (?:propose|introduce|present|develop)|novel (?:method|approach)|our (?:method|approach)", text):
        tags.append("methodology")
    return tags


def rerank(cands: list[Candidate], claim: str, llm: LLMClient | None) -> tuple[list[Candidate], str]:
    terms = content_terms(claim)
    method = "term overlap"
    base = [coverage(terms, f"{c.title}. {c.abstract}") for c in cands]
    if llm is not None and cands:
        try:
            vecs = np.asarray(llm.embed([claim] + [f"{c.title}. {c.abstract}"[:1200] for c in cands]), dtype=np.float32)
            n = np.linalg.norm(vecs, axis=1, keepdims=True)
            n[n == 0] = 1.0
            vecs = vecs / n
            sims = vecs[1:] @ vecs[0]
            base = [float(0.7 * s + 0.3 * b) for s, b in zip(sims, base, strict=True)]
            method = "local embeddings + term overlap"
        except (OllamaUnavailable, OllamaError):
            pass
    for c, s in zip(cands, base, strict=True):
        c.score = round(float(s), 3)
    return sorted(cands, key=lambda c: -c.score), method


# ------------------------------------------------------------------ main entry points


def local_candidates(db: Session, project_id: int, queries: list[str], claim: str, llm: LLMClient | None) -> list[Candidate]:
    seen: dict[int, Candidate] = {}
    terms = content_terms(claim)
    for q in queries + [claim]:
        res = search(db, q, project_id, 6, "hybrid", llm)
        for h in res.hits:
            if h.paper_id in seen:
                continue
            p = db.get(Paper, h.paper_id)
            if not p:
                continue
            quote = best_quote(h.text, terms)
            seen[h.paper_id] = Candidate(
                title=p.title, authors=p.authors, year=p.year, venue=p.venue or "In your library", source=LOCAL,
                abstract="", paper_id=p.id, page=h.page, why=quote, why_source="library passage",
            )
    return list(seen.values())


def run_discovery(
    db: Session, project_id: int, text: str, queries: list[str] | None, online: bool, llm: LLMClient | None,
    kind: str = "discovery", limit: int = 12,
) -> dict[str, Any]:
    text = text.strip()
    qs = [clean_query(q) for q in (queries or []) if q and q.strip()] or generate_queries(llm, text)
    qs = list(dict.fromkeys(q for q in qs if q))[:5]
    terms = content_terms(text)
    now_year = datetime.now(timezone.utc).year

    local = local_candidates(db, project_id, qs, text, llm)
    external: list[Candidate] = []
    src_status: dict[str, dict[str, Any]] = {}
    if online:
        external, src_status = query_external(qs)
    raw_total = len(local) + len(external)
    for c in external:
        c.why = why_sentence(c.abstract, terms)
        c.why_source = "abstract" if c.why else ""
        c.tags = tag(c, now_year)
    uniq_ext = dedupe(external)
    ranked, rank_method = rerank(local + uniq_ext, text, llm)
    top = ranked[:limit]

    searched = [LOCAL]
    not_searched = list(ALWAYS_NOT_SEARCHED)
    for s in EXTERNAL_SOURCES:
        if not online:
            not_searched.insert(0, f"{s} (online discovery is off)")
        elif src_status.get(s, {}).get("ok", 0) > 0:
            searched.append(s)
        else:
            not_searched.insert(0, f"{s} ({src_status.get(s, {}).get('reason') or 'no response'})")
    results = [_candidate_out(i, c) for i, c in enumerate(top, start=1)]
    counts = {
        "queries": len(qs), "sources_searched": len(searched), "results_returned": raw_total,
        "duplicates_removed": len(external) - len(uniq_ext), "titles_screened": len(local) + len(uniq_ext),
        "abstracts_inspected": sum(1 for c in top if c.abstract or c.why), "candidates": len(top),
    }
    receipt = SearchReceipt(
        project_id=project_id, kind=kind, input_text=text, queries=qs, sources_searched=searched,
        sources_not_searched=not_searched, counts={**counts, "rank_method": rank_method}, results=results, online=online,
    )
    db.add(receipt)
    db.commit()
    return receipt_out(receipt)


def _candidate_out(rank: int, c: Candidate) -> dict[str, Any]:
    return {
        "rank": rank, "title": c.title, "authors": c.authors, "year": c.year, "venue": c.venue, "url": c.url,
        "source": c.source, "why": c.why, "why_source": c.why_source, "tags": c.tags, "score": c.score,
        "paper_id": c.paper_id, "page": c.page, "abstract_available": bool(c.abstract),
    }


def receipt_out(r: SearchReceipt) -> dict[str, Any]:
    return {
        "id": r.id, "project_id": r.project_id, "kind": r.kind, "input_text": r.input_text, "queries": r.queries,
        "sources_searched": r.sources_searched, "sources_not_searched": r.sources_not_searched, "counts": r.counts,
        "results": r.results, "online": r.online, "created_at": r.created_at.isoformat(),
        "notice": "Absence of results is not evidence of novelty.",
    }


# ------------------------------------------------------------------ prior-work audit


def prior_work(db: Session, project_id: int, idea: str, online: bool, llm: LLMClient | None) -> dict[str, Any]:
    receipt = run_discovery(db, project_id, idea, None, online, llm, kind="prior_work", limit=8)
    idea_terms = content_terms(idea)
    overlaps = []
    for c in receipt["results"][:6]:
        source_text = c["why"] or ""
        shared = [t for t in idea_terms if t in {*content_terms(c["title"]), *content_terms(source_text)}][:4]
        method_sent = next((s for s in split_sentences(source_text) if re.search(r"\b(propose|method|approach|introduce|present)", s, re.I)), "")
        datasets = [d for d in DATASET_LEXICON if re.search(rf"\b{re.escape(d)}\b", f"{c['title']} {source_text}")]
        overlaps.append({**c, "overlap": {"shared_terms": shared, "method_statement": method_sent, "datasets": datasets}})
    return {
        "receipt": receipt,
        "closest": overlaps,
        "notices": [
            "Not a legal or patentability opinion. No novelty score.",
            "Absence of results is not evidence of novelty.",
        ],
    }
