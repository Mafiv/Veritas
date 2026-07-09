"""Unit tests for enterprise webhook signing / retry helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.domain import SharedLinkResourceType, WebhookDeliveryStatus
from app.services.enterprise import service as enterprise_service


@pytest.mark.asyncio
async def test_create_webhook_returns_secret():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    ep, secret = await enterprise_service.create_webhook(
        db,
        workspace_id=uuid4(),
        created_by=uuid4(),
        url="https://example.com/hook",
        event_types=["document.ready"],
    )
    assert secret
    assert ep.url == "https://example.com/hook"
    # secret is encrypted at rest
    assert ep.secret_hash != secret
    recovered = enterprise_service.webhook_signing_secret(ep)
    assert recovered == secret
    sig = enterprise_service.sign_payload(secret, b'{"ok":true}')
    assert len(sig) == 64


@pytest.mark.asyncio
async def test_schedule_retry_marks_failed_after_max():
    from app.core.config import get_settings

    d = MagicMock()
    d.attempt_count = get_settings().webhook_max_attempts
    d.status = WebhookDeliveryStatus.PENDING
    d.next_retry_at = None
    enterprise_service.schedule_retry(d)
    assert d.status == WebhookDeliveryStatus.FAILED


@pytest.mark.asyncio
async def test_create_shared_link():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    link, raw = await enterprise_service.create_shared_link(
        db,
        workspace_id=uuid4(),
        created_by=uuid4(),
        resource_type=SharedLinkResourceType.DOCUMENT,
        resource_id=uuid4(),
    )
    assert raw
    assert link.token_hash
