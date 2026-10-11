from __future__ import annotations

import json

from app.services import llm as llm_mod
from app.services.chunking import chunk_document
from app.services.grounding import parse_model_answer
from app.services.text import best_quote, content_terms
from tests.conftest import FakeLLM


def test_health_and_auth_flow(client):
    assert client.get("/api/health").json()["setup_required"] is True
    assert client.get("/api/projects").status_code == 401
    assert client.post("/api/auth/setup", json={"name": "A", "password": "short"}).status_code == 422
    r = client.post("/api/auth/setup", json={"name": "Mira", "password": "long enough pw"})
    assert r.status_code == 200
    assert client.post("/api/auth/setup", json={"name": "B", "password": "another long pw"}).status_code == 409
    assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    ok = client.post("/api/auth/login", json={"password": "long enough pw"})
    assert ok.status_code == 200
    client.headers["Authorization"] = f"Bearer {ok.json()['token']}"
    assert client.get("/api/auth/me").json()["name"] == "Mira"
    assert len(client.get("/api/projects").json()) == 1


def test_upload_rejects_bad_files_and_duplicates(auth, project_id, sample_pdfs, fake_llm):
    _, pdf = sample_pdfs["position"]
    bad = auth.post(f"/api/projects/{project_id}/papers", files=[("files", ("x.pdf", b"not a pdf", "application/pdf"))])
    assert bad.json()["rejected"][0]["reason"] == "This file is not a valid PDF."
    txt = auth.post(f"/api/projects/{project_id}/papers", files=[("files", ("notes.txt", b"hello", "text/plain"))])
    assert "Only PDF" in txt.json()["rejected"][0]["reason"]
    ok = auth.post(f"/api/projects/{project_id}/papers", files=[("files", (pdf.name, pdf.read_bytes(), "application/pdf"))])
    assert ok.json()["papers"][0]["status"] == "ready"
    dup = auth.post(f"/api/projects/{project_id}/papers", files=[("files", (pdf.name, pdf.read_bytes(), "application/pdf"))])
    assert "Already in this project" in dup.json()["rejected"][0]["reason"]


def test_pipeline_pages_chunks_and_viewer_data(uploaded, auth):
    p = uploaded["adaptive-retrieval"]
    assert p["status"] == "ready" and p["page_count"] == 3 and p["chunk_count"] >= 3
    assert p["embedded_count"] == p["chunk_count"]
    assert p["title"].startswith("Adaptive Retrieval Depth")
    pages = auth.get(f"/api/papers/{p['id']}/pages").json()
    assert [x["number"] for x in pages] == [1, 2, 3]
    assert "44.5 exact match" in pages[2]["text"]
    assert auth.get(f"/api/papers/{p['id']}/file").headers["content-type"] == "application/pdf"


def test_pipeline_keyword_only_when_ollama_offline(auth, project_id, sample_pdfs):
    llm_mod.set_llm_factory(lambda db: FakeLLM(online=False))
    _, pdf = sample_pdfs["position"]
    r = auth.post(f"/api/projects/{project_id}/papers", files=[("files", (pdf.name, pdf.read_bytes(), "application/pdf"))])
    paper = r.json()["papers"][0]
    assert paper["status"] == "ready_keyword_only"
    assert "Reindex" in paper["detail"]
    res = auth.post("/api/search", json={"query": "position of the relevant passage", "mode": "keyword", "project_id": project_id}).json()
    assert res["total"] >= 1
    sem = auth.post("/api/search", json={"query": "position of the relevant passage", "mode": "semantic", "project_id": project_id}).json()
    assert sem["degraded"] == "ollama_offline" and sem["mode"] == "keyword"


def test_scanned_pdf_reports_no_text(auth, project_id, tmp_path, fake_llm):
    from reportlab.pdfgen import canvas

    p = tmp_path / "blank.pdf"
    c = canvas.Canvas(str(p))
    c.rect(50, 50, 100, 100)
    c.save()
    r = auth.post(f"/api/projects/{project_id}/papers", files=[("files", ("blank.pdf", p.read_bytes(), "application/pdf"))])
    assert r.json()["papers"][0]["status"] == "no_text"
    assert "scanned" in r.json()["papers"][0]["detail"].lower()


def test_search_keyword_and_semantic(uploaded, auth, project_id):
    kw = auth.post("/api/search", json={"query": "retrieval depth", "mode": "keyword", "project_id": project_id}).json()
    assert kw["total"] > 0 and kw["mode"] == "keyword"
    for r in kw["results"]:
        pages = auth.get(f"/api/papers/{r['paper_id']}/pages").json()
        page_text = next(p["text"] for p in pages if p["number"] == r["page"])
        assert r["quote"] in page_text  # every quote is a verbatim slice of the stored page
    sem = auth.post("/api/search", json={"query": "how many passages should be retrieved", "mode": "semantic", "project_id": project_id}).json()
    assert sem["mode"] in ("semantic", "keyword") and sem["total"] >= 0


def _answer_script(used: list[int], text: str, sufficient: bool = True):
    return lambda system, user: json.dumps({"sufficient": sufficient, "answer": text, "used": used})


