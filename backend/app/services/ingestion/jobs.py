"""Ingestion job status tracking for Celery / inline pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import (
    IngestionJob,
    IngestionJobStage,
    IngestionJobStatus,
)


async def create_job(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    document_id: UUID,
    document_version_id: UUID | None = None,
    celery_task_id: str | None = None,
) -> IngestionJob:
    job = IngestionJob(
        workspace_id=workspace_id,
        document_id=document_id,
        document_version_id=document_version_id,
        celery_task_id=celery_task_id,
        status=IngestionJobStatus.QUEUED,
        stage=IngestionJobStage.PARSE,
    )
    db.add(job)
    await db.flush()
    return job


async def mark_processing(
    db: AsyncSession,
    job: IngestionJob,
    *,
    stage: IngestionJobStage = IngestionJobStage.PARSE,
) -> IngestionJob:
    job.status = IngestionJobStatus.PROCESSING
    job.stage = stage
    job.started_at = job.started_at or datetime.now(timezone.utc)
    await db.flush()
    return job


async def mark_stage(db: AsyncSession, job: IngestionJob, stage: IngestionJobStage) -> IngestionJob:
    job.stage = stage
    job.status = IngestionJobStatus.PROCESSING
    await db.flush()
    return job


async def mark_done(db: AsyncSession, job: IngestionJob) -> IngestionJob:
    job.status = IngestionJobStatus.DONE
    job.stage = IngestionJobStage.INDEX
    job.finished_at = datetime.now(timezone.utc)
    job.error_message = None
    await db.flush()
    return job


async def mark_failed(db: AsyncSession, job: IngestionJob, error: str) -> IngestionJob:
    job.status = IngestionJobStatus.FAILED
    job.error_message = error[:2000]
    job.retry_count = (job.retry_count or 0) + 1
    job.finished_at = datetime.now(timezone.utc)
    await db.flush()
    return job


async def latest_job(db: AsyncSession, document_id: UUID) -> IngestionJob | None:
    result = await db.execute(
        select(IngestionJob)
        .where(IngestionJob.document_id == document_id)
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
