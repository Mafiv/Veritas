"""Unit tests for document parser."""

from app.models.domain import DocumentType
from app.services.ingestion.parser import detect_doc_type, parse_document


def test_detect_doc_type():
    assert detect_doc_type("report.pdf", "application/pdf") == DocumentType.PDF
    assert detect_doc_type("notes.md", "text/markdown") == DocumentType.MARKDOWN
    assert detect_doc_type("export.html", "text/html") == DocumentType.NOTION


def test_parse_markdown_splits_headings():
    data = b"# Title\n\nHello world.\n\n## Section\n\nMore detail about Veritas."
    parsed = parse_document("notes.md", "text/markdown", data)
    assert parsed.doc_type == DocumentType.MARKDOWN
    assert parsed.page_count >= 1
    assert "Hello world" in parsed.text


def test_parse_plain_text():
    parsed = parse_document("a.txt", "text/plain", b"Simple text document.")
    assert parsed.doc_type == DocumentType.TEXT
    assert parsed.pages[0].text == "Simple text document."
