"""Unit tests for billing plan seeding and meters."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.domain import PlanTier
from app.services.billing import service as billing_service


def _result(scalar=None, rows=None):
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    r.scalars.return_value.all.return_value = rows or []
    return r


@pytest.mark.asyncio
async def test_ensure_default_plans_seeds():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(return_value=_result(rows=[]))
    plans = await billing_service.ensure_default_plans(db)
    assert len(plans) == 3
    assert db.add.call_count == 3


@pytest.mark.asyncio
async def test_bump_meter_creates():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(return_value=_result(scalar=None))
    meter = await billing_service.bump_meter(
        db,
        workspace_id=uuid4(),
        user_id=uuid4(),
        meter_key="query",
        quantity=2,
    )
    assert meter.quantity == 2
    assert meter.meter_key == "query"
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_record_usage_with_meter():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(return_value=_result(scalar=None))
    event = await billing_service.record_usage(
        db,
        user_id=uuid4(),
        workspace_id=uuid4(),
        event_type="query",
        quantity=1,
        meter_key="query",
    )
    assert event.event_type == "query"
    # usage event + meter
    assert db.add.call_count >= 2
