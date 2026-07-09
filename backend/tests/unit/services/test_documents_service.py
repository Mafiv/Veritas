"""Unit tests for document collection helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.documents import service as doc_service


@pytest.mark.asyncio
async def test_create_collection():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    col = await doc_service.create_collection(
        db,
        workspace_id=uuid4(),
        created_by=uuid4(),
        name="Research",
        description="notes",
        document_ids=[uuid4(), uuid4()],
    )
    assert col.name == "Research"
    # collection + 2 memberships
    assert db.add.call_count == 3


@pytest.mark.asyncio
async def test_grant_permission():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    row = await doc_service.grant_permission(
        db,
        document_id=uuid4(),
        user_id=uuid4(),
        granted_by=uuid4(),
        scope="document",
    )
    assert row.can_read is True
    db.add.assert_called_once()
