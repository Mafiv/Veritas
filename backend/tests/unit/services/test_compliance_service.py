"""Unit tests for compliance helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.domain import ExportJobType, SsoProvider
from app.services.compliance import service as compliance_service


@pytest.mark.asyncio
async def test_upsert_sso_creates():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    empty = MagicMock()
    empty.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=empty)

    row = await compliance_service.upsert_sso(
        db,
        workspace_id=uuid4(),
        provider="oidc",
        issuer_url="https://idp.example",
        client_id="cid",
        domains=["example.com"],
    )
    assert row.provider == SsoProvider.OIDC
    assert row.domains == ["example.com"]
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_create_export_job():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    job = await compliance_service.create_export_job(
        db,
        user_id=uuid4(),
        workspace_id=uuid4(),
        job_type=ExportJobType.GDPR_USER_EXPORT,
    )
    assert job.job_type == ExportJobType.GDPR_USER_EXPORT
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_retention():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    empty = MagicMock()
    empty.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=empty)
    row = await compliance_service.upsert_retention(
        db,
        workspace_id=uuid4(),
        resource_type="documents",
        retain_days=90,
    )
    assert row.retain_days == 90
    assert row.resource_type == "documents"
