"""Candidate gap map: cluster limitation / future-work statements across the library, each with quotes.

Clusters are grouped by similarity of wording (embeddings when Ollama is available, term vectors otherwise). A dense
cluster can mean active work, not an open gap, so the output is framed as candidates for the researcher to judge.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from ..models import Page, Paper
from .compare import paper_label
from .ollama import LLMClient, OllamaError, OllamaUnavailable
from .text import content_terms, split_sentences

_LIMIT = re.compile(
    r"\b(limitations?|future work|future research|future studies|we leave|remains? (?:an )?(?:open|underexplored|unexplored)|"
    r"underexplored|few studies|we (?:could not|did not|do not|only)|not evaluate|left for)\b", re.I)
_FUTURE = re.compile(r"\b(future work|future research|future studies|should (?:study|consider|explore)|we leave|left for)\b", re.I)
GENERIC = {"limitation", "work", "future", "study", "paper", "result", "model", "method", "approach", "evaluate", "evaluation", "leave", "show"}


def collect_statements(db: Session, project_id: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in db.query(Paper).filter(Paper.project_id == project_id).all():
        for page in db.query(Page).filter(Page.paper_id == p.id).order_by(Page.number).all():
            for sent in split_sentences(page.text):
                if len(sent.split()) >= 6 and _LIMIT.search(sent):
                    out.append({
                        "paper_id": p.id, "paper_title": p.title, "label": paper_label(p), "page": page.number,
                        "quote": sent, "kind": "future work" if _FUTURE.search(sent) else "limitation",
                    })
    return out


def _vectors(statements: list[dict[str, Any]], llm: LLMClient | None) -> tuple[np.ndarray, str]:
    texts = [s["quote"] for s in statements]
    if llm is not None:
        try:
            emb = np.asarray(llm.embed(texts), dtype=np.float32)
            n = np.linalg.norm(emb, axis=1, keepdims=True)
            n[n == 0] = 1.0
            return emb / n, "embeddings"
        except (OllamaUnavailable, OllamaError):
            pass
    vocab: dict[str, int] = {}
    docs = [[t for t in content_terms(x) if t not in GENERIC] for x in texts]
    for d in docs:
        for t in d:
            vocab.setdefault(t, len(vocab))
    df = Counter(t for d in docs for t in set(d))
    mat = np.zeros((len(texts), max(len(vocab), 1)), dtype=np.float32)
    for i, d in enumerate(docs):
        for t, c in Counter(d).items():
            mat[i, vocab[t]] = (1 + math.log(c)) * math.log(1 + len(docs) / df[t])
    n = np.linalg.norm(mat, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return mat / n, "term vectors"


def build_gap_map(db: Session, project_id: int, llm: LLMClient | None, threshold: float | None = None) -> dict[str, Any]:
    statements = collect_statements(db, project_id)
    if not statements:
        return {"clusters": [], "method": "none", "statements_total": 0, "threshold": threshold}
    vecs, method = _vectors(statements, llm)
    thr = threshold if threshold is not None else (0.62 if method == "embeddings" else 0.18)
    centroids: list[np.ndarray] = []
    members: list[list[int]] = []
    for i, v in enumerate(vecs):
        best, best_sim = -1, 0.0
        for ci, c in enumerate(centroids):
            sim = float(v @ c / (np.linalg.norm(c) or 1.0))
            if sim > best_sim:
                best, best_sim = ci, sim
        if best >= 0 and best_sim >= thr:
            members[best].append(i)
            centroids[best] = centroids[best] + v
        else:
            centroids.append(v.copy())
            members.append([i])
    clusters: list[dict[str, Any]] = []
    for idxs in members:
        sts = [statements[i] for i in idxs]
        terms = Counter(t for s in sts for t in set(content_terms(s["quote"])) if t not in GENERIC)
        label_terms = [t for t, _ in terms.most_common(3)]
        papers = {s["paper_id"] for s in sts}
        clusters.append({
            "label_terms": label_terms,
            "label": " · ".join(label_terms) if label_terms else "uncategorised statements",
            "paper_count": len(papers),
            "statement_count": len(sts),
            "kinds": sorted({s["kind"] for s in sts}),
            "statements": sts,
        })
    clusters.sort(key=lambda c: (-c["paper_count"], -c["statement_count"]))
    for n, c in enumerate(clusters, start=1):
        c["n"] = n
    return {
        "clusters": clusters, "method": method, "statements_total": len(statements), "threshold": thr,
        "note": "Candidate gaps for you to evaluate. A dense cluster may indicate active work rather than an open gap.",
    }
