"""Second-stage reranking of fused candidates.

- ``CrossEncoderReranker``: a real cross-encoder (MS MARCO MiniLM, ONNX via
  fastembed). It reads query and passage together, which is far more precise
  than first-stage similarity. Raw logits are squashed with a sigmoid so the
  score lies in (0, 1) and can drive the abstention threshold.
- ``LexicalReranker``: term-overlap heuristic used only as a fallback (tests,
  or when the model cannot be loaded). It is *not* a cross-encoder.
"""

from __future__ import annotations

import asyncio
import math
import threading
from collections import Counter
from dataclasses import replace
from typing import Any, Protocol

from app.core.config import get_settings
from app.services.monitoring.logger import get_logger
from app.services.retrieval.hybrid_search import ScoredChunk, tokenize

log = get_logger("veritas.reranker")


class Reranker(Protocol):
    name: str

    async def rerank(
        self, query: str, candidates: list[ScoredChunk], top_k: int = 8
    ) -> list[ScoredChunk]: ...


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class LexicalReranker:
    """Term-overlap heuristic (fallback only)."""

    name = "lexical"

    async def rerank(
        self, query: str, candidates: list[ScoredChunk], top_k: int = 8
    ) -> list[ScoredChunk]:
        scored = [
            replace(c, score=0.45 * c.score + 0.55 * self._pair_score(query, c.chunk.content))
            for c in candidates
        ]
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    @staticmethod
    def _pair_score(query: str, passage: str) -> float:
        q = tokenize(query)
        p = tokenize(passage)
        if not q or not p:
            return 0.0
        q_set = set(q)
        p_counts = Counter(p)
        overlap = sum(min(1, p_counts[t]) for t in q_set)
        coverage = overlap / len(q_set)
        density = overlap / math.sqrt(len(p))
        passage_lower = passage.lower()
        bigram_boost = sum(0.1 for i in range(len(q) - 1) if f"{q[i]} {q[i + 1]}" in passage_lower)
        return min(1.0, coverage * 0.7 + density * 0.2 + bigram_boost)


class CrossEncoderReranker:
    """fastembed TextCrossEncoder; inference runs in a worker thread."""

    name = "cross_encoder"
    _models: dict[str, Any] = {}
    _lock = threading.Lock()

    def __init__(self, model_name: str | None = None, cache_dir: str | None = None) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.reranker_model
        self.cache_dir = cache_dir or settings.model_cache_dir or None

    def _model(self) -> Any:
        with self._lock:
            model = self._models.get(self.model_name)
            if model is None:
                from fastembed.rerank.cross_encoder import TextCrossEncoder

                model = TextCrossEncoder(self.model_name, cache_dir=self.cache_dir)
                self._models[self.model_name] = model
            return model

    def _score_sync(self, query: str, passages: list[str]) -> list[float]:
        return [_sigmoid(float(s)) for s in self._model().rerank(query, passages)]

    async def rerank(
        self, query: str, candidates: list[ScoredChunk], top_k: int = 8
    ) -> list[ScoredChunk]:
        if not candidates:
            return []
        passages = [c.chunk.content for c in candidates]
        try:
            scores = await asyncio.to_thread(self._score_sync, query, passages)
        except Exception as exc:  # noqa: BLE001 - degrade loudly, never fail the request
            log.warning("reranker.cross_encoder_failed", model=self.model_name, error=str(exc))
            return await LexicalReranker().rerank(query, candidates, top_k=top_k)
        scored = [replace(c, score=s) for c, s in zip(candidates, scores)]
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]


def build_reranker() -> Reranker:
    """Model weights load lazily on first use, not at import/startup."""
    if get_settings().reranker_backend == "cross_encoder":
        return CrossEncoderReranker()
    return LexicalReranker()
