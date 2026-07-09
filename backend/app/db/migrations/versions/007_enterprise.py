"""007 enterprise — webhooks, SSO, retention, GDPR exports, shared links

Revision ID: 007_enterprise
Revises: 006_audit_notifications
Create Date: 2026-07-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007_enterprise"
down_revision: Union[str, Sequence[str], None] = "006_audit_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

webhook_delivery_status = postgresql.ENUM(
    "pending", "success", "failed", name="webhook_delivery_status", create_type=False
)
sso_provider = postgresql.ENUM(
    "oidc", "saml", "google", "microsoft", name="sso_provider", create_type=False
)
export_job_type = postgresql.ENUM(
    "gdpr_user_export",
    "workspace_export",
    "document_export",
    name="export_job_type",
    create_type=False,
)
export_job_status = postgresql.ENUM(
    "queued", "processing", "ready", "failed", "expired", name="export_job_status", create_type=False
)
shared_link_resource_type = postgresql.ENUM(
    "thread", "document", "collection", name="shared_link_resource_type", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    for e in (
        webhook_delivery_status,
        sso_provider,
        export_job_type,
        export_job_status,
        shared_link_resource_type,
    ):
        e.create(bind, checkfirst=True)

    op.create_table(
        "webhook_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("secret_hash", sa.String(128), nullable=False),
        sa.Column("event_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_webhook_endpoints_workspace_id", "webhook_endpoints", ["workspace_id"])
    op.create_index("ix_webhook_endpoints_created_by", "webhook_endpoints", ["created_by"])
    op.create_index("ix_webhook_endpoints_deleted_at", "webhook_endpoints", ["deleted_at"])

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", webhook_delivery_status, nullable=False, server_default="pending"),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["endpoint_id"], ["webhook_endpoints.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_webhook_deliveries_endpoint_id", "webhook_deliveries", ["endpoint_id"])
    op.create_index(
        "ix_webhook_deliveries_endpoint_created", "webhook_deliveries", ["endpoint_id", "created_at"]
    )

    op.create_table(
        "sso_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sso_provider, nullable=False),
        sa.Column("issuer_url", sa.String(1000), nullable=True),
        sa.Column("client_id", sa.String(300), nullable=True),
        sa.Column("client_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("metadata_xml", sa.Text(), nullable=True),
        sa.Column("domains", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_enforced", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "provider", name="uq_sso_workspace_provider"),
    )
    op.create_index("ix_sso_connections_workspace_id", "sso_connections", ["workspace_id"])
    op.create_index("ix_sso_connections_deleted_at", "sso_connections", ["deleted_at"])

    op.create_table(
        "data_retention_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("retain_days", sa.Integer(), nullable=False),
        sa.Column("hard_delete", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "resource_type", name="uq_retention_workspace_resource"),
    )
    op.create_index("ix_data_retention_policies_workspace_id", "data_retention_policies", ["workspace_id"])

    op.create_table(
        "export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_type", export_job_type, nullable=False),
        sa.Column("status", export_job_status, nullable=False, server_default="queued"),
        sa.Column("celery_task_id", sa.String(120), nullable=True),
        sa.Column("storage_path", sa.String(1000), nullable=True),
        sa.Column("download_url", sa.String(1000), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_export_jobs_user_id", "export_jobs", ["user_id"])
    op.create_index("ix_export_jobs_workspace_id", "export_jobs", ["workspace_id"])
    op.create_index("ix_export_jobs_user_created", "export_jobs", ["user_id", "created_at"])
    op.create_index("ix_export_jobs_workspace_status", "export_jobs", ["workspace_id", "status"])

    op.create_table(
        "shared_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", shared_link_resource_type, nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("allow_download", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_shared_links_workspace_id", "shared_links", ["workspace_id"])
    op.create_index("ix_shared_links_created_by", "shared_links", ["created_by"])
    op.create_index("ix_shared_links_token_hash", "shared_links", ["token_hash"])
    op.create_index("ix_shared_links_resource", "shared_links", ["resource_type", "resource_id"])
    op.create_index("ix_shared_links_deleted_at", "shared_links", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("shared_links")
    op.drop_table("export_jobs")
    op.drop_table("data_retention_policies")
    op.drop_table("sso_connections")
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_endpoints")
    bind = op.get_bind()
    for e in (
        shared_link_resource_type,
        export_job_status,
        export_job_type,
        sso_provider,
        webhook_delivery_status,
    ):
        e.drop(bind, checkfirst=True)
