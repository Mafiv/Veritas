"""Shared mixins, enums, and column helpers for Veritas domain models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.session import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


# ── Enums ─────────────────────────────────────────────────────────────────────


class PlanTier(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"


class WorkspaceRole(str, enum.Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class DocumentType(str, enum.Enum):
    PDF = "pdf"
    MARKDOWN = "markdown"
    TEXT = "text"
    NOTION = "notion"
    DOCX = "docx"


class InvitationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class FeedbackVote(str, enum.Enum):
    UP = "up"
    DOWN = "down"


class SubscriptionStatus(str, enum.Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"
    UNPAID = "unpaid"


class UsageEventType(str, enum.Enum):
    QUERY = "query"
    TOKEN = "token"
    CHUNK = "chunk"
    UPLOAD = "upload"
    EMBEDDING = "embedding"


class IngestionJobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class IngestionJobStage(str, enum.Enum):
    PARSE = "parse"
    CHUNK = "chunk"
    EMBED = "embed"
    SUMMARIZE = "summarize"
    INDEX = "index"


class EntityType(str, enum.Enum):
    PERSON = "person"
    ORGANIZATION = "organization"
    DATE = "date"
    CONCEPT = "concept"
    LOCATION = "location"
    OTHER = "other"


class PermissionScope(str, enum.Enum):
    DOCUMENT = "document"
    PAGE_RANGE = "page_range"
    SECTION = "section"


class NotificationChannel(str, enum.Enum):
    IN_APP = "in_app"
    EMAIL = "email"


class ExportJobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    EXPIRED = "expired"


class ExportJobType(str, enum.Enum):
    GDPR_USER_EXPORT = "gdpr_user_export"
    WORKSPACE_EXPORT = "workspace_export"
    DOCUMENT_EXPORT = "document_export"


class WebhookDeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class SsoProvider(str, enum.Enum):
    OIDC = "oidc"
    SAML = "saml"
    GOOGLE = "google"
    MICROSOFT = "microsoft"


class SharedLinkResourceType(str, enum.Enum):
    THREAD = "thread"
    DOCUMENT = "document"
    COLLECTION = "collection"


# ── Mixins ────────────────────────────────────────────────────────────────────


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Recoverable entities (users, workspaces, documents, threads, keys, etc.)."""

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


__all__ = [
    "Base",
    "JSONType",
    "UUID",
    "TimestampMixin",
    "SoftDeleteMixin",
    "new_uuid",
    "PlanTier",
    "WorkspaceRole",
    "DocumentStatus",
    "DocumentType",
    "InvitationStatus",
    "MessageRole",
    "FeedbackVote",
    "SubscriptionStatus",
    "UsageEventType",
    "IngestionJobStatus",
    "IngestionJobStage",
    "EntityType",
    "PermissionScope",
    "NotificationChannel",
    "ExportJobStatus",
    "ExportJobType",
    "WebhookDeliveryStatus",
    "SsoProvider",
    "SharedLinkResourceType",
]
