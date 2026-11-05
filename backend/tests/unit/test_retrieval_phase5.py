"""Unit tests for retrieval introspection and reranker selection/fallback."""

from __future__ import annotations

from app.services.retrieval.hybrid_search import ScoredChunk
from app.services.retrieval.pgvector import describe_vector_strategy
from app.services.retrieval.reranker import (
    CrossEncoderReranker,
    LexicalReranker,
    build_reranker,
)


class _Chunk:
    def __init__(self, content: str) -> None:
        self.content = content


def test_pgvector_describe():
    info = describe_vector_strategy()
    assert info["vector_store"] == "postgres/pgvector"
    assert info["embedding_dimensions"] == 384


async def test_lexical_reranker_empty():
    assert await LexicalReranker().rerank("query", [], top_k=3) == []


def test_build_reranker_respects_backend_setting():
    # tests/conftest.py sets RERANKER_BACKEND=lexical
    assert isinstance(build_reranker(), LexicalReranker)


async def test_cross_encoder_falls_back_to_lexical_when_model_unavailable():
    reranker = CrossEncoderReranker(model_name="does-not-exist/model")
    candidates = [
        ScoredChunk(chunk=_Chunk("gardening tips"), document=None, score=0.9),  # type: ignore[arg-type]
        ScoredChunk(chunk=_Chunk("refund policy for purchases"), document=None, score=0.1),  # type: ignore[arg-type]
    ]
    ranked = await reranker.rerank("refund policy", candidates, top_k=2)
    assert ranked[0].chunk.content == "refund policy for purchases"
