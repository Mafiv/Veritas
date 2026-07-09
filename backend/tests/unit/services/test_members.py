"""Unit tests for identity member service (mocked session patterns)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.domain import WorkspaceRole
from app.services.identity import members as member_service


def _result(scalar=None, rows=None, count=None):
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    r.scalar_one.return_value = count if count is not None else 0
    r.all.return_value = rows or []
    r.scalars.return_value.all.return_value = rows or []
    r.scalars.return_value.first.return_value = scalar
    return r


@pytest.mark.asyncio
async def test_add_existing_member_not_found():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result(scalar=None))
    with pytest.raises(NotFoundError):
        await member_service.add_existing_member(
            db,
            workspace_id=uuid4(),
            email="missing@example.com",
            role=WorkspaceRole.VIEWER,
            actor_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_add_existing_member_conflict():
    user = MagicMock()
    user.id = uuid4()
    user.email = "a@example.com"
    existing_mem = MagicMock()

    async def execute(stmt):
        # first call: find user; second: get_membership
        if not hasattr(execute, "n"):
            execute.n = 0
        execute.n += 1
        if execute.n == 1:
            return _result(scalar=user)
        return _result(scalar=existing_mem)

    db = AsyncMock()
    db.execute = execute
    db.add = MagicMock()
    db.flush = AsyncMock()
    with pytest.raises(ConflictError):
        await member_service.add_existing_member(
            db,
            workspace_id=uuid4(),
            email="a@example.com",
            role=WorkspaceRole.VIEWER,
            actor_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_cannot_demote_last_owner():
    member = MagicMock()
    member.role = WorkspaceRole.OWNER
    member.id = uuid4()

    async def execute(stmt):
        if not hasattr(execute, "n"):
            execute.n = 0
        execute.n += 1
        if execute.n == 1:
            return _result(scalar=member)
        return _result(count=1)

    db = AsyncMock()
    db.execute = execute
    db.flush = AsyncMock()
    with pytest.raises(ForbiddenError):
        await member_service.change_role(
            db,
            workspace_id=uuid4(),
            target_user_id=uuid4(),
            new_role=WorkspaceRole.EDITOR,
            actor_id=uuid4(),
        )
