"""pgvector helper unit tests."""

from __future__ import annotations

from app.services.retrieval.pgvector import (
    _vector_literal,
    describe_vector_strategy,
    pgvector_enabled,
)


def test_vector_literal():
    lit = _vector_literal([0.1, 0.2, 0.3])
    assert lit.startswith("[")
    assert "0.10000000" in lit


def test_describe_strategy():
    info = describe_vector_strategy()
    assert info["migration"] == "008_pgvector"
    assert "storage" in info
    assert isinstance(pgvector_enabled(), bool)
