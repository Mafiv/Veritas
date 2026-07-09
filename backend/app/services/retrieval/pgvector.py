"""Optional pgvector helpers — JSON embeddings remain the portable default."""

from __future__ import annotations

from app.core.config import get_settings
from app.services.monitoring.logger import get_logger

log = get_logger("veritas.pgvector")

# SQL to enable when use_pgvector=true and running on Postgres with the extension.
PGVECTOR_SETUP_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

-- Example: add a dedicated vector column alongside JSON embeddings.
-- ALTER TABLE document_chunks
--   ADD COLUMN IF NOT EXISTS embedding_vec vector(1536);

-- CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_vec
--   ON document_chunks USING ivfflat (embedding_vec vector_cosine_ops)
--   WITH (lists = 100);
"""


def pgvector_enabled() -> bool:
    return bool(get_settings().use_pgvector)


def describe_vector_strategy() -> dict:
    """Runtime introspection for admin/health — does not change retrieval path yet."""
    settings = get_settings()
    return {
        "use_pgvector": settings.use_pgvector,
        "embedding_dimensions": settings.embedding_dimensions,
        "storage": "json_on_document_chunks",
        "note": (
            "Embeddings stay on document_chunks.embedding (JSON) for portability. "
            "Set USE_PGVECTOR=true and apply PGVECTOR_SETUP_SQL when ready for native indexes."
        ),
        "setup_sql_available": True,
    }


async def ensure_pgvector_extension(conn) -> bool:
    """Best-effort CREATE EXTENSION — safe no-op when disabled or unsupported."""
    if not pgvector_enabled():
        return False
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        log.info("pgvector.extension_ready")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("pgvector.extension_failed", error=str(exc))
        return False
