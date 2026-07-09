"""Unit tests for SSO helpers and notification preferences."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.domain import NotificationChannel, SsoProvider
from app.services.identity import sso as sso_service
from app.services.notifications import service as notif_service


def _result(scalar=None, rows=None):
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    r.scalars.return_value.all.return_value = rows or []
    r.all.return_value = rows or []
    return r


@pytest.mark.asyncio
async def test_upsert_sso_encrypts_secret():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(return_value=_result(scalar=None))
    row = await sso_service.upsert_sso(
        db,
        workspace_id=uuid4(),
        provider="oidc",
        issuer_url="https://idp.example",
        client_id="cid",
        client_secret="super-secret",
        domains=["Acme.COM"],
        is_enforced=True,
    )
    assert row.provider == SsoProvider.OIDC
    assert row.domains == ["acme.com"]
    assert row.client_secret_encrypted
    assert not row.client_secret_encrypted.startswith("super-secret")
    assert row.is_enforced is True


@pytest.mark.asyncio
async def test_create_sso_state_and_pop():
    state = sso_service.create_sso_state(
        connection_id=uuid4(),
        workspace_id=uuid4(),
        provider="oidc",
        email="a@example.com",
    )
    data = sso_service.pop_sso_state(state)
    assert data["provider"] == "oidc"
    assert data["email"] == "a@example.com"


@pytest.mark.asyncio
async def test_upsert_notification_preference():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(return_value=_result(scalar=None))
    row = await notif_service.upsert_preference(
        db,
        user_id=uuid4(),
        event_type="document.ready",
        channel="email",
        enabled=False,
    )
    assert row.enabled is False
    assert row.channel == NotificationChannel.EMAIL
