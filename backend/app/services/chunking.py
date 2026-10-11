"""Page-aware chunking: a chunk never crosses a page boundary."""
from __future__ import annotations

from dataclasses import dataclass

from .text import split_sentences


@dataclass(frozen=True)
class ChunkSpec:
    page_number: int
    idx: int
    text: str


def chunk_page(text: str, page_number: int, start_idx: int, size: int, overlap: int) -> list[ChunkSpec]:
    """Pack whole sentences into ~size-char chunks, carrying `overlap` chars of trailing sentences forward.

    Chunk text is always a contiguous, verbatim slice of the (whitespace-normalised) page text.
    """
    text = text.strip()
    if not text:
        return []
    sentences = split_sentences(text)
    # Hard-split sentences that are longer than the chunk size (tables, reference lists).
    pieces: list[str] = []
    for s in sentences:
        while len(s) > size * 1.5:
            cut = s.rfind(" ", 0, size)
            cut = cut if cut > size // 2 else size
            pieces.append(s[:cut])
            s = s[cut:].lstrip()
        if s:
            pieces.append(s)

    chunks: list[ChunkSpec] = []
    cur: list[str] = []
    cur_len = 0
    idx = start_idx
    for piece in pieces:
        add = len(piece) + (1 if cur else 0)
        if cur and cur_len + add > size:
            chunks.append(ChunkSpec(page_number, idx, " ".join(cur)))
            idx += 1
            # carry overlap
            carry: list[str] = []
            carry_len = 0
            for s in reversed(cur):
                if carry_len + len(s) > overlap:
                    break
                carry.insert(0, s)
                carry_len += len(s) + 1
            cur, cur_len = carry, sum(len(s) + 1 for s in carry)
            add = len(piece) + (1 if cur else 0)
        cur.append(piece)
        cur_len += add
    if cur and (not chunks or " ".join(cur) != chunks[-1].text):
        chunks.append(ChunkSpec(page_number, idx, " ".join(cur)))
    return chunks


def chunk_document(pages: list[str], size: int = 900, overlap: int = 150) -> list[ChunkSpec]:
    out: list[ChunkSpec] = []
    for i, text in enumerate(pages, start=1):
        out.extend(chunk_page(text, i, len(out), size, overlap))
    return out
