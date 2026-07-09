"""Stripe payment client and webhook helpers."""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.models.domain import PlanTier


class StripeClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.stripe_secret_key)

    def create_checkout_session(
        self,
        *,
        customer_email: str,
        customer_id: str | None,
        plan: PlanTier,
        success_url: str,
        cancel_url: str,
        client_reference_id: str,
    ) -> dict[str, Any]:
        if not self.enabled:
            # Dev mock checkout
            return {
                "id": "cs_test_mock",
                "url": f"{self.settings.frontend_url}/settings?checkout=mock&plan={plan.value}",
                "mock": True,
            }

        import stripe

        stripe.api_key = self.settings.stripe_secret_key
        price = (
            self.settings.stripe_price_pro
            if plan == PlanTier.PRO
            else self.settings.stripe_price_team
        )
        params: dict[str, Any] = {
            "mode": "subscription",
            "line_items": [{"price": price, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": client_reference_id,
            "customer_email": customer_email if not customer_id else None,
            "customer": customer_id,
        }
        # Remove Nones
        params = {k: v for k, v in params.items() if v is not None}
        session = stripe.checkout.Session.create(**params)
        return {"id": session.id, "url": session.url, "mock": False}

    def construct_event(self, payload: bytes, sig_header: str) -> Any:
        import stripe

        stripe.api_key = self.settings.stripe_secret_key
        return stripe.Webhook.construct_event(
            payload, sig_header, self.settings.stripe_webhook_secret
        )


def plan_limits(plan: PlanTier) -> dict[str, int]:
    settings = get_settings()
    if plan == PlanTier.PRO:
        return {
            "queries_per_day": 500,
            "documents": 200,
            "workspaces": 10,
        }
    if plan == PlanTier.TEAM:
        return {
            "queries_per_day": 5000,
            "documents": 2000,
            "workspaces": 100,
        }
    return {
        "queries_per_day": settings.free_tier_queries_per_day,
        "documents": settings.free_tier_documents,
        "workspaces": settings.free_tier_workspaces,
    }
