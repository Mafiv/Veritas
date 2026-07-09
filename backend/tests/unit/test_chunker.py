"""Unit tests for semantic chunker."""

from app.services.ingestion.chunker import chunk_document, estimate_tokens
from app.services.ingestion.parser import ParsedDocument, ParsedPage
from app.models.domain import DocumentType


def test_estimate_tokens():
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 40) == 10


def test_chunk_respects_paragraph_boundaries():
    text = "\n\n".join(
        [
            "Introduction paragraph about Veritas retrieval systems and grounded answers.",
            "Second paragraph discusses hybrid search combining vector similarity with BM25 keyword matching for better recall.",
            "Third paragraph covers cross-encoder reranking of top candidates before the LLM call.",
            "Fourth paragraph explains HyDE hypothetical document embeddings for query rewriting.",
        ]
        * 3
    )
    parsed = ParsedDocument(
        text=text,
        pages=[ParsedPage(page_number=1, text=text, heading="# Overview")],
        page_count=1,
        doc_type=DocumentType.MARKDOWN,
        meta={},
    )
    chunks = chunk_document(parsed, target_tokens=80, overlap_tokens=20, min_tokens=10)
    assert len(chunks) >= 2
    assert all(c.content.strip() for c in chunks)
    assert chunks[0].heading == "# Overview"
