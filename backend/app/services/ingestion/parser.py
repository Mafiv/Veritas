"""Document parsers for PDF, markdown, Notion exports, and plain text."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

from app.models.domain import DocumentType


@dataclass
class ParsedPage:
    page_number: int
    text: str
    heading: str | None = None


@dataclass
class ParsedDocument:
    text: str
    pages: list[ParsedPage]
    page_count: int
    doc_type: DocumentType
    meta: dict


def detect_doc_type(filename: str, content_type: str) -> DocumentType:
    lower = filename.lower()
    if lower.endswith(".pdf") or content_type == "application/pdf":
        return DocumentType.PDF
    if lower.endswith((".md", ".markdown")) or "markdown" in content_type:
        return DocumentType.MARKDOWN
    if lower.endswith(".docx"):
        return DocumentType.DOCX
    if "notion" in lower or lower.endswith(".html"):
        return DocumentType.NOTION
    return DocumentType.TEXT


def parse_document(filename: str, content_type: str, data: bytes) -> ParsedDocument:
    doc_type = detect_doc_type(filename, content_type)
    if doc_type == DocumentType.PDF:
        return _parse_pdf(data)
    if doc_type == DocumentType.MARKDOWN:
        return _parse_markdown(data)
    if doc_type == DocumentType.DOCX:
        return _parse_docx(data)
    if doc_type == DocumentType.NOTION:
        return _parse_notion(data)
    return _parse_text(data)


def _parse_pdf(data: bytes) -> ParsedDocument:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages: list[ParsedPage] = []
        parts: list[str] = []
        for i, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            # Lightweight OCR stub: if page is empty, note it for future Textract/Tesseract
            if not text:
                text = f"[Page {i}: scanned content — OCR pending]"
            pages.append(ParsedPage(page_number=i, text=text))
            parts.append(text)
        full = "\n\n".join(parts)
        return ParsedDocument(
            text=full,
            pages=pages,
            page_count=len(pages),
            doc_type=DocumentType.PDF,
            meta={"parser": "pypdf"},
        )
    except Exception as exc:  # noqa: BLE001
        text = data.decode("utf-8", errors="ignore")
        return ParsedDocument(
            text=text,
            pages=[ParsedPage(page_number=1, text=text)],
            page_count=1,
            doc_type=DocumentType.PDF,
            meta={"parser": "fallback", "error": str(exc)},
        )


def _parse_markdown(data: bytes) -> ParsedDocument:
    text = data.decode("utf-8", errors="ignore")
    pages = _split_by_headings(text)
    return ParsedDocument(
        text=text,
        pages=pages,
        page_count=len(pages),
        doc_type=DocumentType.MARKDOWN,
        meta={"parser": "markdown"},
    )


def _parse_notion(data: bytes) -> ParsedDocument:
    raw = data.decode("utf-8", errors="ignore")
    # Strip basic HTML tags from Notion HTML exports
    text = re.sub(r"<script[\s\S]*?</script>", "", raw, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    pages = _split_by_headings(text)
    return ParsedDocument(
        text=text,
        pages=pages,
        page_count=len(pages),
        doc_type=DocumentType.NOTION,
        meta={"parser": "notion-html"},
    )


def _parse_docx(data: bytes) -> ParsedDocument:
    try:
        from docx import Document as DocxDocument

        doc = DocxDocument(io.BytesIO(data))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        text = "\n\n".join(paragraphs)
        # Preserve simple tables as markdown
        for table in doc.tables:
            rows = []
            for row in table.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                rows.append("| " + " | ".join(cells) + " |")
            if rows:
                header_sep = "| " + " | ".join(["---"] * len(table.rows[0].cells)) + " |"
                table_md = "\n".join([rows[0], header_sep, *rows[1:]])
                text += "\n\n" + table_md
        pages = [ParsedPage(page_number=1, text=text)]
        return ParsedDocument(
            text=text,
            pages=pages,
            page_count=1,
            doc_type=DocumentType.DOCX,
            meta={"parser": "python-docx"},
        )
    except Exception as exc:  # noqa: BLE001
        text = data.decode("utf-8", errors="ignore")
        return ParsedDocument(
            text=text,
            pages=[ParsedPage(page_number=1, text=text)],
            page_count=1,
            doc_type=DocumentType.DOCX,
            meta={"parser": "fallback", "error": str(exc)},
        )


def _parse_text(data: bytes) -> ParsedDocument:
    text = data.decode("utf-8", errors="ignore")
    return ParsedDocument(
        text=text,
        pages=[ParsedPage(page_number=1, text=text)],
        page_count=1,
        doc_type=DocumentType.TEXT,
        meta={"parser": "text"},
    )


def _split_by_headings(text: str) -> list[ParsedPage]:
    parts = re.split(r"(?m)^(#{1,3}\s+.+)$", text)
    pages: list[ParsedPage] = []
    current_heading: str | None = None
    buffer: list[str] = []
    page_num = 1

    def flush() -> None:
        nonlocal page_num, buffer, current_heading
        body = "\n".join(buffer).strip()
        if body or current_heading:
            content = f"{current_heading}\n\n{body}".strip() if current_heading else body
            pages.append(ParsedPage(page_number=page_num, text=content, heading=current_heading))
            page_num += 1
        buffer = []

    for part in parts:
        if re.match(r"^#{1,3}\s+", part or ""):
            flush()
            current_heading = part.strip()
        else:
            if part:
                buffer.append(part)
    flush()
    if not pages:
        pages = [ParsedPage(page_number=1, text=text)]
    return pages


def guess_extension(doc_type: DocumentType) -> str:
    return {
        DocumentType.PDF: ".pdf",
        DocumentType.MARKDOWN: ".md",
        DocumentType.TEXT: ".txt",
        DocumentType.NOTION: ".html",
        DocumentType.DOCX: ".docx",
    }.get(doc_type, ".bin")
