"""Unit tests for notifications and shared links."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.domain import SharedLinkResourceType
from app.services.enterprise import service as enterprise_service
from app.services.notifications import service as notif_service


@pytest.mark.asyncio
async def test_notify_user():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    row = await notif_service.notify_user(
        db,
        user_id=uuid4(),
        workspace_id=uuid4(),
        type="document.ready",
        title="Ready",
        body="done",
        link_url="/documents",
    )
    assert row.type == "document.ready"
    assert row.title == "Ready"
    db.add.assert_called_once()


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
    assert link.resource_type == SharedLinkResourceType.DOCUMENT
    db.add.assert_called_once()
