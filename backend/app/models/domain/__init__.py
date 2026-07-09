"""Veritas domain models — split by domain, re-exported for backward compatibility.

Import from ``app.models.domain`` as before, or from domain-specific modules.
"""

from app.models.domain.audit import AuditLog, LoginHistory
from app.models.domain.base import (
    Base,
    DocumentStatus,
    DocumentType,
    EntityType,
    ExportJobStatus,
    ExportJobType,
    FeedbackVote,
    IngestionJobStage,
    IngestionJobStatus,
    InvitationStatus,
    JSONType,
    MessageRole,
    NotificationChannel,
    PermissionScope,
    PlanTier,
    SharedLinkResourceType,
    SoftDeleteMixin,
    SsoProvider,
    SubscriptionStatus,
    TimestampMixin,
    UsageEventType,
    WebhookDeliveryStatus,
    WorkspaceRole,
)
from app.models.domain.billing import Invoice, Plan, Subscription, UsageEvent, UsageMeter
from app.models.domain.chat import (
    ChatMessage,
    ChatThread,
    ChatThreadDocument,
    MessageCitation,
    MessageFeedback,
    ThreadComment,
)
from app.models.domain.documents import (
    Collection,
    CollectionDocument,
    Document,
    DocumentChunk,
    DocumentEntity,
    DocumentPermission,
    DocumentSummary,
    DocumentVersion,
    EmbeddingModel,
    Entity,
    EntityRelationship,
    IngestionJob,
    SuggestedQuestion,
)
from app.models.domain.enterprise import (
    DataRetentionPolicy,
    ExportJob,
    SharedLink,
    SsoConnection,
    WebhookDelivery,
    WebhookEndpoint,
)
from app.models.domain.identity import (
    ApiKey,
    Invitation,
    RefreshToken,
    User,
    Workspace,
    WorkspaceMember,
)
from app.models.domain.notifications import Notification, NotificationPreference

__all__ = [
    # mixins / enums
    "Base",
    "TimestampMixin",
    "SoftDeleteMixin",
    "JSONType",
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
    # identity
    "User",
    "Workspace",
    "WorkspaceMember",
    "Invitation",
    "RefreshToken",
    "ApiKey",
    # documents
    "EmbeddingModel",
    "Document",
    "DocumentVersion",
    "DocumentChunk",
    "DocumentSummary",
    "SuggestedQuestion",
    "DocumentPermission",
    "Collection",
    "CollectionDocument",
    "Entity",
    "DocumentEntity",
    "EntityRelationship",
    "IngestionJob",
    # chat
    "ChatThread",
    "ChatThreadDocument",
    "ChatMessage",
    "MessageCitation",
    "MessageFeedback",
    "ThreadComment",
    # billing
    "Plan",
    "Subscription",
    "UsageEvent",
    "UsageMeter",
    "Invoice",
    # audit
    "AuditLog",
    "LoginHistory",
    # notifications
    "Notification",
    "NotificationPreference",
    # enterprise
    "WebhookEndpoint",
    "WebhookDelivery",
    "SsoConnection",
    "DataRetentionPolicy",
    "ExportJob",
    "SharedLink",
]
