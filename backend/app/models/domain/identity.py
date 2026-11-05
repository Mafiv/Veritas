"""Identity & access domain models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

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
    Base,
    InvitationStatus,
    JSONType,
    PlanTier,
    SoftDeleteMixin,
    TimestampMixin,
    UUID,
    WorkspaceRole,
    new_uuid,
)

if TYPE_CHECKING:
    from app.models.domain.billing import Subscription
    from app.models.domain.chat import ChatThread
    from app.models.domain.documents import Document


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Nullable for Better Auth / OAuth users (password lives in Better Auth account table)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default="")
    auth_user_id: Mapped[Optional[str]] = mapped_column(
        String(128), unique=True, index=True, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Legacy billing fields — source of truth moves to subscriptions/usage_meters.
    # Kept additive for backward compatibility until a breaking cleanup migration.
    plan: Mapped[PlanTier] = mapped_column(Enum(PlanTier, name="plan_tier"), default=PlanTier.FREE)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    queries_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    queries_reset_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    avatar_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    memberships: Mapped[list[WorkspaceMember]] = relationship(back_populates="user")
    owned_workspaces: Mapped[list[Workspace]] = relationship(back_populates="owner")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="user")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")


class Workspace(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    owner: Mapped[User] = relationship(back_populates="owned_workspaces")
    members: Mapped[list[WorkspaceMember]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(back_populates="workspace")
    threads: Mapped[list["ChatThread"]] = relationship(back_populates="workspace")
    invitations: Mapped[list[Invitation]] = relationship(back_populates="workspace")
    api_keys: Mapped[list[ApiKey]] = relationship(back_populates="workspace")


class WorkspaceMember(Base, TimestampMixin):
    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_user"),
        Index("ix_workspace_members_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[WorkspaceRole] = mapped_column(
        Enum(WorkspaceRole, name="workspace_role"), default=WorkspaceRole.VIEWER, nullable=False
    )

    workspace: Mapped[Workspace] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class Invitation(Base, TimestampMixin, SoftDeleteMixin):
    """Pending workspace invites by email with expiring tokens."""

    __tablename__ = "invitations"
    __table_args__ = (
        Index("ix_invitations_workspace_status", "workspace_id", "status"),
        Index("ix_invitations_email", "email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[WorkspaceRole] = mapped_column(
        Enum(WorkspaceRole, name="workspace_role", create_constraint=False),
        default=WorkspaceRole.VIEWER,
        nullable=False,
    )
    invited_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus, name="invitation_status"),
        default=InvitationStatus.PENDING,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    workspace: Mapped[Workspace] = relationship(back_populates="invitations")


class RefreshToken(Base, TimestampMixin):
    """Hashed refresh tokens with rotation / reuse detection."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True
    )
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class ApiKey(Base, TimestampMixin, SoftDeleteMixin):
    """Workspace-scoped programmatic access keys (store hash only)."""

    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_workspace_id", "workspace_id"),
        Index("ix_api_keys_prefix", "key_prefix"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    scopes: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace: Mapped[Workspace] = relationship(back_populates="api_keys")
