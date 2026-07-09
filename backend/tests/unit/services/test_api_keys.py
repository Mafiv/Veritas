"""Unit tests for API key hashing / validation helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import UnauthorizedError
from app.services.identity import api_keys as api_key_service


@pytest.mark.asyncio
async def test_create_key_returns_raw_once():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    # write_audit also calls flush
    row, raw = await api_key_service.create_key(
        db,
        workspace_id=uuid4(),
        created_by=uuid4(),
        name="CI",
        scopes=["documents:read"],
    )
    assert raw.startswith("vtk_")
    assert row.key_prefix == raw[:12]
    assert row.key_hash != raw
    assert db.add.called


@pytest.mark.asyncio
async def test_validate_key_rejects_bad_prefix():
    db = AsyncMock()
    with pytest.raises(UnauthorizedError):
        await api_key_service.validate_key(db, "not-a-key")
