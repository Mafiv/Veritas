"""Extended Pydantic schemas for normalized Veritas tables."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.domain import (
    ExportJobStatus,
    ExportJobType,
    FeedbackVote,
    IngestionJobStage,
    IngestionJobStatus,
    InvitationStatus,
    PlanTier,
    SharedLinkResourceType,
    SubscriptionStatus,
    WorkspaceRole,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Identity ──────────────────────────────────────────────────────────────────


class InvitationCreate(BaseModel):
    email: EmailStr
    role: WorkspaceRole = WorkspaceRole.VIEWER


class InvitationOut(ORMModel):
    id: UUID
    workspace_id: UUID
    email: EmailStr
    role: WorkspaceRole
    status: InvitationStatus
    expires_at: datetime
    created_at: datetime
    accepted_at: Optional[datetime] = None


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scopes: list[str] = Field(default_factory=lambda: ["documents:read", "chat:write"])
    expires_at: Optional[datetime] = None


class ApiKeyOut(ORMModel):
    id: UUID
    workspace_id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    # plaintext only returned once on create
    secret: Optional[str] = None


class RefreshTokenOut(ORMModel):
    id: UUID
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    user_agent: Optional[str] = None
    created_at: datetime


# ── Documents ─────────────────────────────────────────────────────────────────


class DocumentVersionOut(ORMModel):
    id: UUID
    document_id: UUID
    version_number: int
    is_active: bool
    file_size: int
    content_hash: Optional[str] = None
    change_note: Optional[str] = None
    created_at: datetime


class DocumentSummaryOut(ORMModel):
    id: UUID
    document_id: UUID
    summary_text: str
    summary_type: str
    model_name: Optional[str] = None
    created_at: datetime


class SuggestedQuestionOut(ORMModel):
    id: UUID
    document_id: UUID
    question: str
    rank: int


class DocumentPermissionCreate(BaseModel):
    user_id: UUID
    scope: str = "document"
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    section_heading: Optional[str] = None
    can_read: bool = True
    can_cite: bool = True


class DocumentPermissionOut(ORMModel):
    id: UUID
    document_id: UUID
    user_id: UUID
    scope: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    can_read: bool
    can_cite: bool


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    document_ids: list[UUID] = Field(default_factory=list)


class CollectionOut(ORMModel):
    id: UUID
    workspace_id: UUID
    name: str
    description: Optional[str] = None
    created_at: datetime
    document_count: int = 0


class EntityOut(ORMModel):
    id: UUID
    workspace_id: UUID
    name: str
    entity_type: str
    normalized_name: str


class IngestionJobOut(ORMModel):
    id: UUID
    document_id: UUID
    status: IngestionJobStatus
    stage: IngestionJobStage
    error_message: Optional[str] = None
    retry_count: int
    created_at: datetime
    finished_at: Optional[datetime] = None


# ── Chat ──────────────────────────────────────────────────────────────────────


class MessageCitationOut(ORMModel):
    id: UUID
    message_id: UUID
    chunk_id: UUID
    document_id: UUID
    citation_index: int
    snippet: str
    score: float
    page_number: Optional[int] = None
    heading: Optional[str] = None


class MessageFeedbackCreate(BaseModel):
    vote: FeedbackVote
    comment: Optional[str] = Field(default=None, max_length=2000)


class MessageFeedbackOut(ORMModel):
    id: UUID
    message_id: UUID
    user_id: UUID
    vote: FeedbackVote
    comment: Optional[str] = None
    created_at: datetime


class ThreadCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    parent_comment_id: Optional[UUID] = None


class ThreadCommentOut(ORMModel):
    id: UUID
    thread_id: UUID
    user_id: UUID
    body: str
    parent_comment_id: Optional[UUID] = None
    created_at: datetime


# ── Billing ───────────────────────────────────────────────────────────────────


class PlanOut(ORMModel):
    id: UUID
    code: PlanTier
    name: str
    description: Optional[str] = None
    price_cents_monthly: int
    queries_per_day: int
    documents_limit: int
    workspaces_limit: int
    storage_bytes_limit: int
    seats_limit: int
    features: Optional[dict[str, Any]] = None


class SubscriptionOut(ORMModel):
    id: UUID
    user_id: UUID
    plan_id: UUID
    status: SubscriptionStatus
    stripe_customer_id: Optional[str] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False


class InvoiceOut(ORMModel):
    id: UUID
    stripe_invoice_id: str
    status: str
    amount_due_cents: int
    amount_paid_cents: int
    currency: str
    hosted_invoice_url: Optional[str] = None
    paid_at: Optional[datetime] = None
    created_at: datetime


class UsageMeterOut(ORMModel):
    workspace_id: UUID
    meter_key: str
    period_start: datetime
    period_end: datetime
    quantity: int


# ── Notifications ─────────────────────────────────────────────────────────────


class NotificationOut(ORMModel):
    id: UUID
    type: str
    title: str
    body: Optional[str] = None
    link_url: Optional[str] = None
    read_at: Optional[datetime] = None
    created_at: datetime


class NotificationPreferenceUpdate(BaseModel):
    event_type: str
    channel: str
    enabled: bool


class NotificationPreferenceOut(BaseModel):
    id: UUID
    event_type: str
    channel: str
    enabled: bool


# ── Enterprise ────────────────────────────────────────────────────────────────


class WebhookEndpointCreate(BaseModel):
    url: str = Field(min_length=8, max_length=1000)
    event_types: list[str]
    description: Optional[str] = None


class WebhookEndpointOut(ORMModel):
    id: UUID
    workspace_id: UUID
    url: str
    event_types: list[str]
    is_active: bool
    description: Optional[str] = None
    created_at: datetime


class SsoConnectionCreate(BaseModel):
    provider: str
    issuer_url: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    domains: list[str] = Field(default_factory=list)
    is_enforced: bool = False
    metadata_xml: Optional[str] = None
    is_active: bool = True


class SsoConnectionOut(ORMModel):
    id: UUID
    workspace_id: UUID
    provider: str
    issuer_url: Optional[str] = None
    client_id: Optional[str] = None
    domains: list[str]
    is_enforced: bool
    is_active: bool
    metadata_xml: Optional[str] = None


class DataRetentionPolicyUpsert(BaseModel):
    resource_type: str
    retain_days: int = Field(ge=1, le=3650)
    hard_delete: bool = True
    notes: Optional[str] = None


class DataRetentionPolicyOut(ORMModel):
    id: UUID
    workspace_id: UUID
    resource_type: str
    retain_days: int
    hard_delete: bool
    is_active: bool


class ExportJobCreate(BaseModel):
    job_type: ExportJobType = ExportJobType.GDPR_USER_EXPORT
    workspace_id: Optional[UUID] = None


class ExportJobOut(ORMModel):
    id: UUID
    job_type: ExportJobType
    status: ExportJobStatus
    download_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class SharedLinkCreate(BaseModel):
    resource_type: SharedLinkResourceType
    resource_id: UUID
    expires_at: Optional[datetime] = None
    password: Optional[str] = None
    allow_download: bool = False


class SharedLinkOut(ORMModel):
    id: UUID
    workspace_id: UUID
    resource_type: SharedLinkResourceType
    resource_id: UUID
    expires_at: Optional[datetime] = None
    view_count: int
    allow_download: bool
    created_at: datetime
    # plaintext token only on create
    token: Optional[str] = None
