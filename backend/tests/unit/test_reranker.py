"""Unit tests for query rewriter / reranker."""

import pytest

from app.core.config import Settings, get_settings
from app.services.retrieval.reranker import CrossEncoderReranker
from app.services.retrieval.hybrid_search import ScoredChunk
from app.services.llm.client import LLMClient


class FakeChunk:
    def __init__(self, content: str, id: str = "1"):
        self.content = content
        self.id = id
        self.page_number = 1
        self.heading = None


class FakeDoc:
    def __init__(self):
        self.id = "d1"
        self.original_filename = "doc.md"


def test_reranker_prefers_overlapping_passage():
    reranker = CrossEncoderReranker()
    candidates = [
        ScoredChunk(chunk=FakeChunk("unrelated gardening tips"), document=FakeDoc(), score=0.5),
        ScoredChunk(
            chunk=FakeChunk("hybrid search with bm25 keyword matching improves recall"),
            document=FakeDoc(),
            score=0.4,
        ),
    ]
    ranked = reranker.rerank("hybrid search bm25", candidates, top_k=2)
    assert "hybrid" in ranked[0].chunk.content


@pytest.mark.asyncio
async def test_mock_llm_grounded_answer(monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.llm.client.get_settings",
        lambda: Settings(use_mock_llm=True),
    )
    llm = LLMClient()
    text = await llm.complete(
        system="answer",
        user="Sources:\n[1] revenue was 4.2M\n\nQuestion: What was revenue?",
    )
    assert "[1]" in text or "grounded" in text.lower() or "Answer" in text
