"""Enterprise extras: webhooks, SSO, retention, GDPR exports, shared links."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.domain.base import (
    enum_values,
    Base,
    ExportJobStatus,
    ExportJobType,
    JSONType,
    SharedLinkResourceType,
    SoftDeleteMixin,
    SsoProvider,
    TimestampMixin,
    UUID,
    WebhookDeliveryStatus,
    new_uuid,
)


class WebhookEndpoint(Base, TimestampMixin, SoftDeleteMixin):
    """Outbound webhook subscriptions for workspace events."""

    __tablename__ = "webhook_endpoints"
    __table_args__ = (Index("ix_webhook_endpoints_workspace_id", "workspace_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    event_types: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    deliveries: Mapped[list[WebhookDelivery]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )


class WebhookDelivery(Base, TimestampMixin):
    """Delivery attempts for webhook endpoints (retry / debug)."""

    __tablename__ = "webhook_deliveries"
    __table_args__ = (Index("ix_webhook_deliveries_endpoint_created", "endpoint_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False)
    status: Mapped[WebhookDeliveryStatus] = mapped_column(
        Enum(WebhookDeliveryStatus, values_callable=enum_values, name="webhook_delivery_status"),
        default=WebhookDeliveryStatus.PENDING,
        nullable=False,
    )
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    endpoint: Mapped[WebhookEndpoint] = relationship(back_populates="deliveries")


class SsoConnection(Base, TimestampMixin, SoftDeleteMixin):
    """Workspace/org SSO (OIDC/SAML) configuration."""

    __tablename__ = "sso_connections"
    __table_args__ = (
        UniqueConstraint("workspace_id", "provider", name="uq_sso_workspace_provider"),
        Index("ix_sso_connections_workspace_id", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[SsoProvider] = mapped_column(
        Enum(SsoProvider, values_callable=enum_values, name="sso_provider"), nullable=False
    )
    issuer_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    client_id: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    # Encrypted at application layer before persist.
    client_secret_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_xml: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    domains: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    is_enforced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    meta: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)


class DataRetentionPolicy(Base, TimestampMixin):
    """Per-workspace retention rules for GDPR/CCPA compliance."""

    __tablename__ = "data_retention_policies"
    __table_args__ = (
        UniqueConstraint("workspace_id", "resource_type", name="uq_retention_workspace_resource"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    retain_days: Mapped[int] = mapped_column(Integer, nullable=False)
    hard_delete: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ExportJob(Base, TimestampMixin):
    """GDPR / workspace data export jobs."""

    __tablename__ = "export_jobs"
    __table_args__ = (
        Index("ix_export_jobs_user_created", "user_id", "created_at"),
        Index("ix_export_jobs_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True
    )
    job_type: Mapped[ExportJobType] = mapped_column(
        Enum(ExportJobType, values_callable=enum_values, name="export_job_type"), nullable=False
    )
    status: Mapped[ExportJobStatus] = mapped_column(
        Enum(ExportJobStatus, values_callable=enum_values, name="export_job_status"),
        default=ExportJobStatus.QUEUED,
        nullable=False,
    )
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    storage_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    download_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)


class SharedLink(Base, TimestampMixin, SoftDeleteMixin):
    """Public/expiring share links for threads, documents, or collections."""

    __tablename__ = "shared_links"
    __table_args__ = (
        Index("ix_shared_links_workspace_id", "workspace_id"),
        Index("ix_shared_links_token_hash", "token_hash"),
        Index("ix_shared_links_resource", "resource_type", "resource_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    resource_type: Mapped[SharedLinkResourceType] = mapped_column(
        Enum(SharedLinkResourceType, values_callable=enum_values, name="shared_link_resource_type"),
        nullable=False,
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    allow_download: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    meta: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
