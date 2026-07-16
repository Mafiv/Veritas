"""005 billing — plans, subscriptions, usage_meters, invoices (+ seed plans)

Revision ID: 005_billing
Revises: 004_chat
Create Date: 2026-07-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_billing"
down_revision: Union[str, Sequence[str], None] = "004_chat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

subscription_status = postgresql.ENUM(
    "trialing",
    "active",
    "past_due",
    "canceled",
    "incomplete",
    "unpaid",
    name="subscription_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    subscription_status.create(bind, checkfirst=True)

    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "code",
            postgresql.ENUM(
                "free", "pro", "team", "enterprise", name="plan_tier", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price_cents_monthly", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="usd"),
        sa.Column("stripe_price_id", sa.String(120), nullable=True),
        sa.Column("queries_per_day", sa.Integer(), nullable=False),
        sa.Column("documents_limit", sa.Integer(), nullable=False),
        sa.Column("workspaces_limit", sa.Integer(), nullable=False),
        sa.Column("storage_bytes_limit", sa.BigInteger(), nullable=False),
        sa.Column("seats_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stripe_customer_id", sa.String(120), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(120), nullable=True),
        sa.Column("status", subscription_status, nullable=False, server_default="active"),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_plan_id", "subscriptions", ["plan_id"])
    op.create_index("ix_subscriptions_workspace_id", "subscriptions", ["workspace_id"])
    op.create_index("ix_subscriptions_user_status", "subscriptions", ["user_id", "status"])
    op.create_index("ix_subscriptions_stripe_sub", "subscriptions", ["stripe_subscription_id"])

    op.create_table(
        "usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_usage_events_user_id", "usage_events", ["user_id"])
    op.create_index("ix_usage_events_workspace_id", "usage_events", ["workspace_id"])
    op.create_index(
        "ix_usage_events_workspace_created", "usage_events", ["workspace_id", "created_at"]
    )
    op.create_index(
        "ix_usage_events_user_type_created",
        "usage_events",
        ["user_id", "event_type", "created_at"],
    )

    # Deliberate denormalization of usage_events for O(1) quota checks
    op.create_table(
        "usage_meters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("meter_key", sa.String(50), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "workspace_id", "meter_key", "period_start", name="uq_usage_meter_period"
        ),
    )
    op.create_index("ix_usage_meters_workspace_id", "usage_meters", ["workspace_id"])
    op.create_index("ix_usage_meters_user_id", "usage_meters", ["user_id"])
    op.create_index(
        "ix_usage_meters_workspace_period", "usage_meters", ["workspace_id", "period_start"]
    )

    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stripe_invoice_id", sa.String(120), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("amount_due_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount_paid_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="usd"),
        sa.Column("hosted_invoice_url", sa.String(1000), nullable=True),
        sa.Column("invoice_pdf_url", sa.String(1000), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("stripe_invoice_id"),
    )
    op.create_index("ix_invoices_user_id", "invoices", ["user_id"])
    op.create_index("ix_invoices_subscription_id", "invoices", ["subscription_id"])

    # Seed plan catalog (quotas as data)
    op.execute(
        sa.text(
            """
            INSERT INTO plans (
              id, code, name, description, price_cents_monthly, queries_per_day,
              documents_limit, workspaces_limit, storage_bytes_limit, seats_limit,
              features, sort_order
            ) VALUES
            (gen_random_uuid(), 'free', 'Free', 'Explore grounded Q&A', 0, 20, 5, 1,
             10737418240, 1, '{"rerank": false, "hyde": true}'::jsonb, 0),
            (gen_random_uuid(), 'pro', 'Pro', 'Higher limits + premium retrieval', 2900, 500, 200, 10,
             26843545600, 5, '{"rerank": true, "hyde": true, "api_keys": true}'::jsonb, 1),
            (gen_random_uuid(), 'team', 'Team', 'Collaboration + admin', 9900, 5000, 2000, 100,
             107374182400, 50, '{"rerank": true, "shared_threads": true, "sso": false}'::jsonb, 2),
            (gen_random_uuid(), 'enterprise', 'Enterprise', 'SSO, retention, webhooks, CMK', 0, 50000, 50000, 1000,
             1099511627776, 500, '{"sso": true, "webhooks": true, "retention": true, "cmk": true}'::jsonb, 3)
            """
        )
    )


def downgrade() -> None:
    op.drop_table("invoices")
    op.drop_table("usage_meters")
    op.drop_table("usage_events")
    op.drop_table("subscriptions")
    op.drop_table("plans")
    subscription_status.drop(op.get_bind(), checkfirst=True)