def test_grounded_answer_resolves_citations_in_backend(uploaded, auth, project_id, fake_llm):
    fake_llm.script = _answer_script([1], "Adaptive Retrieval reports 44.5 exact match [1]. Another claim [9].")
    t = auth.post("/api/threads", json={"project_id": project_id}).json()
    r = auth.post(f"/api/threads/{t['id']}/messages", json={"content": "What exact match does Adaptive Retrieval obtain on Natural Questions?"}).json()
    a = r["assistant"]
    assert a["status"] == "answered"
    assert "[9]" not in a["content"] and "[1]" in a["content"]  # invented markers are stripped
    assert len(a["citations"]) == 1
    c = a["citations"][0]
    pages = auth.get(f"/api/papers/{c['paper_id']}/pages").json()
    assert c["quote"] in next(p["text"] for p in pages if p["number"] == c["page"])
    assert c["paper_title"] and c["page"] >= 1
    assert auth.get(f"/api/threads/{t['id']}").json()["title"].startswith("What exact match")


def test_model_cannot_cite_nonexistent_excerpts():
    parsed = parse_model_answer(json.dumps({"sufficient": True, "answer": "x [4]", "used": [4, 99, 0, "a"]}), 3)
    assert parsed == (True, "x [4]", [])


def test_unsupported_question_is_insufficient_without_llm_call(uploaded, auth, project_id, fake_llm):
    fake_llm.script = _answer_script([1], "should never be used")
    before = len(fake_llm.calls)  # extraction runs its own LLM pass at upload time; only the question matters here
    t = auth.post("/api/threads", json={"project_id": project_id}).json()
    r = auth.post(f"/api/threads/{t['id']}/messages", json={"content": "What is the boiling point of tungsten in kelvin?"}).json()
    assert r["assistant"]["status"] == "insufficient"
    assert r["assistant"]["citations"] == []
    assert len(fake_llm.calls) == before


def test_model_can_refuse_even_with_related_passages(uploaded, auth, project_id, fake_llm):
    fake_llm.script = _answer_script([], "", sufficient=False)
    t = auth.post("/api/threads", json={"project_id": project_id}).json()
    r = auth.post(f"/api/threads/{t['id']}/messages", json={"content": "Does adaptive retrieval eliminate hallucinations in clinical decision support?"}).json()
    assert r["assistant"]["status"] == "insufficient"


def test_offline_ollama_returns_extractive_passages(uploaded, auth, project_id):
    llm_mod.set_llm_factory(lambda db: FakeLLM(online=False))
    t = auth.post("/api/threads", json={"project_id": project_id}).json()
    r = auth.post(f"/api/threads/{t['id']}/messages", json={"content": "What retrieval depth does adaptive retrieval use by default?"}).json()
    a = r["assistant"]
    assert a["status"] == "offline" and a["citations"], a
    assert "Ollama" in a["content"]


def test_reading_mode_points_to_papers_without_llm(uploaded, auth, project_id, fake_llm):
    before = len(fake_llm.calls)
    t = auth.post("/api/threads", json={"project_id": project_id}).json()
    r = auth.post(f"/api/threads/{t['id']}/messages", json={"content": "retrieval depth and random seeds", "reading_mode": True}).json()
    a = r["assistant"]
    assert a["status"] == "reading" and "Read" in a["content"] and a["citations"]
    assert len(fake_llm.calls) == before


def test_copilot_uses_a_persistent_thread(uploaded, auth, project_id, fake_llm):
    fake_llm.script = _answer_script([1], "Reported as 44.5 [1].")
    a = auth.post("/api/copilot/ask", json={"project_id": project_id, "question": "adaptive retrieval exact match natural questions"}).json()
    b = auth.post("/api/copilot/ask", json={"project_id": project_id, "question": "adaptive retrieval exact match natural questions again"}).json()
    assert a["thread_id"] == b["thread_id"]


def test_delete_paper_removes_search_hits(uploaded, auth, project_id):
    p = uploaded["position"]
    assert auth.post("/api/search", json={"query": "HotpotQA position-aware reranking", "mode": "keyword", "project_id": project_id}).json()["total"] > 0
    assert auth.delete(f"/api/papers/{p['id']}").status_code == 204
    assert auth.post("/api/search", json={"query": "HotpotQA position-aware reranking", "mode": "keyword", "project_id": project_id}).json()["total"] == 0


def test_settings_validation_and_ollama_test(auth, fake_llm):
    assert auth.put("/api/settings", json={"ollama_url": "ftp://x"}).status_code == 422
    assert auth.put("/api/settings", json={"tolerance": 99}).status_code == 422
    s = auth.put("/api/settings", json={"online_discovery": True, "tolerance": 8}).json()
    assert s["online_discovery"] is True and s["tolerance"] == 8
    assert auth.post("/api/system/ollama/test", json={}).status_code == 200


def test_export_and_delete_all(uploaded, auth):
    z = auth.post("/api/data/export")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    assert auth.request("DELETE", "/api/data", json={"confirm": "nope"}).status_code == 422
    assert auth.request("DELETE", "/api/data", json={"confirm": "DELETE"}).json()["deleted"] is True
    assert auth.get("/api/health").json()["setup_required"] is True


def test_chunks_never_cross_pages_and_are_verbatim():
    pages = ["First sentence here. Second sentence follows it. " * 30, "Other page text. " * 20]
    specs = chunk_document([" ".join(p.split()) for p in pages], 300, 60)
    assert {s.page_number for s in specs} == {1, 2}
    for s in specs:
        assert s.text in " ".join(pages[s.page_number - 1].split())


def test_text_helpers():
    assert "retrieval" in content_terms("What does the retrieval depth do?")
    q = best_quote("A one. " * 40 + "The retriever returns five passages per question. " + "B two. " * 40, content_terms("retriever passages"), 120)
    assert "retriever" in q and len(q) <= 120
