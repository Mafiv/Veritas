"""Cross-encoder style reranker with pluggable backends."""

from __future__ import annotations

import math
from collections import Counter

from app.core.config import get_settings
from app.services.retrieval.hybrid_search import ScoredChunk, tokenize


class LexicalReranker:
    """Lightweight lexical cross-encoder stand-in (default / mock-friendly)."""

    def rerank(
        self, query: str, candidates: list[ScoredChunk], top_k: int = 8
    ) -> list[ScoredChunk]:
        scored: list[ScoredChunk] = []
        for c in candidates:
            lexical = self._pair_score(query, c.chunk.content)
            new_score = 0.45 * c.score + 0.55 * lexical
            scored.append(
                ScoredChunk(
                    chunk=c.chunk,
                    document=c.document,
                    score=new_score,
                    vector_score=c.vector_score,
                    bm25_score=c.bm25_score,
                )
            )
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    def _pair_score(self, query: str, passage: str) -> float:
        q = tokenize(query)
        p = tokenize(passage)
        if not q or not p:
            return 0.0
        q_set = set(q)
        p_counts = Counter(p)
        overlap = sum(min(1, p_counts[t]) for t in q_set)
        coverage = overlap / len(q_set)
        density = overlap / math.sqrt(len(p))
        bigram_boost = 0.0
        passage_lower = passage.lower()
        for i in range(len(q) - 1):
            phrase = f"{q[i]} {q[i + 1]}"
            if phrase in passage_lower:
                bigram_boost += 0.1
        return min(1.0, coverage * 0.7 + density * 0.2 + bigram_boost)


class CrossEncoderReranker:
    """
    Optional sentence-transformers CrossEncoder backend.

    Falls back to lexical scoring when the model package/weights are unavailable
    or when settings.reranker_backend != cross_encoder.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._lexical = LexicalReranker()
        self._model = None
        if self.settings.reranker_backend == "cross_encoder":
            self._model = self._try_load_model()

    def _try_load_model(self):
        try:
            from sentence_transformers import CrossEncoder

            return CrossEncoder(self.settings.reranker_model)
        except Exception:
            return None

    def rerank(
        self, query: str, candidates: list[ScoredChunk], top_k: int = 8
    ) -> list[ScoredChunk]:
        if self._model is None or not candidates:
            return self._lexical.rerank(query, candidates, top_k=top_k)
        pairs = [(query, c.chunk.content) for c in candidates]
        try:
            scores = self._model.predict(pairs)
        except Exception:
            return self._lexical.rerank(query, candidates, top_k=top_k)
        scored: list[ScoredChunk] = []
        for c, s in zip(candidates, scores):
            scored.append(
                ScoredChunk(
                    chunk=c.chunk,
                    document=c.document,
                    score=float(s),
                    vector_score=c.vector_score,
                    bm25_score=c.bm25_score,
                )
            )
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]
