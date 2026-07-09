"""Billing endpoints — Stripe checkout, portal, webhooks, usage, plans, invoices."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Header, Request
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.exceptions import VeritasError
from app.models.domain import Document, DocumentChunk, PlanTier, SubscriptionStatus, Workspace
from app.models.schemas import CheckoutRequest, UsageStats
from app.models.schemas.extended import InvoiceOut, PlanOut, SubscriptionOut
from app.services.billing import service as billing_service
from app.services.payment.stripe_client import StripeClient

router = APIRouter(prefix="/billing", tags=["billing"])
stripe_client = StripeClient()


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(db: DbSession) -> list[PlanOut]:
    plans = await billing_service.list_plans(db)
    return [PlanOut.model_validate(p) for p in plans]


@router.get("/usage", response_model=UsageStats)
async def usage_stats(db: DbSession, user: CurrentUser) -> UsageStats:
    limits = await billing_service.plan_limits_from_db(db, user.plan)
    docs = (
        await db.execute(
            select(func.count())
            .select_from(Document)
            .join(Workspace, Workspace.id == Document.workspace_id)
            .where(Workspace.owner_id == user.id, Document.deleted_at.is_(None))
        )
    ).scalar_one()
    workspaces = (
        await db.execute(
            select(func.count()).select_from(Workspace).where(Workspace.owner_id == user.id)
        )
    ).scalar_one()
    chunks = (
        await db.execute(
            select(func.count())
            .select_from(DocumentChunk)
            .join(Workspace, Workspace.id == DocumentChunk.workspace_id)
            .where(Workspace.owner_id == user.id)
        )
    ).scalar_one()
    return UsageStats(
        plan=user.plan,
        queries_today=user.queries_today or 0,
        queries_limit=limits["queries_per_day"],
        documents_count=docs,
        documents_limit=limits["documents"],
        workspaces_count=workspaces,
        workspaces_limit=limits["workspaces"],
        chunks_total=chunks,
    )


@router.get("/invoices", response_model=list[InvoiceOut])
async def list_invoices(db: DbSession, user: CurrentUser) -> list[InvoiceOut]:
    rows = await billing_service.list_invoices(db, user.id)
    return [InvoiceOut.model_validate(r) for r in rows]


@router.get("/subscription", response_model=SubscriptionOut | None)
async def get_subscription(db: DbSession, user: CurrentUser) -> SubscriptionOut | None:
    from app.models.domain import Subscription

    sub = (
        await db.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not sub:
        return None
    return SubscriptionOut.model_validate(sub)


@router.post("/checkout")
async def create_checkout(body: CheckoutRequest, db: DbSession, user: CurrentUser) -> dict:
    if body.plan == PlanTier.FREE:
        raise VeritasError("Cannot checkout for free plan", code="invalid_plan")
    settings = get_settings()
    session = stripe_client.create_checkout_session(
        customer_email=user.email,
        customer_id=user.stripe_customer_id,
        plan=body.plan,
        success_url=f"{settings.frontend_url}/settings?checkout=success",
        cancel_url=f"{settings.frontend_url}/settings?checkout=cancel",
        client_reference_id=str(user.id),
    )
    if session.get("mock"):
        await billing_service.upsert_subscription(
            db,
            user=user,
            plan_code=body.plan,
            status=SubscriptionStatus.ACTIVE,
        )
    return session


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: DbSession,
    stripe_signature: str | None = Header(default=None, alias="stripe-signature"),
) -> dict:
    payload = await request.body()
    settings = get_settings()

    if not settings.stripe_secret_key:
        return {"received": True, "mock": True}

    if not stripe_signature:
        raise VeritasError("Missing stripe-signature", status_code=400)

    try:
        event = stripe_client.construct_event(payload, stripe_signature)
    except Exception as exc:  # noqa: BLE001
        raise VeritasError(f"Webhook error: {exc}", status_code=400) from exc

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("client_reference_id")
        if user_id:
            from uuid import UUID

            from app.models.domain import User

            result = await db.execute(select(User).where(User.id == UUID(user_id)))
            user = result.scalar_one_or_none()
            if user:
                plan = PlanTier.PRO
                meta = session.get("metadata") or {}
                if meta.get("plan") == "team":
                    plan = PlanTier.TEAM
                sub = await billing_service.upsert_subscription(
                    db,
                    user=user,
                    plan_code=plan,
                    stripe_customer_id=session.get("customer"),
                    stripe_subscription_id=session.get("subscription"),
                    status=SubscriptionStatus.ACTIVE,
                )
                if session.get("invoice"):
                    await billing_service.record_invoice(
                        db,
                        user_id=user.id,
                        subscription_id=sub.id,
                        stripe_invoice_id=str(session.get("invoice")),
                        status="paid",
                        paid_at=datetime.now(timezone.utc),
                    )

    elif event["type"] == "invoice.paid":
        inv = event["data"]["object"]
        from uuid import UUID

        from app.models.domain import Subscription, User

        customer = inv.get("customer")
        user = None
        if customer:
            user = (
                await db.execute(select(User).where(User.stripe_customer_id == customer))
            ).scalar_one_or_none()
        if user:
            sub = (
                await db.execute(
                    select(Subscription)
                    .where(Subscription.user_id == user.id)
                    .order_by(Subscription.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            await billing_service.record_invoice(
                db,
                user_id=user.id,
                subscription_id=sub.id if sub else None,
                stripe_invoice_id=inv.get("id") or f"inv_{user.id}",
                status=inv.get("status") or "paid",
                amount_due_cents=int(inv.get("amount_due") or 0),
                amount_paid_cents=int(inv.get("amount_paid") or 0),
                currency=inv.get("currency") or "usd",
                hosted_invoice_url=inv.get("hosted_invoice_url"),
                paid_at=datetime.now(timezone.utc),
            )

    elif event["type"] == "customer.subscription.deleted":
        sub_obj = event["data"]["object"]
        from app.models.domain import User

        result = await db.execute(
            select(User).where(User.stripe_subscription_id == sub_obj.get("id"))
        )
        user = result.scalar_one_or_none()
        if user:
            await billing_service.upsert_subscription(
                db,
                user=user,
                plan_code=PlanTier.FREE,
                status=SubscriptionStatus.CANCELED,
            )
            user.stripe_subscription_id = None
            await db.flush()

    return {"received": True}
