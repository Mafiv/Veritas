"""008 pgvector — native vector column + IVFFlat index on document_chunks

Revision ID: 008_pgvector
Revises: 007_enterprise
Create Date: 2026-07-09

Adds embedding_vec alongside JSON embeddings for dual-write/read.
Requires the pgvector extension (available on pgvector/pgvector:pg16).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "008_pgvector"
down_revision: Union[str, Sequence[str], None] = "007_enterprise"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extension may already exist on the pgvector image
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Default dimensions match Settings.embedding_dimensions (1536)
    op.execute(
        "ALTER TABLE document_chunks "
        "ADD COLUMN IF NOT EXISTS embedding_vec vector(1536)"
    )

    # IVFFlat needs data to be useful; create if missing.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'ix_document_chunks_embedding_vec'
            ) THEN
                CREATE INDEX ix_document_chunks_embedding_vec
                    ON document_chunks
                    USING ivfflat (embedding_vec vector_cosine_ops)
                    WITH (lists = 100);
            END IF;
        END$$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_vec")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding_vec")
