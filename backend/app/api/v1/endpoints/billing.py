"""Billing endpoints — Stripe checkout, portal, webhooks, usage."""

from __future__ import annotations

from fastapi import APIRouter, Header, Request
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.exceptions import VeritasError
from app.models.domain import Document, DocumentChunk, PlanTier, UsageEvent, Workspace
from app.models.schemas import CheckoutRequest, UsageStats
from app.services.payment.stripe_client import StripeClient, plan_limits

router = APIRouter(prefix="/billing", tags=["billing"])
stripe_client = StripeClient()


@router.get("/usage", response_model=UsageStats)
async def usage_stats(db: DbSession, user: CurrentUser) -> UsageStats:
    limits = plan_limits(user.plan)
    docs = (
        await db.execute(
            select(func.count())
            .select_from(Document)
            .join(Workspace, Workspace.id == Document.workspace_id)
            .where(Workspace.owner_id == user.id)
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
    # Mock upgrade path for local development
    if session.get("mock"):
        user.plan = body.plan
        await db.flush()
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
        # Accept mock events in development
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
                user.stripe_customer_id = session.get("customer")
                user.stripe_subscription_id = session.get("subscription")
                # Default to pro unless metadata says otherwise
                user.plan = PlanTier.PRO
                await db.flush()

    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        from app.models.domain import User

        result = await db.execute(
            select(User).where(User.stripe_subscription_id == sub.get("id"))
        )
        user = result.scalar_one_or_none()
        if user:
            user.plan = PlanTier.FREE
            user.stripe_subscription_id = None
            await db.flush()

    return {"received": True}
