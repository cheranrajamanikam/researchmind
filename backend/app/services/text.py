"""Small, dependency-free text helpers shared by retrieval, grounding and the analysis modules."""
from __future__ import annotations

import re

STOPWORDS = frozenset(
    """a about above across after again against all also am an and any are as at be because been before being below
    between both but by can could did do does doing down during each few for from further had has have having he her
    here hers him his how i if in into is it its itself just me more most my no nor not now of off on once only or
    other our ours out over own same she should so some such than that the their theirs them then there these they
    this those through to too under until up us very was we were what when where which while who whom why will with
    would you your yours library papers paper evidence study studies show shows tell give find list explain describe
    say says said used use using based among per via vs versus""".split()
)

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-\.']*[A-Za-z0-9]|[A-Za-z0-9]")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(\[])")


def stem(word: str) -> str:
    w = word.lower().strip("-.'")
    for suf in ("ations", "ation", "ingly", "ings", "ing", "edly", "ies", "ied", "ed", "es", "ly", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            w = w[: -len(suf)] + ("y" if suf in ("ies", "ied") else "")
            break
    return w


def tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def content_terms(query: str) -> list[str]:
    """Distinct, stemmed, non-stopword terms of a query (order preserved)."""
    seen: list[str] = []
    for t in tokens(query):
        if t in STOPWORDS or len(t) < 2:
            continue
        s = stem(t)
        if s not in seen:
            seen.append(s)
    return seen


def coverage(terms: list[str], text: str) -> float:
    """Fraction of query terms that occur (stem-matched) in text."""
    if not terms:
        return 0.0
    stems = {stem(t) for t in tokens(text)}
    hit = sum(1 for t in terms if t in stems)
    return hit / len(terms)


# Words whose trailing full stop does not end a sentence: "Rowan et al. (2024)", "e.g. the", "Fig. 3", "A. Rowan".
_ABBREV = frozenset({
    "al", "e.g", "i.e", "cf", "vs", "fig", "figs", "eq", "eqs", "sec", "secs", "ref", "refs", "no", "nos", "dr", "mr", "mrs",
    "ms", "prof", "approx", "ca", "resp", "ed", "eds", "vol", "pp", "st",
})


def _is_abbrev(token: str) -> bool:
    core = token.lstrip("(\"“[").rstrip(".")
    if not token.endswith("."):
        return False
    return core.lower() in _ABBREV or (len(core) == 1 and core.isupper())  # a lone capital is an initial


def split_sentences(text: str) -> list[str]:
    """Split on sentence ends but not after abbreviations or initials, so citations like "Rowan et al. (2024)"
    stay inside one sentence. Pieces are contiguous slices of `text` (minus the separating whitespace)."""
    text = text or ""
    out: list[str] = []
    start = 0
    for m in _SENT.finditer(text):
        prev = re.search(r"(\S+)$", text[start:m.start()])
        if prev and _is_abbrev(prev.group(1)):
            continue
        out.append(text[start:m.start()])
        start = m.end()
    out.append(text[start:])
    return [s for s in out if s]


def best_quote(text: str, terms: list[str], max_len: int = 340) -> str:
    """Pick the most query-relevant run of sentences from `text`, as a verbatim contiguous slice."""
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    sents = split_sentences(text)
    if not sents:
        return text[:max_len].rstrip()
    scored = []
    for i, s in enumerate(sents):
        scored.append((coverage(terms, s) if terms else 0.0, -i, i))
    scored.sort(reverse=True)
    start = scored[0][2]
    quote = sents[start]
    # grow forward then backward while it still fits
    lo = hi = start
    while True:
        grew = False
        if hi + 1 < len(sents) and len(" ".join(sents[lo : hi + 2])) <= max_len:
            hi += 1
            grew = True
        if lo - 1 >= 0 and len(" ".join(sents[lo - 1 : hi + 1])) <= max_len and coverage(terms, sents[lo - 1]) > 0:
            lo -= 1
            grew = True
        if not grew:
            break
    quote = " ".join(sents[lo : hi + 1])
    if len(quote) > max_len:
        quote = quote[:max_len].rsplit(" ", 1)[0]
    return quote.strip()


def raw_terms(query: str) -> list[str]:
    """Unstemmed content words, for FTS5 (its Porter tokenizer does the stemming)."""
    out: list[str] = []
    for t in tokens(query):
        if t not in STOPWORDS and len(t) >= 2 and t not in out:
            out.append(t)
    return out


def fts_match_expr(terms: list[str]) -> str:
    """Build a safe FTS5 MATCH expression: OR of quoted terms (quotes stripped so input can't break syntax)."""
    parts = [f'"{t.replace(chr(34), "")}"' for t in terms if t.replace(chr(34), "").strip()]
    return " OR ".join(parts)


def words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))
