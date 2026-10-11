"""Test fixtures: temp database per test, inline pipeline, and a fake Ollama (no network needed)."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_TMP = Path(tempfile.mkdtemp(prefix="rm-tests-"))
os.environ["RM_DATA_DIR"] = str(_TMP)
os.environ["RM_PROCESS_INLINE"] = "true"
os.environ["RM_SECRET_KEY"] = "test-secret-key-test-secret-key-0123456789"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import init_engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.migrate import upgrade_to_head  # noqa: E402
from app.services import llm as llm_mod  # noqa: E402
from app.services.ollama import OllamaUnavailable  # noqa: E402
from app.services.retrieval import VECTOR_CACHE  # noqa: E402
from eval.samples import write_samples  # noqa: E402

DIM = 96


def _vec(text: str) -> list[float]:
    """Deterministic bag-of-words embedding so semantic search is testable without a model."""
    v = np.zeros(DIM, dtype=np.float32)
    for tok in text.lower().split():
        tok = "".join(c for c in tok if c.isalnum())
        if len(tok) < 3:
            continue
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        v[h % DIM] += 1.0
    n = np.linalg.norm(v)
    return (v / n if n else v).tolist()


class FakeLLM:
    """Stands in for Ollama. `script` receives (system, user) and returns the JSON string to emit."""

    answer_model = "fake-chat"
    embed_model = "fake-embed"

    def __init__(self, online: bool = True, script=None, embeddings: bool = True) -> None:  # noqa: ANN001
        self.online, self.script, self.embeddings = online, script, embeddings
        self.calls: list[tuple[str, str]] = []

    def _check(self) -> None:
        if not self.online:
            raise OllamaUnavailable("Cannot reach Ollama (fake offline).")

    def version(self) -> str:
        self._check()
        return "0.0-fake"

    def list_models(self) -> list[str]:
        self._check()
        return ["fake-chat", "fake-embed"]

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._check()
        if not self.embeddings:
            raise OllamaUnavailable("no embeddings")
        return [_vec(t) for t in texts]

    def chat_json(self, system: str, user: str, schema) -> str:  # noqa: ANN001
        self._check()
        self.calls.append((system, user))
        if self.script:
            return self.script(system, user)
        return json.dumps({"sufficient": False, "answer": "", "used": []})


@pytest.fixture()
def fake_llm():
    fake = FakeLLM()
    llm_mod.set_llm_factory(lambda db: fake)
    yield fake
    llm_mod.set_llm_factory(None)


@pytest.fixture()
def client(tmp_path):
    get_settings.cache_clear()
    cfg = get_settings()
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    init_engine(url)
    upgrade_to_head(url)
    for f in cfg.papers_dir.glob("*"):
        f.unlink()
    VECTOR_CACHE.bump()
    app = create_app()
    c = TestClient(app)
    yield c
    llm_mod.set_llm_factory(None)


@pytest.fixture()
def auth(client):
    r = client.post("/api/auth/setup", json={"name": "Test User", "password": "correct horse"})
    assert r.status_code == 200, r.text
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return client


@pytest.fixture()
def project_id(auth):
    return auth.get("/api/projects").json()[0]["id"]


@pytest.fixture(scope="session")
def sample_pdfs():
    d = Path(tempfile.mkdtemp(prefix="rm-pdfs-"))
    items = write_samples(d)
    yield {spec["slug"]: (spec, path) for spec, path in items}
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def uploaded(auth, project_id, sample_pdfs, fake_llm):
    """All four sample papers uploaded and processed. Returns {slug: paper_json}."""
    files = [("files", (p.name, p.read_bytes(), "application/pdf")) for _, p in sample_pdfs.values()]
    r = auth.post(f"/api/projects/{project_id}/papers", files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert not body["rejected"], body
    by_slug = {}
    for paper in body["papers"]:
        for slug, (spec, path) in sample_pdfs.items():
            if paper["filename"] == path.name:
                by_slug[slug] = auth.get(f"/api/papers/{paper['id']}").json()
    return by_slug
