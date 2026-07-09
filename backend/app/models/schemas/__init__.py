"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.domain import DocumentStatus, DocumentType, PlanTier, WorkspaceRole


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Auth ──────────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(ORMModel):
    id: UUID
    email: EmailStr
    full_name: str
    plan: PlanTier
    is_active: bool
    created_at: datetime
    queries_today: int = 0


# ── Workspaces ────────────────────────────────────────────────────────────────


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None


class WorkspaceOut(ORMModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str]
    owner_id: UUID
    created_at: datetime
    member_count: int = 0
    document_count: int = 0


class MemberInvite(BaseModel):
    email: EmailStr
    role: WorkspaceRole = WorkspaceRole.VIEWER


class MemberOut(ORMModel):
    id: UUID
    user_id: UUID
    email: EmailStr
    full_name: str
    role: WorkspaceRole


# ── Documents ─────────────────────────────────────────────────────────────────


class DocumentOut(ORMModel):
    id: UUID
    workspace_id: UUID
    filename: str
    original_filename: str
    content_type: str
    doc_type: DocumentType
    status: DocumentStatus
    file_size: int
    page_count: int
    chunk_count: int
    version: int
    summary: Optional[str]
    suggested_questions: Optional[list[str]]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentOut]
    total: int


# ── Chat ──────────────────────────────────────────────────────────────────────


class Citation(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_name: str
    page_number: Optional[int] = None
    heading: Optional[str] = None
    snippet: str
    score: float
    citation_index: int


class ThreadCreate(BaseModel):
    title: Optional[str] = "New conversation"


class ThreadOut(ORMModel):
    id: UUID
    workspace_id: UUID
    title: str
    is_shared: bool
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class MessageOut(ORMModel):
    id: UUID
    thread_id: UUID
    role: str
    content: str
    citations: Optional[list[Citation]] = None
    feedback: Optional[str] = None
    created_at: datetime


class ChatQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    thread_id: Optional[UUID] = None
    document_ids: Optional[list[UUID]] = None
    collection_id: Optional[UUID] = None
    use_hyde: bool = True
    use_rerank: bool = True


class ChatQueryResponse(BaseModel):
    thread_id: UUID
    message: MessageOut
    citations: list[Citation]


class FeedbackRequest(BaseModel):
    feedback: str = Field(pattern="^(up|down)$")


# ── Billing ───────────────────────────────────────────────────────────────────


class CheckoutRequest(BaseModel):
    plan: PlanTier


class UsageStats(BaseModel):
    plan: PlanTier
    queries_today: int
    queries_limit: int
    documents_count: int
    documents_limit: int
    workspaces_count: int
    workspaces_limit: int
    chunks_total: int


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str


class ErrorResponse(BaseModel):
    error: dict[str, Any]


# Re-export extended schemas for convenience
from app.models.schemas.extended import *  # noqa: E402, F401, F403
