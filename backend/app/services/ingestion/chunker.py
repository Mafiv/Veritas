"""Semantic chunking — split on logical boundaries, not fixed sizes."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.ingestion.parser import ParsedDocument, ParsedPage


@dataclass
class TextChunk:
    content: str
    chunk_index: int
    page_number: int | None
    heading: str | None
    token_count: int
    meta: dict


def estimate_tokens(text: str) -> int:
    # Rough heuristic (~4 chars/token) — avoids hard dependency on tiktoken at import time
    return max(1, len(text) // 4)


def chunk_document(
    parsed: ParsedDocument,
    *,
    target_tokens: int = 400,
    overlap_tokens: int = 60,
    min_tokens: int = 40,
) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    index = 0

    for page in parsed.pages:
        page_chunks = _chunk_page(page, target_tokens=target_tokens, overlap_tokens=overlap_tokens)
        for pc in page_chunks:
            if estimate_tokens(pc) < min_tokens and chunks:
                # Merge tiny trailing fragments into previous chunk
                prev = chunks[-1]
                merged = prev.content + "\n\n" + pc
                chunks[-1] = TextChunk(
                    content=merged,
                    chunk_index=prev.chunk_index,
                    page_number=prev.page_number,
                    heading=prev.heading or page.heading,
                    token_count=estimate_tokens(merged),
                    meta=prev.meta,
                )
                continue
            chunks.append(
                TextChunk(
                    content=pc,
                    chunk_index=index,
                    page_number=page.page_number,
                    heading=page.heading,
                    token_count=estimate_tokens(pc),
                    meta={"source_page": page.page_number},
                )
            )
            index += 1

    if not chunks and parsed.text.strip():
        chunks.append(
            TextChunk(
                content=parsed.text.strip(),
                chunk_index=0,
                page_number=1,
                heading=None,
                token_count=estimate_tokens(parsed.text),
                meta={},
            )
        )
    return chunks


def _chunk_page(page: ParsedPage, *, target_tokens: int, overlap_tokens: int) -> list[str]:
    text = page.text.strip()
    if not text:
        return []

    # Prefer paragraph / section boundaries
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    # Also split oversized paragraphs on sentence boundaries
    units: list[str] = []
    for para in paragraphs:
        if estimate_tokens(para) <= target_tokens:
            units.append(para)
        else:
            units.extend(_split_sentences(para, target_tokens))

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for unit in units:
        unit_tokens = estimate_tokens(unit)
        if current and current_tokens + unit_tokens > target_tokens:
            chunks.append("\n\n".join(current))
            # Overlap: keep trailing units that fit overlap budget
            overlap: list[str] = []
            overlap_count = 0
            for u in reversed(current):
                t = estimate_tokens(u)
                if overlap_count + t > overlap_tokens:
                    break
                overlap.insert(0, u)
                overlap_count += t
            current = overlap
            current_tokens = overlap_count
        current.append(unit)
        current_tokens += unit_tokens

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _split_sentences(text: str, target_tokens: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    units: list[str] = []
    buf: list[str] = []
    tokens = 0
    for s in sentences:
        t = estimate_tokens(s)
        if buf and tokens + t > target_tokens:
            units.append(" ".join(buf))
            buf = [s]
            tokens = t
        else:
            buf.append(s)
            tokens += t
    if buf:
        units.append(" ".join(buf))
    return units
