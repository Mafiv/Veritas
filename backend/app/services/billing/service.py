"""Billing plans, subscriptions, usage meters, and invoices."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, QuotaExceededError
from app.models.domain import (
    Invoice,
    Plan,
    PlanTier,
    Subscription,
    SubscriptionStatus,
    UsageEvent,
    UsageMeter,
    User,
)
from app.services.payment.stripe_client import plan_limits as hardcoded_limits


async def ensure_default_plans(db: AsyncSession) -> list[Plan]:
    """Seed free/pro/team plan rows if missing."""
    existing = list((await db.execute(select(Plan))).scalars().all())
    by_code = {p.code: p for p in existing}
    defaults = [
        {
            "code": PlanTier.FREE,
            "name": "Free",
            "description": "Get started with grounded answers",
            "price_cents_monthly": 0,
            "queries_per_day": 20,
            "documents_limit": 10,
            "workspaces_limit": 1,
            "storage_bytes_limit": 100_000_000,
            "seats_limit": 1,
            "sort_order": 0,
        },
        {
            "code": PlanTier.PRO,
            "name": "Pro",
            "description": "For individual researchers",
            "price_cents_monthly": 2900,
            "queries_per_day": 500,
            "documents_limit": 200,
            "workspaces_limit": 10,
            "storage_bytes_limit": 5_000_000_000,
            "seats_limit": 1,
            "sort_order": 1,
        },
        {
            "code": PlanTier.TEAM,
            "name": "Team",
            "description": "Shared workspaces and higher limits",
            "price_cents_monthly": 9900,
            "queries_per_day": 5000,
            "documents_limit": 2000,
            "workspaces_limit": 100,
            "storage_bytes_limit": 50_000_000_000,
            "seats_limit": 20,
            "sort_order": 2,
        },
    ]
    out: list[Plan] = []
    for d in defaults:
        if d["code"] in by_code:
            out.append(by_code[d["code"]])
            continue
        plan = Plan(**d, is_active=True)
        db.add(plan)
        out.append(plan)
    await db.flush()
    return out


async def get_plan_by_code(db: AsyncSession, code: PlanTier) -> Plan:
    await ensure_default_plans(db)
    plan = (
        await db.execute(select(Plan).where(Plan.code == code, Plan.is_active.is_(True)))
    ).scalar_one_or_none()
    if not plan:
        raise NotFoundError(f"Plan {code} not found")
    return plan


async def plan_limits_from_db(db: AsyncSession, plan_tier: PlanTier) -> dict[str, int]:
    try:
        plan = await get_plan_by_code(db, plan_tier)
        return {
            "queries_per_day": plan.queries_per_day,
            "documents": plan.documents_limit,
            "workspaces": plan.workspaces_limit,
        }
    except Exception:
        return hardcoded_limits(plan_tier)


def _day_period(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


async def record_usage(
    db: AsyncSession,
    *,
    user_id: UUID,
    workspace_id: UUID | None,
    event_type: str,
    quantity: int = 1,
    meta: dict | None = None,
    meter_key: str | None = None,
) -> UsageEvent:
    event = UsageEvent(
        user_id=user_id,
        workspace_id=workspace_id,
        event_type=event_type,
        quantity=quantity,
        meta=meta,
    )
    db.add(event)
    if workspace_id and meter_key:
        await bump_meter(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            meter_key=meter_key,
            quantity=quantity,
        )
    await db.flush()
    return event


async def bump_meter(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID | None,
    meter_key: str,
    quantity: int = 1,
) -> UsageMeter:
    start, end = _day_period()
    meter = (
        await db.execute(
            select(UsageMeter).where(
                UsageMeter.workspace_id == workspace_id,
                UsageMeter.meter_key == meter_key,
                UsageMeter.period_start == start,
            )
        )
    ).scalar_one_or_none()
    if meter:
        meter.quantity = (meter.quantity or 0) + quantity
        await db.flush()
        return meter
    meter = UsageMeter(
        workspace_id=workspace_id,
        user_id=user_id,
        meter_key=meter_key,
        period_start=start,
        period_end=end,
        quantity=quantity,
    )
    db.add(meter)
    await db.flush()
    return meter


async def get_meter_quantity(
    db: AsyncSession, *, workspace_id: UUID, meter_key: str
) -> int:
    start, _ = _day_period()
    meter = (
        await db.execute(
            select(UsageMeter).where(
                UsageMeter.workspace_id == workspace_id,
                UsageMeter.meter_key == meter_key,
                UsageMeter.period_start == start,
            )
        )
    ).scalar_one_or_none()
    return int(meter.quantity) if meter else 0


async def check_query_quota_metered(
    db: AsyncSession, *, user: User, workspace_id: UUID
) -> None:
    limits = await plan_limits_from_db(db, user.plan)
    # Keep legacy counter in sync for UsageStats
    now = datetime.now(timezone.utc)
    if user.queries_reset_at is None or user.queries_reset_at.date() < now.date():
        user.queries_today = 0
        user.queries_reset_at = now
        await db.flush()
    used = await get_meter_quantity(db, workspace_id=workspace_id, meter_key="query")
    # Prefer meter; fall back to user.queries_today
    effective = max(used, user.queries_today or 0)
    if effective >= limits["queries_per_day"]:
        raise QuotaExceededError(
            f"Daily query limit reached ({limits['queries_per_day']}). Upgrade your plan."
        )


async def upsert_subscription(
    db: AsyncSession,
    *,
    user: User,
    plan_code: PlanTier,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
) -> Subscription:
    plan = await get_plan_by_code(db, plan_code)
    sub = (
        await db.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if sub:
        sub.plan_id = plan.id
        sub.status = status
        if stripe_customer_id:
            sub.stripe_customer_id = stripe_customer_id
        if stripe_subscription_id:
            sub.stripe_subscription_id = stripe_subscription_id
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=30)
    else:
        sub = Subscription(
            user_id=user.id,
            plan_id=plan.id,
            status=status,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db.add(sub)
    user.plan = plan_code
    if stripe_customer_id:
        user.stripe_customer_id = stripe_customer_id
    if stripe_subscription_id:
        user.stripe_subscription_id = stripe_subscription_id
    await db.flush()
    return sub


async def record_invoice(
    db: AsyncSession,
    *,
    user_id: UUID,
    subscription_id: UUID | None,
    stripe_invoice_id: str,
    status: str,
    amount_due_cents: int = 0,
    amount_paid_cents: int = 0,
    currency: str = "usd",
    hosted_invoice_url: str | None = None,
    paid_at: datetime | None = None,
) -> Invoice:
    existing = (
        await db.execute(
            select(Invoice).where(Invoice.stripe_invoice_id == stripe_invoice_id)
        )
    ).scalar_one_or_none()
    if existing:
        existing.status = status
        existing.amount_due_cents = amount_due_cents
        existing.amount_paid_cents = amount_paid_cents
        existing.hosted_invoice_url = hosted_invoice_url
        existing.paid_at = paid_at
        await db.flush()
        return existing
    inv = Invoice(
        user_id=user_id,
        subscription_id=subscription_id,
        stripe_invoice_id=stripe_invoice_id,
        status=status,
        amount_due_cents=amount_due_cents,
        amount_paid_cents=amount_paid_cents,
        currency=currency,
        hosted_invoice_url=hosted_invoice_url,
        paid_at=paid_at,
    )
    db.add(inv)
    await db.flush()
    return inv


async def list_plans(db: AsyncSession) -> list[Plan]:
    await ensure_default_plans(db)
    return list(
        (
            await db.execute(
                select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.sort_order)
            )
        )
        .scalars()
        .all()
    )


async def list_invoices(db: AsyncSession, user_id: UUID) -> list[Invoice]:
    return list(
        (
            await db.execute(
                select(Invoice)
                .where(Invoice.user_id == user_id)
                .order_by(Invoice.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
