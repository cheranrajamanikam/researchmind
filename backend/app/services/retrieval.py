"""Hybrid retrieval: SQLite FTS5 keyword search + persisted-embedding semantic search.

Embeddings live in SQLite (chunks.embedding, float32 blobs) so they survive restarts. For search they are
loaded once per project into a NumPy matrix and compared exactly (cosine). That is fast for hundreds of papers;
see README "Limitations" for the swap-in point for an ANN index.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import text as sql
from sqlalchemy.orm import Session

from ..models import Chunk, Paper
from .ollama import LLMClient, OllamaError, OllamaUnavailable
from .text import content_terms, coverage, fts_match_expr, raw_terms


@dataclass
class Hit:
    chunk_id: int
    paper_id: int
    page: int
    text: str
    semantic: float | None = None  # cosine similarity, when available
    keyword: float = 0.0  # query-term coverage of this chunk (0..1)
    rank_score: float = 0.0
    sources: set[str] = field(default_factory=set)


@dataclass
class RetrievalResult:
    hits: list[Hit]
    mode: str  # keyword | semantic | hybrid
    degraded: str | None = None  # e.g. "ollama_offline"
    terms: list[str] = field(default_factory=list)


class _VectorCache:
    """Per-project matrix of normalised embeddings, rebuilt when the index version changes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._version = 0
        self._entries: dict[tuple[int, str], tuple[int, np.ndarray, list[int]]] = {}

    def bump(self) -> None:
        with self._lock:
            self._version += 1

    def get(self, db: Session, project_id: int | None, model: str) -> tuple[np.ndarray, list[int]]:
        key = (project_id or 0, model)
        with self._lock:
            ent = self._entries.get(key)
            if ent and ent[0] == self._version:
                return ent[1], ent[2]
            version = self._version
        q = db.query(Chunk.id, Chunk.embedding).join(Paper, Paper.id == Chunk.paper_id).filter(
            Chunk.embedding.isnot(None), Chunk.embedding_model == model
        )
        if project_id:
            q = q.filter(Paper.project_id == project_id)
        ids: list[int] = []
        vecs: list[np.ndarray] = []
        for cid, blob in q:
            v = np.frombuffer(blob, dtype=np.float32)
            if v.size:
                ids.append(cid)
                vecs.append(v)
        if vecs:
            dim = vecs[0].size
            keep = [i for i, v in enumerate(vecs) if v.size == dim]
            mat = np.vstack([vecs[i] for i in keep]).astype(np.float32)
            ids = [ids[i] for i in keep]
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            mat = mat / norms
        else:
            mat = np.zeros((0, 1), dtype=np.float32)
        with self._lock:
            self._entries[key] = (version, mat, ids)
        return mat, ids


VECTOR_CACHE = _VectorCache()


def to_blob(vec: list[float]) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def keyword_search(db: Session, query: str, project_id: int | None, k: int) -> list[Hit]:
    terms = content_terms(query)
    if not terms:
        return []
    expr = fts_match_expr(raw_terms(query))
    sql_text = (
        "SELECT c.id, c.paper_id, c.page_number, c.text, bm25(chunk_fts) AS score "
        "FROM chunk_fts JOIN chunks c ON c.id = chunk_fts.rowid JOIN papers p ON p.id = c.paper_id "
        "WHERE chunk_fts MATCH :expr "
        + ("AND p.project_id = :pid " if project_id else "")
        + "ORDER BY score LIMIT :lim"
    )
    params: dict = {"expr": expr, "lim": max(k * 3, 20)}
    if project_id:
        params["pid"] = project_id
    rows = db.execute(sql(sql_text), params).all()
    hits = [
        Hit(chunk_id=r[0], paper_id=r[1], page=r[2], text=r[3], keyword=coverage(terms, r[3]), sources={"keyword"})
        for r in rows
    ]
    hits.sort(key=lambda h: (-h.keyword, ))  # coverage first; FTS order (bm25) is the stable tiebreak
    return hits[:k]


def semantic_search(
    db: Session, llm: LLMClient, query: str, project_id: int | None, k: int
) -> list[Hit]:
    qv = np.asarray(llm.embed([query])[0], dtype=np.float32)  # first, so "Ollama offline" is detected even with no index
    mat, ids = VECTOR_CACHE.get(db, project_id, llm.embed_model)
    if not ids:
        return []
    if qv.size != mat.shape[1]:
        return []
    n = np.linalg.norm(qv)
    qv = qv / (n if n else 1.0)
    sims = mat @ qv
    top = np.argsort(-sims)[:k]
    chunks = {c.id: c for c in db.query(Chunk).filter(Chunk.id.in_([ids[i] for i in top])).all()}
    terms = content_terms(query)
    out: list[Hit] = []
    for i in top:
        c = chunks.get(ids[i])
        if c:
            out.append(
                Hit(c.id, c.paper_id, c.page_number, c.text, semantic=float(sims[i]),
                    keyword=coverage(terms, c.text), sources={"semantic"})
            )
    return out


def search(
    db: Session, query: str, project_id: int | None, k: int, mode: str = "hybrid", llm: LLMClient | None = None
) -> RetrievalResult:
    """mode: keyword | semantic | hybrid. Falls back to keyword (and says so) when embeddings are unavailable."""
    terms = content_terms(query)
    kw = keyword_search(db, query, project_id, k * 2) if mode in ("keyword", "hybrid", "semantic") else []
    sem: list[Hit] = []
    degraded: str | None = None
    if mode in ("semantic", "hybrid") and llm is not None:
        try:
            sem = semantic_search(db, llm, query, project_id, k * 2)
            if not sem:
                degraded = "no_embeddings"
        except OllamaUnavailable:
            degraded = "ollama_offline"
        except OllamaError:
            degraded = "embedding_model_unavailable"
    elif mode in ("semantic", "hybrid"):
        degraded = "ollama_offline"

    if mode == "keyword" or not sem:
        return RetrievalResult(kw[:k], "keyword", degraded if mode != "keyword" else None, terms)

    merged: dict[int, Hit] = {}
    for rank, h in enumerate(sem):
        merged[h.chunk_id] = h
        h.rank_score += 1.0 / (60 + rank)
    for rank, h in enumerate(kw):
        if h.chunk_id in merged:
            merged[h.chunk_id].rank_score += 1.0 / (60 + rank)
            merged[h.chunk_id].sources.add("keyword")
        else:
            h.rank_score = 1.0 / (60 + rank)
            merged[h.chunk_id] = h
    ordered = sorted(merged.values(), key=lambda h: -h.rank_score)
    if mode == "semantic":
        ordered = [h for h in ordered if h.semantic is not None]
    return RetrievalResult(ordered[:k], "semantic" if mode == "semantic" else "hybrid", degraded, terms)
