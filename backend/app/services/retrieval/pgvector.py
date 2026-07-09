"""Optional pgvector helpers — dual-write/read alongside JSON embeddings."""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.monitoring.logger import get_logger

log = get_logger("veritas.pgvector")

PGVECTOR_SETUP_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE document_chunks
  ADD COLUMN IF NOT EXISTS embedding_vec vector(1536);
CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_vec
  ON document_chunks USING ivfflat (embedding_vec vector_cosine_ops)
  WITH (lists = 100);
"""


def pgvector_enabled() -> bool:
    return bool(get_settings().use_pgvector)


def describe_vector_strategy() -> dict:
    settings = get_settings()
    return {
        "use_pgvector": settings.use_pgvector,
        "embedding_dimensions": settings.embedding_dimensions,
        "storage": (
            "json_plus_pgvector" if settings.use_pgvector else "json_on_document_chunks"
        ),
        "note": (
            "JSON embeddings always written. When USE_PGVECTOR=true, embedding_vec is "
            "dual-written and hybrid search uses <=> cosine distance for vector ranking."
        ),
        "setup_sql_available": True,
        "migration": "008_pgvector",
    }


async def ensure_pgvector_extension(conn) -> bool:
    if not pgvector_enabled():
        return False
    try:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        log.info("pgvector.extension_ready")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("pgvector.extension_failed", error=str(exc))
        return False


def _vector_literal(embedding: Sequence[float]) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in embedding) + "]"


async def write_embedding_vec(
    db: AsyncSession,
    *,
    chunk_id: UUID,
    embedding: Sequence[float],
) -> None:
    """Dual-write native vector column. No-op when pgvector disabled."""
    if not pgvector_enabled() or not embedding:
        return
    lit = _vector_literal(embedding)
    try:
        await db.execute(
            text(
                "UPDATE document_chunks SET embedding_vec = CAST(:vec AS vector) "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {"vec": lit, "id": str(chunk_id)},
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("pgvector.write_failed", chunk_id=str(chunk_id), error=str(exc))


async def backfill_embedding_vecs(db: AsyncSession, *, limit: int = 500) -> int:
    """Copy JSON embeddings into embedding_vec for rows missing the vector."""
    if not pgvector_enabled():
        return 0
    result = await db.execute(
        text(
            """
            SELECT id, embedding FROM document_chunks
            WHERE embedding IS NOT NULL
              AND embedding_vec IS NULL
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    rows = result.all()
    updated = 0
    for row in rows:
        emb = row.embedding
        if not emb:
            continue
        await write_embedding_vec(db, chunk_id=row.id, embedding=emb)
        updated += 1
    await db.flush()
    return updated


async def vector_search_ids(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    query_embedding: Sequence[float],
    document_ids: list[UUID] | None,
    limit: int,
) -> list[tuple[UUID, float]]:
    """
    Return (chunk_id, cosine_similarity) using pgvector <=> operator.
    Similarity ≈ 1 - cosine_distance.
    """
    if not pgvector_enabled() or not query_embedding:
        return []
    lit = _vector_literal(query_embedding)
    params: dict = {
        "vec": lit,
        "workspace_id": str(workspace_id),
        "limit": limit,
    }
    doc_filter = ""
    if document_ids is not None:
        if not document_ids:
            return []
        placeholders = []
        for i, did in enumerate(document_ids):
            key = f"d{i}"
            placeholders.append(f"CAST(:{key} AS uuid)")
            params[key] = str(did)
        doc_filter = f"AND dc.document_id IN ({', '.join(placeholders)})"

    sql = f"""
        SELECT dc.id,
               (1 - (dc.embedding_vec <=> CAST(:vec AS vector))) AS score
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        WHERE dc.workspace_id = CAST(:workspace_id AS uuid)
          AND dc.embedding_vec IS NOT NULL
          AND d.deleted_at IS NULL
          {doc_filter}
        ORDER BY dc.embedding_vec <=> CAST(:vec AS vector)
        LIMIT :limit
    """
    try:
        result = await db.execute(text(sql), params)
        return [(row.id, float(row.score or 0.0)) for row in result.all()]
    except Exception as exc:  # noqa: BLE001
        log.warning("pgvector.search_failed", error=str(exc))
        return []
