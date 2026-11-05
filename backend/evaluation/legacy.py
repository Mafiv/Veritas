"""The retrieval pipeline as it was before the pgvector refactor (commit e66665f).

Reproduced faithfully so the evaluation can compare against it: load *every*
chunk of the workspace, compute cosine similarity in pure Python, fit an
in-memory BM25 index per query, fuse with weighted RRF, then apply the
term-overlap "reranker". Only the embeddings differ: both pipelines read the
same stored vectors, so the comparison isolates the retrieval design.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Document, DocumentChunk
from app.services.ingestion.embedder import cosine_similarity
from app.services.retrieval.hybrid_search import BM25Index, ScoredChunk, reciprocal_rank_fusion
from app.services.retrieval.reranker import LexicalReranker


async def legacy_search(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    query: str,
    query_embedding: Sequence[float],
    top_k: int = 20,
    rerank_top_k: int = 10,
    vector_weight: float = 0.6,
    bm25_weight: float = 0.4,
) -> list[ScoredChunk]:
    rows = (
        await db.execute(
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.workspace_id == workspace_id)
            .where(DocumentChunk.embedding.is_not(None))
            .where(Document.deleted_at.is_(None))
        )
    ).all()
    if not rows:
        return []
    chunks = [r[0] for r in rows]
    docs = {r[0].id: r[1] for r in rows}
    q = list(query_embedding)

    vector_scores = [cosine_similarity(q, list(c.embedding)) for c in chunks]
    vector_ranked = sorted(range(len(chunks)), key=lambda i: vector_scores[i], reverse=True)

    bm25 = BM25Index()
    bm25.fit([c.content for c in chunks])
    bm25_scores = bm25.score(query)
    bm25_ranked = sorted(range(len(chunks)), key=lambda i: bm25_scores[i], reverse=True)

    fused = reciprocal_rank_fusion(
        [vector_ranked, bm25_ranked], weights=[vector_weight, bm25_weight]
    )
    ordered = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]
    candidates = [
        ScoredChunk(
            chunk=chunks[i],
            document=docs[chunks[i].id],
            score=s,
            vector_score=vector_scores[i],
            keyword_score=bm25_scores[i],
        )
        for i, s in ordered
    ]
    return await LexicalReranker().rerank(query, candidates, top_k=rerank_top_k)
