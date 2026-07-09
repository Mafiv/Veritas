"""Cross-encoder style reranker (mock-friendly)."""

from __future__ import annotations

import math
import re
from collections import Counter

from app.services.retrieval.hybrid_search import ScoredChunk, tokenize


class CrossEncoderReranker:
    """
    Lightweight lexical cross-encoder stand-in.
    When a real model (e.g. MiniLM) is available, swap score() for model inference.
    """

    def rerank(self, query: str, candidates: list[ScoredChunk], top_k: int = 8) -> list[ScoredChunk]:
        scored: list[ScoredChunk] = []
        for c in candidates:
            lexical = self._pair_score(query, c.chunk.content)
            # Blend original fusion score with pair score
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
        # Soft length prior — prefer denser relevant passages
        density = overlap / math.sqrt(len(p))
        # Phrase boost for contiguous query bigrams
        bigram_boost = 0.0
        passage_lower = passage.lower()
        for i in range(len(q) - 1):
            phrase = f"{q[i]} {q[i + 1]}"
            if phrase in passage_lower:
                bigram_boost += 0.1
        return min(1.0, coverage * 0.7 + density * 0.2 + bigram_boost)
