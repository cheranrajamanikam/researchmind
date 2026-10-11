"""PDF text extraction (text-layer PDFs only; no OCR) and light metadata guessing."""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader

_WS = re.compile(r"\s+")
_HYPHEN = re.compile(r"(?<=[A-Za-z])-\n(?=[a-z])")


def normalize_text(text: str) -> str:
    """Join hyphenated line breaks and collapse all whitespace to single spaces.

    Chunks and quotes are cut from this exact string, so every quote is a verbatim
    substring of the stored page text.
    """
    text = _HYPHEN.sub("", text or "")
    return _WS.sub(" ", text).strip()


@dataclass
class ExtractedPdf:
    pages: list[str]
    title: str = ""
    authors: str = ""
    year: int | None = None
    warnings: list[str] = field(default_factory=list)


def _guess_title(first_page_raw: str, meta_title: str | None, fallback: str, font_title: str = "") -> str:
    if meta_title and len(meta_title.strip()) >= 8 and not meta_title.lower().endswith((".pdf", ".docx", ".tex")):
        return meta_title.strip()[:300]
    if font_title:
        return font_title[:300]
    for line in (first_page_raw or "").splitlines():
        line = line.strip()
        if len(line) >= 12 and not re.match(r"^(arxiv|proceedings|preprint|published|copyright|\d)", line, re.I):
            return line[:300]
    return fallback


def _title_from_fonts(path: Path) -> str:
    """Largest-font text block near the top of page 1 (titles are set larger than headers/footers)."""
    try:
        import pdfplumber

        with pdfplumber.open(str(path)) as pdf:
            if not pdf.pages:
                return ""
            words = pdf.pages[0].extract_words(extra_attrs=["size"], keep_blank_chars=False, use_text_flow=False)
    except Exception:  # noqa: BLE001 - heuristics only; never block ingestion
        return ""
    if not words:
        return ""
    top = max(round(w["size"], 1) for w in words)
    big = [w for w in words if round(w["size"], 1) >= top - 0.3]
    if top < 10 and len(words) > 40:  # no visually distinct title
        return ""
    big.sort(key=lambda w: (round(w["top"]), w["x0"]))
    lines: list[list[str]] = []
    last_top = None
    for w in big:
        if last_top is None or abs(w["top"] - last_top) > top * 0.6:
            lines.append([])
        lines[-1].append(w["text"])
        last_top = w["top"]
    title = " ".join(" ".join(line) for line in lines[:3]).strip()
    return title if len(title) >= 8 else ""


_NAME_TOKEN = r"[A-Z][A-Za-z\u00C0-\u024F.\-']*"
_NAME = re.compile(rf"^{_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{1,3}}$")
_NOT_NAMES = re.compile(
    r"\b(university|institute|department|laborator(?:y|ies)|school|college|abstract|keywords?|proceedings|conference|journal|"
    r"preprint|arxiv|copyright|received|accepted|published|email|corresponding|google|microsoft|meta|openai|research|technical report)\b",
    re.I,
)
_JUNK_AUTHOR = re.compile(r"^(user|admin|administrator|unknown|anonymous|microsoft|latex|word|pdf|none|acrobat)\b", re.I)


def _flat(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def guess_authors(first_page_raw: str, title: str) -> str:
    """Read a byline such as "A. Rowan, K. Mehta. 2024." from the lines under the title. Conservative: returns ""
    unless a line is made only of capitalised name-like tokens separated by commas / "and"."""
    flat_title = _flat(title)
    for raw in (first_page_raw or "").splitlines()[:25]:
        line = raw.strip()
        if not line:
            continue
        if re.match(r"^abstract\b", line, re.I):
            break
        flat = _flat(line)
        if not flat or flat in flat_title or (len(flat) > 12 and flat_title in flat):
            continue  # part of the title
        cand = re.sub(r"[\s.,;]*\b(?:19|20)\d{2}\b[\s.,;]*$", "", line)  # drop a trailing year
        cand = re.sub(r"[\d*†‡§¶]+", "", cand).strip(" .;,")
        if not cand or _NOT_NAMES.search(cand) or "@" in line:
            continue
        parts = [x.strip(" .") for x in re.split(r",|;|\band\b|&", cand) if x.strip(" .")]
        if not 1 <= len(parts) <= 12 or not all(_NAME.match(x) for x in parts):
            continue
        return ", ".join(parts)[:300]
    return ""


def _guess_year(first_page_raw: str, meta_date: str | None) -> int | None:
    this_year = datetime.now().year
    for m in re.finditer(r"\b(19[89]\d|20\d{2})\b", first_page_raw or ""):
        y = int(m.group(1))
        if 1980 <= y <= this_year:
            return y
    if meta_date:
        m = re.match(r"D:(\d{4})", meta_date)
        if m and 1980 <= int(m.group(1)) <= this_year:
            return int(m.group(1))
    return None


def _pick_authors(meta_author: str | None, first_raw: str, title: str) -> str:
    meta = (meta_author or "").strip()
    if meta and re.search(r"[A-Za-z]{2}", meta) and not _JUNK_AUTHOR.match(meta):
        return meta[:300]
    return guess_authors(first_raw, title)


def extract_pdf(
    path: Path, fallback_title: str, on_page: Callable[[int, int], None] | None = None
) -> ExtractedPdf:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as e:  # noqa: BLE001
            raise ValueError("This PDF is password-protected.") from e
    total = len(reader.pages)
    pages: list[str] = []
    first_raw = ""
    for i, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - a broken page must not kill the whole paper
            raw = ""
        if i == 1:
            first_raw = raw
        pages.append(normalize_text(raw))
        if on_page:
            on_page(i, total)
    meta = reader.metadata
    meta_title = getattr(meta, "title", None) if meta else None
    meta_author = getattr(meta, "author", None) if meta else None
    meta_date = (meta.get("/CreationDate") if meta else None) if meta else None
    title = _guess_title(first_raw, meta_title, fallback_title, _title_from_fonts(path))
    return ExtractedPdf(
        pages=pages,
        title=title,
        authors=_pick_authors(meta_author, first_raw, title),
        year=_guess_year(first_raw, str(meta_date) if meta_date else None),
    )
