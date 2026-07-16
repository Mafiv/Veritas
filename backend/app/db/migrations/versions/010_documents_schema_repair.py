"""010 documents_schema_repair — add missing active_version_id / chunk FKs

Revision ID: 010_documents_schema_repair
Revises: 009_plan_storage_bigint
Create Date: 2026-07-16
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010_documents_schema_repair"
down_revision: Union[str, Sequence[str], None] = "009_plan_storage_bigint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table
              AND column_name = :column
            """
        ),
        {"table": table, "column": column},
    )
    return result.scalar() is not None


def _has_constraint(name: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_schema = 'public' AND constraint_name = :name
            """
        ),
        {"name": name},
    )
    return result.scalar() is not None


def upgrade() -> None:
    if not _has_column("documents", "active_version_id"):
        op.add_column(
            "documents",
            sa.Column("active_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    if not _has_constraint("fk_documents_active_version"):
        op.create_foreign_key(
            "fk_documents_active_version",
            "documents",
            "document_versions",
            ["active_version_id"],
            ["id"],
            ondelete="SET NULL",
        )

    if not _has_column("document_chunks", "document_version_id"):
        op.add_column(
            "document_chunks",
            sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_index(
            "ix_document_chunks_document_version_id",
            "document_chunks",
            ["document_version_id"],
        )
        op.create_foreign_key(
            "fk_document_chunks_document_version_id",
            "document_chunks",
            "document_versions",
            ["document_version_id"],
            ["id"],
            ondelete="CASCADE",
        )

    if not _has_column("document_chunks", "embedding_model_id"):
        op.add_column(
            "document_chunks",
            sa.Column("embedding_model_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_index(
            "ix_document_chunks_embedding_model_id",
            "document_chunks",
            ["embedding_model_id"],
        )
        op.create_foreign_key(
            "fk_document_chunks_embedding_model_id",
            "document_chunks",
            "embedding_models",
            ["embedding_model_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    if _has_column("document_chunks", "embedding_model_id"):
        op.drop_constraint(
            "fk_document_chunks_embedding_model_id", "document_chunks", type_="foreignkey"
        )
        op.drop_index("ix_document_chunks_embedding_model_id", table_name="document_chunks")
        op.drop_column("document_chunks", "embedding_model_id")

    if _has_column("document_chunks", "document_version_id"):
        op.drop_constraint(
            "fk_document_chunks_document_version_id", "document_chunks", type_="foreignkey"
        )
        op.drop_index("ix_document_chunks_document_version_id", table_name="document_chunks")
        op.drop_column("document_chunks", "document_version_id")

    if _has_constraint("fk_documents_active_version"):
        op.drop_constraint("fk_documents_active_version", "documents", type_="foreignkey")

    if _has_column("documents", "active_version_id"):
        op.drop_column("documents", "active_version_id")
