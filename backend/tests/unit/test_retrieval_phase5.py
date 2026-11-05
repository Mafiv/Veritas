"""Unit tests for pgvector / reranker helpers."""

from __future__ import annotations

from app.services.retrieval.pgvector import describe_vector_strategy
from app.services.retrieval.reranker import CrossEncoderReranker, LexicalReranker


def test_pgvector_describe():
    info = describe_vector_strategy()
    assert info["vector_store"] == "postgres/pgvector"
    assert info["embedding_dimensions"] == 384


def test_lexical_reranker_empty():
    r = LexicalReranker()
    assert r.rerank("query", [], top_k=3) == []


def test_cross_encoder_falls_back():
    r = CrossEncoderReranker()
    assert r.rerank("hello world", [], top_k=2) == []
