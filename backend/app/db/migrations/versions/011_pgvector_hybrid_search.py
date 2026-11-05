"""011 pgvector + full-text search on document_chunks

Revision ID: 011_pgvector_hybrid_search
Revises: 010_documents_schema_repair
Create Date: 2026-11-05

Replaces the JSONB embedding column (scanned in Python on every query) with:

- ``embedding vector(384)`` + HNSW index (cosine) for approximate nearest
  neighbour search inside Postgres;
- ``content_tsv`` generated ``tsvector`` + GIN index for keyword search.

Existing JSONB embeddings came from a different model/width (1536-d OpenAI or
hash-based mock vectors) and cannot be converted, so the column is dropped and
chunks must be re-embedded once::

    python -m app.cli.reembed

Chunks stay keyword-searchable in the meantime.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "011_pgvector_hybrid_search"
down_revision: Union[str, Sequence[str], None] = "010_documents_schema_repair"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DIMENSIONS = 384
TSV_EXPRESSION = "to_tsvector('english', coalesce(heading, '') || ' ' || content)"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.drop_column("document_chunks", "embedding")
    op.execute(f"ALTER TABLE document_chunks ADD COLUMN embedding vector({DIMENSIONS})")
    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN content_tsv tsvector "
        f"GENERATED ALWAYS AS ({TSV_EXPRESSION}) STORED"
    )

    # HNSW (not IVFFlat): no training step, so it is accurate from the first row
    # and does not need rebuilding as the corpus grows.
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_content_tsv ON document_chunks USING gin (content_tsv)"
    )

    # Register the local model as the default embedding model.
    op.execute("UPDATE embedding_models SET is_default = false")
    op.execute(
        "INSERT INTO embedding_models (id, name, provider, model_id, dimensions, is_default, "
        "is_active, created_at, updated_at) VALUES (gen_random_uuid(), 'bge-small-en-v1.5', "
        f"'local', 'BAAI/bge-small-en-v1.5', {DIMENSIONS}, true, true, now(), now()) "
        "ON CONFLICT (name) DO UPDATE SET is_default = true, dimensions = EXCLUDED.dimensions"
    )
    op.execute("UPDATE document_chunks SET embedding_model_id = NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_tsv")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.drop_column("document_chunks", "content_tsv")
    op.drop_column("document_chunks", "embedding")
    op.add_column(
        "document_chunks",
        sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute("DELETE FROM embedding_models WHERE name = 'bge-small-en-v1.5'")
    op.execute(
        "UPDATE embedding_models SET is_default = true WHERE name = 'text-embedding-3-small'"
    )
