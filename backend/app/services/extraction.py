"""Structured extraction with Two-Pass Agreement.

Pass A is deterministic (regex / lexicons / tables). Pass B is an LLM constrained to a JSON schema. A field is
auto-accepted ("agree") only when both passes found it, their values match, and the quote is a verbatim slice of the
paper's own page text. Everything else is flagged "verify" for the human, with both candidates kept.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..models import ExtractedField, Page, Paper, ResultRow, utcnow
from .llm import get_llm
from .ollama import LLMClient, OllamaError, OllamaUnavailable, parse_json_object
from .results import DATASET_LEXICON, METRIC_WORDS, Claim, norm_dataset, norm_method, norm_metric, parse_paper_claims, split_sentences
from .text import coverage, content_terms, tokens

log = logging.getLogger("researchmind.extraction")

FIELD_NAMES = [
    "Method", "Dataset", "Split", "Model", "Conditions", "Metric", "Metric value",
    "Hyperparameters", "Hardware", "Seeds", "Code link", "Limitations",
]

_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "ten": 10}
_CODE_RE = re.compile(r"https?://(?:www\.)?(?:github\.com|gitlab\.com|huggingface\.co|zenodo\.org|bitbucket\.org)/[^\s)\]>,;]+")
_SEED_RE = re.compile(
    r"\b(?:averaged\s+over|across|over|using|with|from)\s+(\d+|one|two|three|four|five|six|ten)\s+(?:independent\s+)?(?:random\s+)?seeds?\b"
    r"|\b(?:a\s+)?(single)\s+random\s+seed\b|\b(\d+)\s+random\s+seeds?\b", re.I)
_HW_RE = re.compile(
    r"\b((?:\d+|a single|single|one|two|four|eight)\s+(?:NVIDIA\s+)?(?:A100|V100|H100|A6000|T4|RTX\s?\d{4}|TPU(?:\s?v\d)?)(?:\s+GPUs?)?)", re.I)
_LR_RE = re.compile(r"learning\s+rate\s+(?:was|of|is|=|set to)?\s*([0-9]+(?:\.[0-9]+)?(?:e-?[0-9]+)?)", re.I)
_BS_RE = re.compile(r"batch\s+size\s+(?:of|was|is|=|set to)?\s*(\d+)", re.I)
_SPLIT_RE = re.compile(
    r"((?:standard\s+)?train(?:ing)?,?\s+(?:dev|validation|val)\s*(?:,|and)?\s*(?:and\s+)?test\s+split"
    r"|\b\d{2}/\d{2}/\d{2}\s+split|\b\d+-fold\s+cross-validation|\bheld-out\s+test\s+set)", re.I)
_DEPTH_RE = re.compile(r"(?:retrieval\s+depth\s+(?:is|was|of)\s+)?\b(top-?\d+\s+passages?|top-?k\s*=\s*\d+)", re.I)
_MODEL_RE = re.compile(
    r"\b(DPR(?:-[A-Za-z]+)?|BART-(?:base|large)|T5-(?:small|base|large|xl|xxl)|BERT-(?:base|large)|RoBERTa-(?:base|large)|"
    r"Llama\s?\d?(?:[- ]\d+B)?|GPT-\d\w*|Contriever(?:-MS MARCO)?|E5-(?:small|base|large)|Mistral[- ]?\d*B?|Qwen[\d.]*[- ]?\d*B?)", re.I)
_LIMIT_RE = re.compile(r"\b(limitations?|future work|future research|we could not|we did not|we only|remains? underexplored|few studies|we leave)\b", re.I)


def norm_value(s: str) -> str:
    return " ".join(tokens(s))


def _find_page(pages: list[str], needle: str) -> int | None:
    n = " ".join(needle.split())
    for i, t in enumerate(pages, start=1):
        if n and n in t:
            return i
    return None


def sentence_with(pages: list[str], pattern: re.Pattern[str]) -> tuple[re.Match[str], str, int] | None:
    for pno, text in enumerate(pages, start=1):
        for sent in split_sentences(text):
            m = pattern.search(sent)
            if m:
                return m, sent, pno
    return None


def pass_a(pages: list[str], claims: list[Claim], title: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    def put(name: str, value: str, quote: str, page: int | None) -> None:
        if value and quote and page:
            out[name] = {"value": value.strip(), "quote": quote.strip(), "page": page}

    hit = sentence_with(pages, _CODE_RE)
    if hit:
        put("Code link", hit[0].group(0).rstrip(".,;"), hit[1], hit[2])
    hit = sentence_with(pages, _SEED_RE)
    if hit:
        g = next((x for x in hit[0].groups() if x), "")
        n = _NUM_WORDS.get(g.lower(), g) if g else ""
        n = "1" if str(n).lower() == "single" else n
        put("Seeds", f"{n} random seed{'s' if str(n) != '1' else ''}", hit[1], hit[2])
    hit = sentence_with(pages, _HW_RE)
    if hit:
        put("Hardware", re.sub(r"\s+", " ", hit[0].group(1)), hit[1], hit[2])
    lr = sentence_with(pages, _LR_RE)
    bs = sentence_with(pages, _BS_RE)
    hp_parts, hp_quote, hp_page = [], "", None
    if lr:
        hp_parts.append(f"learning rate {lr[0].group(1)}")
        hp_quote, hp_page = lr[1], lr[2]
    if bs:
        hp_parts.append(f"batch size {bs[0].group(1)}")
        if not hp_quote:
            hp_quote, hp_page = bs[1], bs[2]
    if hp_parts:
        put("Hyperparameters", "; ".join(hp_parts), hp_quote, hp_page)
    hit = sentence_with(pages, _SPLIT_RE)
    if hit:
        put("Split", hit[0].group(1).lower(), hit[1], hit[2])
    hit = sentence_with(pages, _DEPTH_RE)
    if hit:
        put("Conditions", f"retrieval depth {hit[0].group(1).lower()}", hit[1], hit[2])
    hit = sentence_with(pages, _MODEL_RE)
    if hit:
        names: list[str] = []
        for pno, text in enumerate(pages, start=1):
            if pno != hit[2]:
                continue
            for mm in _MODEL_RE.finditer(hit[1]):
                if mm.group(1) not in names:
                    names.append(mm.group(1))
        put("Model", ", ".join(names), hit[1], hit[2])

    # Dataset: lexicon first (verifiable), then results
    ds_found: list[tuple[str, str, int]] = []
    for name in DATASET_LEXICON:
        for pno, text in enumerate(pages, start=1):
            for sent in split_sentences(text):
                if re.search(rf"\b{re.escape(name)}\b", sent) and re.search(r"\b(evaluat|experiment|dataset|benchmark|train|report)", sent, re.I):
                    ds_found.append((name, sent, pno))
                    break
            else:
                continue
            break
    if claims:
        by_ds = Counter(norm_dataset(c.dataset) for c in claims)
        top = by_ds.most_common(1)[0][0]
        main = next(c for c in claims if norm_dataset(c.dataset) == top)
        match = next((d for d in ds_found if norm_dataset(d[0]) == top), None)
        if match:
            put("Dataset", match[0], match[1], match[2])
        else:
            put("Dataset", main.dataset, main.quote, main.page)
    elif ds_found:
        put("Dataset", ds_found[0][0], ds_found[0][1], ds_found[0][2])

    # Method / metric / value from result claims
    if claims:
        tt = set(tokens(title))
        def overlap(c: Claim) -> tuple[int, int]:
            return (len(set(tokens(c.method)) & tt), -claims.index(c))
        primary_method = max(claims, key=overlap)
        mkey = norm_method(primary_method.method)
        mine = [c for c in claims if norm_method(c.method) == mkey]
        # primary result = most frequently reported metric for the primary method, first occurrence in the results section
        metric_counts = Counter(norm_metric(c.metric) for c in mine)
        best_metric = metric_counts.most_common(1)[0][0]
        in_table = [c for c in mine if "table" in c.source]
        if in_table:  # a value reported in a table as well as in prose is the paper's headline result
            best_metric = Counter(norm_metric(c.metric) for c in in_table).most_common(1)[0][0]
        pick = next((c for c in mine if norm_metric(c.metric) == best_metric and "table" in c.source), None) \
            or next((c for c in mine if norm_metric(c.metric) == best_metric and "result" in c.section.lower()), None) \
            or next(c for c in mine if norm_metric(c.metric) == best_metric)
        put("Method", primary_method.method, primary_method.quote, primary_method.page)
        put("Metric", pick.metric, pick.quote, pick.page)
        put("Metric value", f"{pick.value:g}{pick.unit or ''} {pick.metric}", pick.quote, pick.page)
    else:
        for pno, text in enumerate(pages, start=1):
            for sent in split_sentences(text):
                m = re.search(r"\b(" + "|".join(re.escape(w) for w in METRIC_WORDS if len(w) > 3) + r")\b", sent, re.I)
                if m and re.search(r"evaluat|measure|report", sent, re.I):
                    put("Metric", m.group(1), sent, pno)
                    break
            if "Metric" in out:
                break

    for pno, text in enumerate(pages, start=1):
        done = False
        for sent in split_sentences(text):
            if len(sent.split()) >= 6 and _LIMIT_RE.search(sent):  # skip bare headings like "6. Limitations."
                put("Limitations", sent, sent, pno)
                done = True
                break
        if done:
            break
    return out


PASS_B_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        name: {
            "type": "object",
            "properties": {"value": {"type": "string"}, "quote": {"type": "string"}, "page": {"type": "integer"}},
            "required": ["value", "quote", "page"],
        }
        for name in FIELD_NAMES
    },
}

PASS_B_SYSTEM = (
    "You extract experimental setup facts from a research paper. For each field, return the value exactly as the paper "
    "states it, plus a QUOTE copied word-for-word from the text and the page number it appears on. "
    "If the paper does not state a field, omit that field. Never guess or infer. Fields: " + ", ".join(FIELD_NAMES) + "."
)


def pass_b(llm: LLMClient, pages: list[str]) -> dict[str, dict[str, Any]]:
    budget = 9000
    parts, used = [], 0
    for i, t in enumerate(pages, start=1):
        chunk = f"=== PAGE {i} ===\n{t}"
        if used + len(chunk) > budget:
            chunk = chunk[: max(0, budget - used)]
        parts.append(chunk)
        used += len(chunk)
        if used >= budget:
            break
    prompt = "\n\n".join(parts)
    obj = None
    for attempt in range(2):
        raw = llm.chat_json(PASS_B_SYSTEM, prompt if attempt == 0 else prompt + "\n\nReturn valid JSON only.", PASS_B_SCHEMA)
        obj = parse_json_object(raw)
        if obj is not None:
            break
    if obj is None:
        return {}
    out: dict[str, dict[str, Any]] = {}
    norm_pages = [" ".join(p.split()) for p in pages]
    for name in FIELD_NAMES:
        item = obj.get(name)
        if not isinstance(item, dict):
            continue
        value, quote, page = item.get("value"), item.get("quote"), item.get("page")
        if not isinstance(value, str) or not isinstance(quote, str) or not value.strip() or not quote.strip():
            continue
        q = " ".join(quote.split())
        real_page = None
        if isinstance(page, int) and 1 <= page <= len(norm_pages) and q in norm_pages[page - 1]:
            real_page = page
        else:  # model got the page wrong: accept only if the quote verbatim exists somewhere
            real_page = _find_page(norm_pages, q)
        if real_page is None:
            continue  # unverifiable quote → treated as not extracted by pass B
        out[name] = {"value": value.strip(), "quote": q, "page": real_page}
    return out


def values_agree(name: str, a: str, b: str) -> bool:
    na, nb = norm_value(a), norm_value(b)
    if na == nb:
        return True
    if name in ("Metric value",):
        ma, mb = re.search(r"\d+(?:\.\d+)?", a), re.search(r"\d+(?:\.\d+)?", b)
        return bool(ma and mb and float(ma.group()) == float(mb.group()))
    if name in ("Seeds",):
        ma, mb = re.search(r"\d+", a), re.search(r"\d+", b)
        return bool(ma and mb and ma.group() == mb.group())
    if name in ("Code link",):
        return na.rstrip("/") == nb.rstrip("/") or na in nb or nb in na
    if name in ("Limitations",):
        return False  # free text: always human-reviewed
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.8 or ta <= tb or tb <= ta


def merge(a: dict[str, dict[str, Any]], b: dict[str, dict[str, Any]], pass_b_ran: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in FIELD_NAMES:
        fa, fb = a.get(name), b.get(name)
        if not fa and not fb:
            rows.append({"name": name, "value": "", "quote": "", "page": None, "status": "not_reported", "pass_a": {}, "pass_b": {}})
            continue
        primary = fa or fb
        status = "verify"
        if fa and fb and values_agree(name, fa["value"], fb["value"]):
            status = "agree"
        rows.append({
            "name": name, "value": primary["value"], "quote": primary["quote"], "page": primary["page"],
            "status": status, "pass_a": fa or {}, "pass_b": fb or {},
        })
    return rows


def run_for_paper(db: Session, paper: Paper, llm: LLMClient | None = None, use_llm: bool = True) -> dict[str, Any]:
    """(Re)extract fields + result rows for one paper. Human-reviewed fields (confirmed/edited/rejected) are kept."""
    page_rows = db.query(Page).filter(Page.paper_id == paper.id).order_by(Page.number).all()
    pages = [p.text for p in page_rows]
    if not pages:
        return {"fields": 0, "results": 0, "llm_pass": False}
    claims = parse_paper_claims(Path(paper.file_path), pages)
    a = pass_a(pages, claims, paper.title)
    b: dict[str, dict[str, Any]] = {}
    llm_ran, llm_error = False, ""
    if use_llm:
        client = llm or get_llm(db)
        try:
            b = pass_b(client, pages)
            llm_ran = True
        except OllamaUnavailable:
            llm_error = "Ollama was not reachable, so only the deterministic pass ran."
        except OllamaError as e:
            llm_error = str(e)
    rows = merge(a, b, llm_ran)

    existing = {f.name: f for f in db.query(ExtractedField).filter(ExtractedField.paper_id == paper.id).all()}
    for r in rows:
        cur = existing.get(r["name"])
        if cur and cur.status in ("confirmed", "edited", "rejected"):
            continue  # never overwrite a human decision
        if cur:
            cur.value, cur.quote, cur.page, cur.status = r["value"], r["quote"], r["page"], r["status"]
            cur.pass_a, cur.pass_b, cur.updated_at = r["pass_a"], r["pass_b"], utcnow()
        else:
            db.add(ExtractedField(paper_id=paper.id, **r))
    db.query(ResultRow).filter(ResultRow.paper_id == paper.id).delete()
    for c in claims:
        db.add(ResultRow(paper_id=paper.id, method=c.method, dataset=c.dataset, metric=c.metric, value=c.value,
                         unit=c.unit, quote=c.quote, page=c.page))
    db.commit()
    return {"fields": len(rows), "results": len(claims), "llm_pass": llm_ran, "llm_error": llm_error}


def paper_fields_out(db: Session, paper: Paper) -> dict[str, Any]:
    fields = db.query(ExtractedField).filter(ExtractedField.paper_id == paper.id).all()
    order = {n: i for i, n in enumerate(FIELD_NAMES)}
    fields.sort(key=lambda f: order.get(f.name, 99))
    agreed = sum(1 for f in fields if f.status in ("agree", "confirmed", "edited"))
    found = [f for f in fields if f.status != "not_reported"]
    auto = sum(1 for f in fields if f.status == "agree")
    return {
        "paper_id": paper.id,
        "fields": [
            {"id": f.id, "name": f.name, "value": f.value, "quote": f.quote, "page": f.page, "status": f.status,
             "pass_a": f.pass_a or {}, "pass_b": f.pass_b or {}}
            for f in fields
        ],
        "counts": {
            "total": len(fields),
            "reviewed": sum(1 for f in fields if f.status in ("confirmed", "edited", "rejected", "not_reported")),
            "verify": sum(1 for f in fields if f.status == "verify"),
            "agree": auto,
        },
        "agreement_rate": round(auto / len(found), 3) if found else None,
        "accepted": agreed,
    }


def after_paper_ready(db: Session, paper: Paper) -> None:
    if paper.status in ("ready", "ready_keyword_only"):
        run_for_paper(db, paper)
