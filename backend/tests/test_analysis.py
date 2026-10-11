"""Tests for extraction review, comparison, integrity checks, discovery, evaluation and the think-first features."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.services import discovery
from app.services.discovery import Candidate
from eval.samples import make_pdf

ENDPOINTS_NEEDING_AUTH = [
    "/api/projects/1/overview", "/api/projects/1/extraction", "/api/projects/1/contradictions", "/api/projects/1/gaps",
    "/api/projects/1/reading", "/api/projects/1/decisions", "/api/projects/1/predictions", "/api/projects/1/provenance",
    "/api/projects/1/receipts", "/api/projects/1/eval/runs", "/api/papers/1/fields", "/api/papers/1/numeric",
    "/api/papers/1/reproducibility", "/api/projects/1/citation-audit",
]


def _norm(s: str) -> str:
    return " ".join(s.split()).lower()


def assert_quote_in_paper(auth, paper_id: int, page: int | None, quote: str) -> None:
    """The product rule: every quote shown to the user is a verbatim slice of the stored page text."""
    pages = auth.get(f"/api/papers/{paper_id}/pages").json()
    haystack = [p for p in pages if page is None or p["number"] == page]
    assert haystack, f"page {page} missing for paper {paper_id}"
    assert any(_norm(quote) in _norm(p["text"]) for p in haystack), f"not verbatim: {quote!r} (paper {paper_id}, p.{page})"


def upload_one(auth, project_id: int, path: Path) -> dict:
    r = auth.post(f"/api/projects/{project_id}/papers", files=[("files", (path.name, path.read_bytes(), "application/pdf"))])
    assert r.status_code == 201, r.text
    assert not r.json()["rejected"], r.json()
    return r.json()["papers"][0]


@pytest.mark.parametrize("raw,title,expected", [
    ("Adaptive Retrieval Depth for Open-Domain Question Answering\nA. Rowan, K. Mehta. 2024.\nAbstract. We study", "Adaptive Retrieval Depth for Open-Domain Question Answering", "A. Rowan, K. Mehta"),
    ("Position Sensitivity\nJane Doe and John Smith\nAbstract", "Position Sensitivity", "Jane Doe, John Smith"),
    ("Attention Is All You Need\nAshish Vaswani1, Noam Shazeer1\nAbstract", "Attention Is All You Need", "Ashish Vaswani, Noam Shazeer"),
    ("Position Sensitivity\nAbstract", "Position Sensitivity", ""),                       # no byline: do not mistake the title for names
    ("Deep Nets\nStanford University\nDepartment of Computer Science\nAbstract", "Deep Nets", ""),
    ("Deep Nets\nProceedings of the Thirty-Ninth Conference\nAbstract", "Deep Nets", ""),
    ("Deep Nets\njane@example.com\nAbstract", "Deep Nets", ""),
])
def test_author_byline_guess_is_conservative(raw, title, expected):
    from app.services.pdf import guess_authors
    assert guess_authors(raw, title) == expected


def test_uploaded_papers_get_authors_from_their_byline(uploaded):
    assert uploaded["adaptive-retrieval"]["authors"] == "A. Rowan, K. Mehta"
    assert uploaded["replication"]["authors"].startswith("N. Okafor")


def test_every_analysis_endpoint_requires_sign_in(client):
    for url in ENDPOINTS_NEEDING_AUTH:
        assert client.get(url).status_code == 401, url
    assert client.post("/api/projects/1/overclaim", json={"text": "x"}).status_code == 401


# ------------------------------------------------------------------ extraction + two-pass agreement


def _pass_b_script(system: str, user: str) -> str:
    """A fake model: correct on Method and Hardware, wrong on Seeds, and invents a quote for Dataset."""
    return json.dumps({
        "Method": {"value": "Adaptive Retrieval", "quote": "Adaptive Retrieval chooses the number of passages for every question.", "page": 2},
        "Hardware": {"value": "4 NVIDIA A100 GPUs", "quote": "Training used 4 NVIDIA A100 GPUs.", "page": 2},
        "Seeds": {"value": "5", "quote": "All results are averaged over 3 random seeds.", "page": 2},
        "Dataset": {"value": "TriviaQA", "quote": "We evaluate on TriviaQA with a custom split nobody wrote.", "page": 2},
    })


def test_two_pass_agreement_only_accepts_matching_verified_fields(auth, project_id, sample_pdfs, fake_llm):
    fake_llm.script = _pass_b_script
    _, path = sample_pdfs["adaptive-retrieval"]
    paper = upload_one(auth, project_id, path)
    data = auth.get(f"/api/papers/{paper['id']}/fields").json()
    by = {f["name"]: f for f in data["fields"]}
    assert by["Method"]["status"] == "agree" and by["Hardware"]["status"] == "agree"
    assert by["Seeds"]["status"] == "verify", "passes disagree (3 vs 5), so a human must check"
    assert by["Seeds"]["pass_a"]["value"] and by["Seeds"]["pass_b"]["value"] == "5"
    assert by["Dataset"]["status"] == "verify" and not by["Dataset"]["pass_b"], "an invented quote must be discarded"
    assert 0 < data["agreement_rate"] < 1
    for f in data["fields"]:
        if f["quote"]:
            assert_quote_in_paper(auth, paper["id"], f["page"], f["quote"])


def test_review_actions_are_stored_and_survive_reextraction(uploaded, auth):
    pid = uploaded["adaptive-retrieval"]["id"]
    fields = {f["name"]: f for f in auth.get(f"/api/papers/{pid}/fields").json()["fields"]}
    seeds = fields["Seeds"]
    r = auth.patch(f"/api/fields/{seeds['id']}", json={"action": "edit", "value": "3 seeds (checked)"})
    assert r.status_code == 200
    assert {f["name"]: f for f in r.json()["fields"]}["Seeds"]["status"] == "edited"
    assert auth.patch(f"/api/fields/{seeds['id']}", json={"action": "edit", "value": "  "}).status_code == 422
    meth = fields["Method"]
    assert auth.patch(f"/api/fields/{meth['id']}", json={"action": "confirm"}).status_code == 200
    assert auth.patch(f"/api/fields/{fields['Hardware']['id']}", json={"action": "reject"}).status_code == 200
    again = auth.post(f"/api/papers/{pid}/extract").json()
    by = {f["name"]: f for f in again["fields"]}
    assert by["Seeds"]["value"] == "3 seeds (checked)" and by["Seeds"]["status"] == "edited"
    assert by["Method"]["status"] == "confirmed" and by["Hardware"]["status"] == "rejected"
    assert again["counts"]["reviewed"] >= 3
    assert auth.patch("/api/fields/999999", json={"action": "confirm"}).status_code == 404


def test_project_extraction_filter_verify_only(uploaded, auth, project_id):
    allf = auth.get(f"/api/projects/{project_id}/extraction").json()
    ver = auth.get(f"/api/projects/{project_id}/extraction?only=verify").json()
    assert len(allf["papers"]) == 4
    assert all(f["status"] == "verify" for p in ver["papers"] for f in p["fields"])
    assert auth.get(f"/api/projects/{project_id}/extraction?only=bogus").status_code == 422


# ------------------------------------------------------------------ diff + contradictions


def test_paper_diff_highlights_differences_with_quotes(uploaded, auth, project_id):
    a, b = uploaded["adaptive-retrieval"]["id"], uploaded["replication"]["id"]
    d = auth.post(f"/api/projects/{project_id}/diff", json={"paper_ids": [a, b]}).json()
    rows = {r["field"]: r for r in d["rows"]}
    assert rows["Seeds"]["differs"] and rows["Hardware"]["differs"] and not rows["Dataset"]["differs"]
    for row in d["rows"]:
        for cell, paper in zip(row["cells"], d["papers"], strict=True):
            if cell["quote"]:
                assert_quote_in_paper(auth, paper["id"], cell["page"], cell["quote"])
    assert "does not indicate which paper is better" in d["note"]
    assert auth.post(f"/api/projects/{project_id}/diff", json={"paper_ids": [a]}).status_code == 422
    assert auth.post(f"/api/projects/{project_id}/diff", json={"paper_ids": [a, a]}).status_code == 422


def test_contradictions_use_tolerance_and_stay_cautious(uploaded, auth, project_id):
    c = auth.get(f"/api/projects/{project_id}/contradictions?tolerance=5").json()
    assert len(c["items"]) == 1
    item = c["items"][0]
    assert {item["a"]["display"], item["b"]["display"]} == {"44.5", "41.2"}
    assert item["key"]["dataset"] == "Natural Questions"
    assert item["setup_differences"] and item["possible_reasons"] and item["candidate_experiment"]
    assert "possibilities, not conclusions" in c["note"]
    for side in (item["a"], item["b"]):
        assert_quote_in_paper(auth, side["paper_id"], side["page"], side["quote"])
    assert auth.get(f"/api/projects/{project_id}/contradictions?tolerance=10").json()["items"] == []
    assert auth.get(f"/api/projects/{project_id}/contradictions?tolerance=-1").status_code == 422


# ------------------------------------------------------------------ integrity checks


def test_numeric_consistency_finds_abstract_vs_results_mismatch(uploaded, auth):
    r = auth.get(f"/api/papers/{uploaded['adaptive-retrieval']['id']}/numeric").json()
    assert len(r["mismatches"]) == 1
    m = r["mismatches"][0]
    assert {m["a"]["value"], m["b"]["value"]} == {"95%", "89.1%"}
    assert {m["a"]["section"], m["b"]["section"]} >= {"Abstract"}
    for side in (m["a"], m["b"]):
        assert_quote_in_paper(auth, uploaded["adaptive-retrieval"]["id"], side["page"], side["quote"])
    assert "not a finding of error" in r["note"]
    assert r["disclaimer"].startswith("Analytical estimate")


def test_reproducibility_lists_reported_and_missing(uploaded, auth):
    r = auth.get(f"/api/papers/{uploaded['position']['id']}/reproducibility").json()
    assert {i["status"] for i in r["items"]} <= {"reported", "partial", "missing"}
    assert sum(r["counts"].values()) == len(r["items"]) == 8
    for i in r["items"]:
        if i["quote"]:
            assert_quote_in_paper(auth, uploaded["position"]["id"], i["page"], i["quote"])


def test_overclaim_flags_wording_and_quotes_the_draft_without_a_verdict(uploaded, auth, project_id):
    text = "Our method always improves faithfulness across all datasets. The model is state-of-the-art. We ran an ablation."
    r = auth.post(f"/api/projects/{project_id}/overclaim", json={"text": text}).json()
    assert [f["sentence"] for f in r["findings"]] == [
        "Our method always improves faithfulness across all datasets.", "The model is state-of-the-art."]
    first = r["findings"][0]
    assert {w["term"].lower() for w in first["wording"]} >= {"always", "across all"}
    assert text[first["start"]:first["end"]] == first["sentence"]
    assert first["evidence"] and first["questions"]
    assert not {"score", "verdict", "rating"} & set(r) and not {"score", "verdict"} & set(first)
    assert r["sentences_checked"] == 3
    assert auth.post(f"/api/projects/{project_id}/overclaim", json={"text": ""}).status_code == 422


def test_library_and_draft_citation_audit(auth, project_id, sample_pdfs, tmp_path, fake_llm):
    _, base = sample_pdfs["adaptive-retrieval"]
    upload_one(auth, project_id, base)
    citing = tmp_path / "citing.pdf"
    make_pdf(citing, [[
        "A Survey of Retrieval Depth Choices",
        "B. Citer. 2025.",
        "Rowan et al. (2024) report that adaptive retrieval chooses the number of passages for every question. "
        "We build on this idea in the survey.",
    ]])
    paper = upload_one(auth, project_id, citing)
    audit = auth.get(f"/api/projects/{project_id}/citation-audit").json()
    assert audit["items"], "a library paper citing 'Rowan et al. (2024)' should be matched to the Rowan 2024 paper"
    row = audit["items"][0]
    assert row["citing_paper"]["paper_id"] == paper["id"] and "Rowan" in row["cited"]["label"]
    assert_quote_in_paper(auth, row["cited"]["paper_id"], row["passage"]["page"], row["passage"]["quote"])
    assert "No verdict" in audit["note"] and "verdict" not in {k for k in row}
    cited_id = row["cited"]["paper_id"]
    draft = auth.post(f"/api/projects/{project_id}/citation-audit", json={
        "text": "Adaptive retrieval chooses the number of passages per question [1].", "mapping": {"1": cited_id}}).json()
    assert draft["items"] and draft["items"][0]["marker"] == "[1]"


# ------------------------------------------------------------------ discovery + reading list + prior work


def test_discovery_is_local_only_unless_online_is_enabled(uploaded, auth, project_id, monkeypatch):
    sent: list[list[str]] = []

    def fake_external(queries):  # noqa: ANN001, ANN202
        sent.append(list(queries))
        cand = Candidate(title="A Study of Retrieval Depth", authors="Q. Writer", year=2022, venue="ExampleConf",
                         url="https://example.org/p", abstract="We propose a depth selector. It reduces latency on open-domain QA.",
                         source="OpenAlex")
        return [cand], {"OpenAlex": {"ok": 1, "failed": 0, "reason": ""}, "Semantic Scholar": {"ok": 0, "failed": 1, "reason": "rate limited"},
                        "arXiv": {"ok": 0, "failed": 0, "reason": ""}}

    monkeypatch.setattr(discovery, "query_external", fake_external)
    body = {"text": "adaptive retrieval depth for question answering"}
    off = auth.post(f"/api/projects/{project_id}/discover", json=body).json()
    assert sent == [], "no external call may happen while Online discovery is off"
    assert off["online"] is False and off["sources_searched"] == ["Your local library"]
    assert any("online discovery is off" in s for s in off["sources_not_searched"])
    assert off["notice"] == "Absence of results is not evidence of novelty."
    assert all("supports" not in json.dumps(r).lower() and "contradict" not in json.dumps(r).lower() for r in off["results"])

    assert auth.put("/api/settings", json={"online_discovery": True}).json()["online_discovery"] is True
    on = auth.post(f"/api/projects/{project_id}/discover", json={**body, "queries": ["retrieval depth selection", "adaptive top-k"]}).json()
    assert sent == [["retrieval depth selection", "adaptive top-k"]], "only short queries are sent, never paper text"
    assert max(len(q) for q in sent[0]) < 60
    ext = [r for r in on["results"] if r["source"] == "OpenAlex"]
    assert ext and ext[0]["why"] == "It reduces latency on open-domain QA." or ext[0]["why"].startswith("We propose")
    assert "OpenAlex" in on["sources_searched"] and any("Semantic Scholar" in s and "rate limited" in s for s in on["sources_not_searched"])
    assert len(auth.get(f"/api/projects/{project_id}/receipts").json()) == 2
    assert auth.get(f"/api/receipts/{on['id']}").json()["queries"] == ["retrieval depth selection", "adaptive top-k"]
    assert auth.post(f"/api/projects/{project_id}/discover", json={"text": "x"}).status_code == 422


def test_reading_list_save_update_delete(auth, project_id):
    item = {"title": "A Study of Retrieval Depth", "authors": "Q. Writer", "year": 2022, "tags": ["methodology"], "why": "It reduces latency."}
    a = auth.post(f"/api/projects/{project_id}/reading", json=item)
    assert a.status_code == 201
    again = auth.post(f"/api/projects/{project_id}/reading", json={**item, "title": "a study of retrieval depth"}).json()
    assert again["id"] == a.json()["id"], "saving the same paper twice must not duplicate it"
    upd = auth.patch(f"/api/reading/{a.json()['id']}", json={"status": "read", "note": "Check section 3"}).json()
    assert upd["status"] == "read" and upd["note"] == "Check section 3"
    assert auth.patch(f"/api/reading/{a.json()['id']}", json={"status": "finished"}).status_code == 422
    assert len(auth.get(f"/api/projects/{project_id}/reading").json()) == 1
    assert auth.delete(f"/api/reading/{a.json()['id']}").status_code == 204
    assert auth.get(f"/api/projects/{project_id}/reading").json() == []


def test_prior_work_has_receipt_and_the_required_notice_and_no_score(uploaded, auth, project_id):
    r = auth.post(f"/api/projects/{project_id}/prior-work", json={"idea": "choose retrieval depth per question adaptively"}).json()
    assert "Not a legal or patentability opinion. No novelty score." in r["notices"]
    assert r["receipt"]["kind"] == "prior_work" and r["receipt"]["sources_not_searched"]
    assert "novelty" not in {k.lower() for k in r} - {"notices"} and not any("score" in k for k in r)
    assert r["closest"] and "overlap" in r["closest"][0]


# ------------------------------------------------------------------ gaps + evaluation + overview


def test_gap_map_clusters_quote_their_sources(uploaded, auth, project_id):
    g = auth.get(f"/api/projects/{project_id}/gaps").json()
    assert g["label"] == "Candidate gaps for you to evaluate" and g["clusters"]
    for c in g["clusters"]:
        for s in c["statements"]:
            assert_quote_in_paper(auth, s["paper_id"], s["page"], s["quote"])
    assert auth.get(f"/api/projects/{project_id}/gaps?threshold=2").status_code == 422


def test_evaluation_runs_and_reports(uploaded, auth, project_id):
    assert auth.post(f"/api/projects/{project_id}/eval/run", json={}).status_code == 409, "no questions loaded yet"
    assert auth.post(f"/api/projects/{project_id}/eval/samples").json()["questions"] == 22
    run = auth.post(f"/api/projects/{project_id}/eval/run", json={"k": 10}).json()
    m = run["metrics"]
    assert run["n_questions"] == 22 and m["answerable"] == 16 and m["unanswerable"] == 6 and m["papers"] == 4
    assert m["recall_at_k"] == 1.0 and 0 < m["mrr"] <= 1 and m["refusal_accuracy"] == 1.0
    assert m["extraction"]["n_papers"] == 4 and m["extraction"]["overall"] >= 0.9
    assert len(run["details"]) == 22
    hist = auth.get(f"/api/projects/{project_id}/eval/runs").json()
    assert len(hist) == 1 and "details" not in hist[0]
    md = auth.get(f"/api/eval/runs/{run['id']}/report.md")
    assert md.status_code == 200 and "| Recall@10 |" in md.text and "Refusal accuracy" in md.text
    assert auth.post(f"/api/projects/{project_id}/eval/run", json={"k": 99}).status_code == 422


def test_overview_summarises_the_project(uploaded, auth, project_id):
    o = auth.get(f"/api/projects/{project_id}/overview").json()
    assert o["stats"]["papers"] == 4 and o["stats"]["pages"] == 12 and o["stats"]["fields_extracted"] > 20
    assert o["contradiction_total"] == 1 and o["contradictions"][0]["title"].startswith("Natural Questions")
    assert o["privacy"]["online_discovery"] is False
    assert o["index"]["chunks"] > 0 and o["index"]["embedded"] == o["index"]["chunks"]
    assert o["extraction_health"]["verify"] == o["stats"]["awaiting_review"]
    assert auth.get("/api/projects/9999/overview").status_code == 404


# ------------------------------------------------------------------ think-first: decisions


def _first_quote(auth, paper_id: int, needle: str) -> tuple[int, str]:
    for p in auth.get(f"/api/papers/{paper_id}/pages").json():
        m = re.search(rf"[^.]*{re.escape(needle)}[^.]*\.", p["text"].replace("\n", " "))
        if m:
            return p["number"], m.group(0).strip()
    raise AssertionError(needle)


def test_decision_requires_real_evidence_and_raises_alert_when_a_new_paper_differs(auth, project_id, sample_pdfs, fake_llm):
    _, first = sample_pdfs["adaptive-retrieval"]
    p1 = upload_one(auth, project_id, first)
    page, quote = _first_quote(auth, p1["id"], "44.5 exact match")
    bad = auth.post(f"/api/projects/{project_id}/decisions", json={
        "title": "Use Adaptive Retrieval", "method": "Adaptive Retrieval", "dataset": "Natural Questions", "metric": "exact match",
        "evidence": [{"paper_id": p1["id"], "page": page, "quote": "Adaptive Retrieval obtains 99.9 exact match on everything."}]})
    assert bad.status_code == 422 and "not found" in bad.json()["detail"]
    ok = auth.post(f"/api/projects/{project_id}/decisions", json={
        "title": "Use Adaptive Retrieval", "rationale": "Best exact match on NQ in the library.", "method": "Adaptive Retrieval",
        "dataset": "Natural Questions", "metric": "exact match", "evidence": [{"paper_id": p1["id"], "page": page, "quote": quote}]})
    assert ok.status_code == 201 and ok.json()["open_alerts"] == 0
    did = ok.json()["id"]

    _, second = sample_pdfs["replication"]
    p2 = upload_one(auth, project_id, second)
    d = auth.get(f"/api/projects/{project_id}/decisions").json()[0]
    assert d["id"] == did and d["open_alerts"] == 1
    alert = d["alerts"][0]
    assert alert["paper_id"] == p2["id"] and "Re-read both" in alert["message"] and "wrong" not in alert["message"].lower()
    assert_quote_in_paper(auth, p2["id"], alert["quote"]["page"], alert["quote"]["quote"])
    assert_quote_in_paper(auth, p1["id"], alert["quote"]["baseline"]["page"], alert["quote"]["baseline"]["quote"])
    ov = auth.get(f"/api/projects/{project_id}/overview").json()
    assert ov["alerts"] and ov["alerts"][0]["decision_title"] == "Use Adaptive Retrieval"
    assert auth.post(f"/api/alerts/{alert['id']}/resolve").json()["resolved"] is True
    assert auth.get(f"/api/projects/{project_id}/decisions").json()[0]["open_alerts"] == 0
    assert auth.delete(f"/api/decisions/{did}").status_code == 204


def test_decision_created_after_papers_is_checked_against_the_library(uploaded, auth, project_id):
    p1 = uploaded["adaptive-retrieval"]["id"]
    page, quote = _first_quote(auth, p1, "44.5 exact match")
    r = auth.post(f"/api/projects/{project_id}/decisions", json={
        "title": "Report NQ exact match", "method": "Adaptive Retrieval", "dataset": "Natural Questions", "metric": "exact match",
        "evidence": [{"paper_id": p1, "page": page, "quote": quote}]}).json()
    assert r["open_alerts"] == 1, "the replication paper already in the library disagrees"


# ------------------------------------------------------------------ think-first: prediction gate


def test_prediction_gate_compares_without_verdicts(uploaded, auth, project_id):
    ids = [uploaded["adaptive-retrieval"]["id"], uploaded["replication"]["id"]]
    good = auth.post(f"/api/projects/{project_id}/predictions", json={
        "paper_ids": ids, "prediction": "Adaptive Retrieval gets 44.5 exact match on Natural Questions in the first paper but only 41.2 in the replication."})
    assert good.status_code == 201
    g = good.json()
    assert g["matched"] and not g["check_reading"]
    assert any(m["field"] == "Result" for m in g["matched"])
    assert g["possibly_missed"], "the setup differences (seeds, hardware, depth) were not mentioned"
    wrong = auth.post(f"/api/projects/{project_id}/predictions", json={
        "paper_ids": ids, "prediction": "Adaptive Retrieval should reach about 60 exact match on Natural Questions."}).json()
    assert wrong["check_reading"], "60 matches no reported exact-match value"
    ev = wrong["check_reading"][0]["evidence"][0]
    assert_quote_in_paper(auth, ev["paper_id"], ev["page"], ev["quote"])
    for item in g["matched"] + g["possibly_missed"] + wrong["check_reading"]:
        assert item["evidence"], "every statement must carry evidence"
        for e in item["evidence"]:
            if e["quote"]:
                assert_quote_in_paper(auth, e["paper_id"], e["page"], e["quote"])
    text = json.dumps([g, wrong]).lower()
    assert "incorrect" not in text and "you are right" not in text and "you are wrong" not in text
    assert g["note"].startswith("Analytical estimate, not proof")
    hist = auth.get(f"/api/projects/{project_id}/predictions").json()
    assert len(hist) == 2 and hist[0]["counts"]["matched"] >= 0
    assert auth.get(f"/api/predictions/{g['id']}").json()["prediction"].startswith("Adaptive Retrieval gets 44.5")
    saved = auth.patch(f"/api/predictions/{g['id']}", json={"reflection": "  The setups differ more than I assumed.  "}).json()
    assert saved["reflection"] == "The setups differ more than I assumed."
    assert auth.get(f"/api/predictions/{g['id']}").json()["reflection"] == saved["reflection"]
    assert auth.patch("/api/predictions/9999", json={"reflection": "x"}).status_code == 404
    assert auth.post(f"/api/projects/{project_id}/predictions", json={"paper_ids": [9999], "prediction": "A long enough prediction text."}).status_code == 422
    assert auth.post(f"/api/projects/{project_id}/predictions", json={"paper_ids": ids, "prediction": "short"}).status_code == 422


def test_project_think_first_toggle_persists(auth, project_id):
    assert auth.get(f"/api/projects/{project_id}").json()["think_first"] is False
    assert auth.patch(f"/api/projects/{project_id}", json={"think_first": True}).json()["think_first"] is True
    assert auth.get(f"/api/projects/{project_id}").json()["think_first"] is True


# ------------------------------------------------------------------ think-first: provenance log


def test_provenance_records_only_user_marks(auth, project_id):
    doc = auth.post(f"/api/projects/{project_id}/provenance", json={"title": "Draft", "content": "Alpha beta gamma delta epsilon."})
    assert doc.status_code == 201
    d = doc.json()
    assert d["note"] == "This tool records your own marking. It does not detect AI text."
    assert [e["kind"] for e in d["events"]] == ["created"] and d["marked_words"] == 0
    r = auth.patch(f"/api/provenance/{d['id']}", json={"marks": [{"start": 0, "end": 10}, {"start": 5, "end": 16}, {"start": 500, "end": 600}]}).json()
    assert r["marks"] == [{"start": 0, "end": 16, "text": "Alpha beta gamma"}], "overlaps merge; out-of-range marks are dropped"
    assert r["marked_words"] == 3 and r["words"] == 5
    assert r["events"][0]["kind"] == "ai_marked" and r["events"][0]["passage"] == "Alpha beta gamma"
    r2 = auth.patch(f"/api/provenance/{d['id']}", json={"marks": []}).json()
    assert r2["marks"] == [] and r2["events"][0]["kind"] == "ai_unmarked"
    r3 = auth.patch(f"/api/provenance/{d['id']}", json={"content": "Alpha beta gamma delta epsilon zeta eta."}).json()
    assert r3["events"][0]["kind"] == "edited" and r3["events"][0]["words"] == 2
    csv_text = auth.get(f"/api/provenance/{d['id']}/export.csv")
    assert csv_text.headers["content-type"].startswith("text/csv")
    lines = csv_text.text.strip().splitlines()
    assert lines[0] == "timestamp,event,words,passage" and len(lines) == 1 + len(r3["events"])
    assert auth.get(f"/api/provenance/{d['id']}/export.json").json()["events"]
    assert len(auth.get(f"/api/projects/{project_id}/provenance").json()) == 1
    assert auth.delete(f"/api/provenance/{d['id']}").status_code == 204
    assert auth.get(f"/api/provenance/{d['id']}").status_code == 404
    assert auth.patch(f"/api/provenance/{d['id']}", json={"marks": [{"start": 4, "end": 2}]}).status_code in (404, 422)


def test_provenance_rejects_bad_marks(auth, project_id):
    d = auth.post(f"/api/projects/{project_id}/provenance", json={"content": "some text"}).json()
    assert auth.patch(f"/api/provenance/{d['id']}", json={"marks": [{"start": -1, "end": 3}]}).status_code == 422
    assert auth.patch(f"/api/provenance/{d['id']}", json={"marks": [{"start": 4, "end": 2}]}).json()["marks"] == []


# ------------------------------------------------------------------ data deletion covers the new tables


def test_delete_all_removes_think_first_data(uploaded, auth, project_id):
    auth.post(f"/api/projects/{project_id}/reading", json={"title": "X"})
    auth.post(f"/api/projects/{project_id}/provenance", json={"content": "abc def"})
    assert auth.request("DELETE", "/api/data", json={"confirm": "nope"}).status_code == 422
    assert auth.request("DELETE", "/api/data", json={"confirm": "DELETE"}).json()["deleted"] is True
    assert auth.get("/api/health").json()["setup_required"] is True


def test_sentence_splitter_keeps_citations_and_initials_together():
    from app.services.text import split_sentences
    assert split_sentences("Rowan et al. (2024) report this. We agree.") == ["Rowan et al. (2024) report this.", "We agree."]
    assert split_sentences("See Fig. 3 for details. Next we test.") == ["See Fig. 3 for details.", "Next we test."]
    assert split_sentences("We use e.g. DPR. It works.") == ["We use e.g. DPR.", "It works."]
    assert split_sentences("Accuracy was 95.0%. Results hold.") == ["Accuracy was 95.0%.", "Results hold."]
