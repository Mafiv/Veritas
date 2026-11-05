"""Hybrid search against real Postgres: HNSW, full-text, RRF and scoping."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import DocumentChunk
from app.services.ingestion.embedder import Embedder, MockEmbeddingProvider
from app.services.retrieval.hybrid_search import HybridSearcher

from .conftest import make_document, make_workspace

TEXTS = [
    "Refunds are issued within 30 days of purchase if the product is unused.",
    "Our office is closed on public holidays and weekends.",
    "Enterprise customers get a dedicated support engineer and 99.9% uptime SLA.",
    "Passwords must be rotated every 90 days according to the security policy.",
]


async def _seed(db: AsyncSession, embedder: Embedder, ws, user, name: str, texts: list[str]):
    doc = await make_document(db, user, ws, name)
    vectors = await embedder.embed_texts(texts)
    for i, (t, v) in enumerate(zip(texts, vectors)):
        db.add(
            DocumentChunk(
                document_id=doc.id,
                workspace_id=ws.id,
                chunk_index=i,
                content=t,
                token_count=len(t) // 4,
                embedding=v,
            )
        )
    await db.flush()
    return doc


def _searcher() -> HybridSearcher:
    # Mock vectors are hash-based: identical text => identical vector, which lets
    # us assert exact nearest-neighbour behaviour without downloading a model.
    return HybridSearcher(Embedder(MockEmbeddingProvider(384)))


async def test_vector_search_finds_exact_match(db: AsyncSession) -> None:
    searcher = _searcher()
    user, ws = await make_workspace(db)
    await _seed(db, searcher.embedder, ws, user, "policy.txt", TEXTS)

    hits = await searcher.search(db, workspace_id=ws.id, query=TEXTS[2], mode="vector", top_k=3)
    assert hits[0].chunk.content == TEXTS[2]
    assert abs(hits[0].vector_score - 1.0) < 1e-5


async def test_keyword_search_uses_stemming_and_or_semantics(db: AsyncSession) -> None:
    searcher = _searcher()
    user, ws = await make_workspace(db)
    await _seed(db, searcher.embedder, ws, user, "policy.txt", TEXTS)

    # "refunded" stems to "refund"; "spaceship" matches nothing but must not
    # turn the query into a no-match (OR semantics, not AND).
    hits = await searcher.search(
        db, workspace_id=ws.id, query="when are refunded spaceship purchases", mode="keyword"
    )
    assert hits and hits[0].chunk.content == TEXTS[0]
    assert hits[0].keyword_score > 0


async def test_hybrid_fuses_both_rankings(db: AsyncSession) -> None:
    searcher = _searcher()
    user, ws = await make_workspace(db)
    await _seed(db, searcher.embedder, ws, user, "policy.txt", TEXTS)

    hits = await searcher.search(db, workspace_id=ws.id, query=TEXTS[3], top_k=4)
    assert hits[0].chunk.content == TEXTS[3]
    assert hits[0].vector_score > 0.99 and hits[0].keyword_score > 0
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


async def test_search_never_crosses_workspaces(db: AsyncSession) -> None:
    searcher = _searcher()
    user_a, ws_a = await make_workspace(db)
    user_b, ws_b = await make_workspace(db)
    await _seed(db, searcher.embedder, ws_a, user_a, "a.txt", TEXTS[:2])
    await _seed(db, searcher.embedder, ws_b, user_b, "b.txt", ["Refunds secret text for B."])

    hits = await searcher.search(db, workspace_id=ws_a.id, query="refunds secret text for B")
    assert hits, "workspace A should still get its own results"
    assert all(h.chunk.workspace_id == ws_a.id for h in hits)


async def test_deleted_and_out_of_scope_documents_are_excluded(db: AsyncSession) -> None:
    searcher = _searcher()
    user, ws = await make_workspace(db)
    keep = await _seed(db, searcher.embedder, ws, user, "keep.txt", [TEXTS[0]])
    gone = await _seed(db, searcher.embedder, ws, user, "gone.txt", [TEXTS[0] + " (old)"])
    other = await _seed(db, searcher.embedder, ws, user, "other.txt", [TEXTS[1]])
    gone.deleted_at = datetime.now(timezone.utc)
    await db.flush()

    hits = await searcher.search(db, workspace_id=ws.id, query="refunds purchase")
    assert {h.document.id for h in hits} <= {keep.id, other.id}

    scoped = await searcher.search(
        db, workspace_id=ws.id, query="refunds purchase", document_ids=[other.id]
    )
    assert {h.document.id for h in scoped} == {other.id}
    assert await searcher.search(db, workspace_id=ws.id, query="x", document_ids=[]) == []
