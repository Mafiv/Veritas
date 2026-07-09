"""Hybrid search: vector similarity + BM25 with Reciprocal Rank Fusion."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.domain import Document, DocumentChunk
from app.services.ingestion.embedder import Embedder, cosine_similarity
from app.services.retrieval import pgvector as pgvector_svc


@dataclass
class ScoredChunk:
    chunk: DocumentChunk
    document: Document
    score: float
    vector_score: float = 0.0
    bm25_score: float = 0.0


TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs: list[list[str]] = []
        self.doc_lens: list[int] = []
        self.df: Counter[str] = Counter()
        self.avgdl = 0.0
        self.N = 0

    def fit(self, corpus: list[str]) -> None:
        self.docs = [tokenize(doc) for doc in corpus]
        self.doc_lens = [len(d) for d in self.docs]
        self.N = len(self.docs)
        self.avgdl = sum(self.doc_lens) / self.N if self.N else 0.0
        self.df = Counter()
        for doc in self.docs:
            for term in set(doc):
                self.df[term] += 1

    def score(self, query: str) -> list[float]:
        q_terms = tokenize(query)
        scores = [0.0] * self.N
        if not self.N or not q_terms:
            return scores
        for i, doc in enumerate(self.docs):
            tf = Counter(doc)
            dl = self.doc_lens[i] or 1
            s = 0.0
            for term in q_terms:
                if term not in tf:
                    continue
                n_qi = self.df.get(term, 0)
                idf = math.log(1 + (self.N - n_qi + 0.5) / (n_qi + 0.5))
                freq = tf[term]
                denom = freq + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                s += idf * (freq * (self.k1 + 1)) / denom
            scores[i] = s
        return scores


def reciprocal_rank_fusion(
    ranked_lists: list[list[int]],
    *,
    k: int = 60,
    weights: list[float] | None = None,
) -> dict[int, float]:
    """Merge multiple ranked index lists via weighted RRF."""
    scores: dict[int, float] = defaultdict(float)
    weights = weights or [1.0] * len(ranked_lists)
    for weight, ranking in zip(weights, ranked_lists):
        for rank, idx in enumerate(ranking):
            scores[idx] += weight * (1.0 / (k + rank + 1))
    return dict(scores)


class HybridSearcher:
    def __init__(self, embedder: Embedder | None = None):
        self.embedder = embedder or Embedder()
        self.settings = get_settings()

    async def search(
        self,
        db: AsyncSession,
        *,
        workspace_id: UUID,
        query: str,
        query_embedding: Sequence[float] | None = None,
        document_ids: list[UUID] | None = None,
        top_k: int | None = None,
    ) -> list[ScoredChunk]:
        top_k = top_k or self.settings.retrieval_top_k
        if query_embedding is None:
            query_embedding = await self.embedder.embed_query(query)

        # Prefer native pgvector ANN for vector ranking when enabled
        if pgvector_svc.pgvector_enabled():
            pg_hits = await pgvector_svc.vector_search_ids(
                db,
                workspace_id=workspace_id,
                query_embedding=query_embedding,
                document_ids=document_ids,
                limit=max(top_k * 3, 40),
            )
            if pg_hits:
                return await self._fuse_with_pgvector(
                    db,
                    workspace_id=workspace_id,
                    query=query,
                    query_embedding=query_embedding,
                    document_ids=document_ids,
                    pg_hits=pg_hits,
                    top_k=top_k,
                )

        return await self._search_json(
            db,
            workspace_id=workspace_id,
            query=query,
            query_embedding=query_embedding,
            document_ids=document_ids,
            top_k=top_k,
        )

    async def _search_json(
        self,
        db: AsyncSession,
        *,
        workspace_id: UUID,
        query: str,
        query_embedding: Sequence[float],
        document_ids: list[UUID] | None,
        top_k: int,
    ) -> list[ScoredChunk]:
        stmt = (
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.workspace_id == workspace_id)
            .where(DocumentChunk.embedding.is_not(None))
            .where(Document.deleted_at.is_(None))
        )
        if document_ids is not None:
            if not document_ids:
                return []
            stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))

        result = await db.execute(stmt)
        rows = list(result.all())
        if not rows:
            return []

        chunks = [r[0] for r in rows]
        documents = {r[0].id: r[1] for r in rows}
        corpus = [c.content for c in chunks]

        vector_scores = [
            cosine_similarity(query_embedding, c.embedding or []) for c in chunks
        ]
        vector_ranked = sorted(
            range(len(chunks)), key=lambda i: vector_scores[i], reverse=True
        )

        bm25 = BM25Index()
        bm25.fit(corpus)
        bm25_scores = bm25.score(query)
        bm25_ranked = sorted(
            range(len(chunks)), key=lambda i: bm25_scores[i], reverse=True
        )

        fused = reciprocal_rank_fusion(
            [vector_ranked, bm25_ranked],
            weights=[
                self.settings.hybrid_vector_weight,
                self.settings.hybrid_bm25_weight,
            ],
        )
        ordered = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results: list[ScoredChunk] = []
        for idx, score in ordered:
            chunk = chunks[idx]
            results.append(
                ScoredChunk(
                    chunk=chunk,
                    document=documents[chunk.id],
                    score=score,
                    vector_score=vector_scores[idx],
                    bm25_score=bm25_scores[idx],
                )
            )
        return results

    async def _fuse_with_pgvector(
        self,
        db: AsyncSession,
        *,
        workspace_id: UUID,
        query: str,
        query_embedding: Sequence[float],
        document_ids: list[UUID] | None,
        pg_hits: list[tuple[UUID, float]],
        top_k: int,
    ) -> list[ScoredChunk]:
        # Load candidate pool: pgvector top hits ∪ BM25 corpus (JSON path limited set)
        hit_ids = [hid for hid, _ in pg_hits]
        stmt = (
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.workspace_id == workspace_id)
            .where(Document.deleted_at.is_(None))
            .where(
                (DocumentChunk.id.in_(hit_ids))
                | (DocumentChunk.embedding.is_not(None))
            )
        )
        if document_ids is not None:
            stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
        # Cap in-memory BM25 corpus for large workspaces
        stmt = stmt.limit(max(500, top_k * 20))

        rows = list((await db.execute(stmt)).all())
        if not rows:
            return []

        chunks = [r[0] for r in rows]
        documents = {r[0].id: r[1] for r in rows}

        pg_scores = {hid: score for hid, score in pg_hits}
        vector_scores = [
            pg_scores.get(
                c.id,
                cosine_similarity(query_embedding, c.embedding or []),
            )
            for c in chunks
        ]
        vector_ranked = sorted(
            range(len(chunks)), key=lambda i: vector_scores[i], reverse=True
        )

        bm25 = BM25Index()
        bm25.fit([c.content for c in chunks])
        bm25_scores = bm25.score(query)
        bm25_ranked = sorted(
            range(len(chunks)), key=lambda i: bm25_scores[i], reverse=True
        )

        fused = reciprocal_rank_fusion(
            [vector_ranked, bm25_ranked],
            weights=[
                self.settings.hybrid_vector_weight,
                self.settings.hybrid_bm25_weight,
            ],
        )
        ordered = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results: list[ScoredChunk] = []
        for idx, score in ordered:
            chunk = chunks[idx]
            results.append(
                ScoredChunk(
                    chunk=chunk,
                    document=documents[chunk.id],
                    score=score,
                    vector_score=vector_scores[idx],
                    bm25_score=bm25_scores[idx],
                )
            )
        return results
