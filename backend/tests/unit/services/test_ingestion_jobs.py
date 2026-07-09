"""Unit tests for ingestion job helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.domain import IngestionJobStage, IngestionJobStatus
from app.services.ingestion import jobs as job_service


@pytest.mark.asyncio
async def test_create_job():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    job = await job_service.create_job(
        db,
        workspace_id=uuid4(),
        document_id=uuid4(),
    )
    assert job.status == IngestionJobStatus.QUEUED
    assert job.stage == IngestionJobStage.PARSE
    db.add.assert_called_once()
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_mark_done_and_failed():
    db = AsyncMock()
    db.flush = AsyncMock()
    job = MagicMock()
    job.started_at = None
    job.retry_count = 0
    await job_service.mark_processing(db, job, stage=IngestionJobStage.EMBED)
    assert job.status == IngestionJobStatus.PROCESSING
    assert job.stage == IngestionJobStage.EMBED
    await job_service.mark_done(db, job)
    assert job.status == IngestionJobStatus.DONE
    assert job.stage == IngestionJobStage.INDEX

    job2 = MagicMock()
    job2.retry_count = 0
    await job_service.mark_failed(db, job2, "boom")
    assert job2.status == IngestionJobStatus.FAILED
    assert job2.retry_count == 1
    assert "boom" in job2.error_message
