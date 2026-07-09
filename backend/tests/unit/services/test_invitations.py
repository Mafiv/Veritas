"""Unit tests for invitation token hashing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import ForbiddenError, VeritasError
from app.models.domain import InvitationStatus, WorkspaceRole
from app.services.identity import invitations as invitation_service


def _result(scalar=None, rows=None):
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    r.scalar_one.return_value = scalar
    r.scalars.return_value.all.return_value = rows or []
    return r


@pytest.mark.asyncio
async def test_create_invitation_hashes_token():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    async def execute(stmt):
        if not hasattr(execute, "n"):
            execute.n = 0
        execute.n += 1
        if execute.n == 1:
            return _result(scalar=None)  # no existing user
        if execute.n == 2:
            return _result(rows=[])  # prior invites
        ws = MagicMock()
        ws.name = "Personal"
        return _result(scalar=ws)

    db.execute = execute

    with patch("app.services.identity.invitations.get_email_sender") as ge:
        sender = AsyncMock()
        ge.return_value = sender
        inv, raw = await invitation_service.create_invitation(
            db,
            workspace_id=uuid4(),
            email="new@example.com",
            role=WorkspaceRole.VIEWER,
            invited_by=uuid4(),
        )
    assert raw
    assert inv.token_hash != raw
    assert inv.email == "new@example.com"
    assert sender.send.await_count == 1


@pytest.mark.asyncio
async def test_accept_invitation_email_mismatch():
    inv = MagicMock()
    inv.status = InvitationStatus.PENDING
    inv.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    inv.email = "other@example.com"
    inv.workspace_id = uuid4()
    inv.role = WorkspaceRole.VIEWER
    inv.id = uuid4()

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result(scalar=inv))
    db.flush = AsyncMock()

    user = MagicMock()
    user.email = "me@example.com"
    user.id = uuid4()

    with pytest.raises(ForbiddenError):
        await invitation_service.accept_invitation(db, raw_token="abc", user=user)
