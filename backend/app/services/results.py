"""Deterministic parsing of reported results (method, dataset, metric, value) from page text and tables.

Only patterns that can be verified against the source are accepted; everything else is simply not extracted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .text import split_sentences as _split_text
from .text import stem, tokens

METRIC_WORDS = (
    "exact match", "em", "f1", "f1 score", "accuracy", "precision", "recall", "bleu", "rouge", "rouge-l", "mrr",
    "ndcg", "perplexity", "auc", "map", "citation precision", "citation recall", "citation correctness", "top-1 accuracy",
    "top-5 accuracy", "error rate", "wer", "cer",
)
METRIC_ALIASES = {"em": "exact match", "f1 score": "f1", "acc": "accuracy"}
DATASET_ALIASES = {"nq": "natural questions", "natural questions (nq)": "natural questions", "hotpot": "hotpotqa"}
DATASET_LEXICON = (
    "Natural Questions", "TriviaQA", "HotpotQA", "PopQA", "SQuAD", "MS MARCO", "ImageNet", "CIFAR-10", "CIFAR-100",
    "MNIST", "GLUE", "SuperGLUE", "WikiText", "CoNLL", "COCO", "WebQuestions", "FEVER", "BEIR", "MMLU", "GSM8K",
    "HumanEval", "PubMedQA", "BioASQ", "TREC", "QuAC", "CoQA", "WikiQA",
)

_VERBS = r"(?:obtains|obtained|achieves|achieved|reaches|reached|attains|attained|reports|reported|gets|scores|yields|records)"
_SENT_RE = re.compile(
    rf"(?P<method>(?:[Oo]ur\s+)?[A-Z][\w\-]*(?:\s+[A-Za-z][\w\-]*){{0,4}}?)(?:\s+method|\s+model|\s+system)?\s+{_VERBS}\s+"
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%)?\s+(?P<metric>[A-Za-z][A-Za-z0-9\- ]{0,30}?)\s+on\s+"
    r"(?P<dataset>[A-Z][A-Za-z0-9\- ]*?)(?=\s*(?:[.,;]|\s(?:using|with|under|when|and|while)\b|$))"
)
# "On the Natural Questions test set, the RAG-Sequence model obtains 44.5 exact match." (dataset first)
_SENT_RE_DATASET_FIRST = re.compile(
    r"\bOn\s+(?:the\s+)?(?P<dataset>[A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*){0,3})"
    r"(?:\s+(?:test|dev|validation|development)\s+(?:set|split))?,\s+(?:the\s+|our\s+)?"
    rf"(?P<method>[A-Z][\w\-]*(?:\s+[A-Za-z][\w\-]*){{0,3}}?)(?:\s+method|\s+model|\s+system)?\s+{_VERBS}\s+"
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%)?\s+(?P<metric>[A-Za-z][A-Za-z0-9\- ]{0,30}?)"
    r"(?=\s*(?:[.,;]|\s(?:under|using|with|when|and|while)\b|$))"
)
# Words that describe a method without naming it ("The model achieves…", "Our proposed method…"). A claim whose
# only method text is made of these cannot be compared across papers, so it is not extracted.
GENERIC_METHOD_WORDS = frozenset({
    "the", "our", "this", "that", "these", "we", "it", "model", "models", "method", "methods", "system", "approach",
    "proposed", "baseline", "replicated", "algorithm", "network", "framework", "new", "full", "final", "best",
})
_HEADING = re.compile(r"(Abstract|\b\d{1,2}\.\s+[A-Z][A-Za-z ]{2,30}?)(?=\.\s|\s[A-Z])")


@dataclass
class Claim:
    method: str
    dataset: str
    metric: str
    value: float
    unit: str
    quote: str
    page: int
    section: str = ""
    source: str = "text"  # text | table


def norm_method(m: str) -> str:
    m = re.sub(r"^(our|the)\s+", "", m.strip(), flags=re.I)
    return " ".join(stem(t) for t in tokens(m))


def norm_metric(m: str) -> str:
    m = " ".join(tokens(m))
    return METRIC_ALIASES.get(m, m)


def norm_dataset(d: str) -> str:
    d = " ".join(tokens(d))
    return DATASET_ALIASES.get(d, d)


def display_method(m: str) -> str:
    return re.sub(r"^(Our|our|The|the)\s+", "", m.strip())


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _split_text(text) if s.strip()]


def section_of(page_text: str, sentence: str) -> str:
    idx = page_text.find(sentence)
    head = page_text[: idx if idx >= 0 else len(page_text)]
    found = _HEADING.findall(head)
    return found[-1].strip() if found else ""


def is_named_method(method: str) -> bool:
    words = re.findall(r"[a-z]+", method.lower())
    return bool(words) and not set(words) <= GENERIC_METHOD_WORDS


def claims_from_text(page_text: str, page: int) -> list[Claim]:
    out: list[Claim] = []
    for sent in split_sentences(page_text):
        for m in [*_SENT_RE.finditer(sent), *_SENT_RE_DATASET_FIRST.finditer(sent)]:
            metric = m.group("metric").strip()
            if not metric or len(metric) < 2 or not is_named_method(m.group("method")):
                continue
            out.append(
                Claim(
                    method=display_method(m.group("method")),
                    dataset=m.group("dataset").strip(),
                    metric=metric,
                    value=float(m.group("value")),
                    unit=m.group("unit") or "",
                    quote=sent,
                    page=page,
                    section=section_of(page_text, sent),
                )
            )
    return out


def _is_metric(cell: str) -> bool:
    c = norm_metric(cell)
    return any(c == w or c.startswith(w) for w in METRIC_WORDS)


def claims_from_tables(pdf_path: Path, page_texts: list[str]) -> list[Claim]:
    out: list[Claim] = []
    try:
        import pdfplumber

        with pdfplumber.open(str(pdf_path)) as pdf:
            for pno, page in enumerate(pdf.pages, start=1):
                text = page_texts[pno - 1] if pno - 1 < len(page_texts) else ""
                for table in page.extract_tables() or []:
                    out.extend(_table_claims(table, text, pno))
    except Exception:  # noqa: BLE001 - table parsing is best effort
        return out
    return out


def _table_claims(table: list[list[str | None]], page_text: str, page: int) -> list[Claim]:
    rows = [[(c or "").strip() for c in r] for r in table if r and any((c or "").strip() for c in r)]
    if len(rows) < 2 or rows[0][0].lower() not in ("method", "model", "system", "approach", "baseline"):
        return []
    caption = ""
    cm = re.findall(r"(Table\s+\d+[:.]\s*[^\n]*?)(?=\s+(?:Method|Model|System|Approach)\b|\s{2,}|$)", page_text)
    if cm:
        caption = cm[-1]
    cap_body = re.sub(r"^Table\s+\d+[:.]\s*", "", caption)
    cap_metric, cap_dataset = "", ""
    mm = re.match(r"(.+?)\s+on\s+(.+)$", cap_body)
    if mm:
        cap_metric, cap_dataset = mm.group(1).strip(), mm.group(2).strip()
    claims: list[Claim] = []
    for row in rows[1:]:
        method = row[0]
        for ci in range(1, min(len(row), len(rows[0]))):
            head, raw = rows[0][ci], row[ci]
            vm = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(%?)", raw.replace(",", ""))
            if not vm:
                continue
            if "(" in head and head.endswith(")"):
                dataset, metric = head.split("(", 1)[0].strip(), head.split("(", 1)[1].rstrip(")").strip()
            elif _is_metric(head):
                dataset, metric = cap_dataset, head
            else:
                dataset, metric = head, cap_metric
            if not dataset or not metric:
                continue
            candidates = [f"{method} {raw}", f"{method} {raw}%"]
            quote = next((c for c in candidates if c in page_text), caption or "")
            if not quote:
                continue
            claims.append(
                Claim(method, dataset, metric, float(vm.group(1)), vm.group(2), quote, page,
                      section_of(page_text, quote), "table")
            )
    return claims


def dedupe(claims: list[Claim]) -> list[Claim]:
    """One claim per (method, dataset, metric, value); the text sentence is kept, and 'text+table' marks a
    value that the paper states both in prose and in a table (a stronger signal of a headline result)."""
    seen: dict[tuple[str, str, str, float], Claim] = {}
    for c in claims:
        key = (norm_method(c.method), norm_dataset(c.dataset), norm_metric(c.metric), round(c.value, 4))
        prev = seen.get(key)
        if prev is None:
            seen[key] = c
            continue
        both = "text+table" if {prev.source, c.source} == {"text", "table"} or "text+table" in (prev.source, c.source) else prev.source
        keep = c if (prev.source == "table" and c.source == "text") else prev
        keep.source = both
        seen[key] = keep
    return list(seen.values())


def parse_paper_claims(pdf_path: Path | None, page_texts: list[str]) -> list[Claim]:
    claims: list[Claim] = []
    for i, t in enumerate(page_texts, start=1):
        claims.extend(claims_from_text(t, i))
    if pdf_path and pdf_path.exists():
        claims.extend(claims_from_tables(pdf_path, page_texts))
    return dedupe(claims)
