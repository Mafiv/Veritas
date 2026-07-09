"""Billing, plans, subscriptions, usage metering, and invoices."""

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
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.domain.base import (
    Base,
    JSONType,
    PlanTier,
    SubscriptionStatus,
    TimestampMixin,
    UsageEventType,
    UUID,
    new_uuid,
)

if TYPE_CHECKING:
    from app.models.domain.identity import User, Workspace


class Plan(Base, TimestampMixin):
    """Plan definitions as data — quotas not hardcoded in application logic."""

    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    code: Mapped[PlanTier] = mapped_column(
        Enum(PlanTier, name="plan_tier", create_constraint=False),
        unique=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price_cents_monthly: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="usd", nullable=False)
    stripe_price_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    queries_per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    documents_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    workspaces_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_bytes_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    seats_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    features: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="plan")


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_user_status", "user_id", "status"),
        Index("ix_subscriptions_stripe_sub", "stripe_subscription_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status"),
        default=SubscriptionStatus.ACTIVE,
        nullable=False,
    )
    current_period_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)

    user: Mapped["User"] = relationship(back_populates="subscriptions")
    plan: Mapped[Plan] = relationship(back_populates="subscriptions")
    invoices: Mapped[list[Invoice]] = relationship(back_populates="subscription")


class UsageEvent(Base, TimestampMixin):
    """Append-only usage ledger. usage_meters deliberately denormalizes this."""

    __tablename__ = "usage_events"
    __table_args__ = (
        Index("ix_usage_events_workspace_created", "workspace_id", "created_at"),
        Index("ix_usage_events_user_type_created", "user_id", "event_type", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Keep String for backward compat with existing free-text event_type writes;
    # new code should use UsageEventType values.
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    meta: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)


class UsageMeter(Base, TimestampMixin):
    """
    Deliberate denormalization of usage_events.

    Rolled-up current-period counters per workspace for O(1) quota checks
    without scanning the append-only ledger on every request.
    """

    __tablename__ = "usage_meters"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "meter_key", "period_start", name="uq_usage_meter_period"
        ),
        Index("ix_usage_meters_workspace_period", "workspace_id", "period_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    meter_key: Mapped[str] = mapped_column(String(50), nullable=False)  # query|token|chunk|upload
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Invoice(Base, TimestampMixin):
    """Local Stripe invoice history for billing UI / disputes."""

    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_subscription_id", "subscription_id"),
        Index("ix_invoices_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    stripe_invoice_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    amount_due_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    amount_paid_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="usd", nullable=False)
    hosted_invoice_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    invoice_pdf_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)

    subscription: Mapped[Optional[Subscription]] = relationship(back_populates="invoices")
