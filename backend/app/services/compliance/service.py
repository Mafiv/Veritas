"""Compliance: SSO config, retention policies, GDPR export jobs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.models.domain import (
    DataRetentionPolicy,
    Document,
    ExportJob,
    ExportJobStatus,
    ExportJobType,
    SsoConnection,
    SsoProvider,
    User,
    Workspace,
)


async def upsert_sso(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    provider: str | SsoProvider,
    issuer_url: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    domains: list[str] | None = None,
    is_enforced: bool = False,
) -> SsoConnection:
    if isinstance(provider, str):
        provider = SsoProvider(provider)
    existing = (
        await db.execute(
            select(SsoConnection).where(
                SsoConnection.workspace_id == workspace_id,
                SsoConnection.provider == provider,
                SsoConnection.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.issuer_url = issuer_url
        existing.client_id = client_id
        if client_secret:
            # App-layer "encryption" placeholder — store opaque; real KMS later
            existing.client_secret_encrypted = f"enc:{client_secret}"
        existing.domains = domains or []
        existing.is_enforced = is_enforced
        existing.is_active = True
        await db.flush()
        return existing
    row = SsoConnection(
        workspace_id=workspace_id,
        provider=provider,
        issuer_url=issuer_url,
        client_id=client_id,
        client_secret_encrypted=f"enc:{client_secret}" if client_secret else None,
        domains=domains or [],
        is_enforced=is_enforced,
        is_active=True,
    )
    db.add(row)
    await db.flush()
    return row


async def list_sso(db: AsyncSession, workspace_id: UUID) -> list[SsoConnection]:
    return list(
        (
            await db.execute(
                select(SsoConnection).where(
                    SsoConnection.workspace_id == workspace_id,
                    SsoConnection.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )


async def upsert_retention(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    resource_type: str,
    retain_days: int,
    hard_delete: bool = True,
    notes: str | None = None,
) -> DataRetentionPolicy:
    existing = (
        await db.execute(
            select(DataRetentionPolicy).where(
                DataRetentionPolicy.workspace_id == workspace_id,
                DataRetentionPolicy.resource_type == resource_type,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.retain_days = retain_days
        existing.hard_delete = hard_delete
        existing.notes = notes
        existing.is_active = True
        await db.flush()
        return existing
    row = DataRetentionPolicy(
        workspace_id=workspace_id,
        resource_type=resource_type,
        retain_days=retain_days,
        hard_delete=hard_delete,
        notes=notes,
        is_active=True,
    )
    db.add(row)
    await db.flush()
    return row


async def list_retention(
    db: AsyncSession, workspace_id: UUID
) -> list[DataRetentionPolicy]:
    return list(
        (
            await db.execute(
                select(DataRetentionPolicy).where(
                    DataRetentionPolicy.workspace_id == workspace_id
                )
            )
        )
        .scalars()
        .all()
    )


async def create_export_job(
    db: AsyncSession,
    *,
    user_id: UUID,
    workspace_id: UUID | None = None,
    job_type: ExportJobType = ExportJobType.GDPR_USER_EXPORT,
) -> ExportJob:
    job = ExportJob(
        user_id=user_id,
        workspace_id=workspace_id,
        job_type=job_type,
        status=ExportJobStatus.QUEUED,
    )
    db.add(job)
    await db.flush()
    return job


async def list_export_jobs(db: AsyncSession, user_id: UUID) -> list[ExportJob]:
    return list(
        (
            await db.execute(
                select(ExportJob)
                .where(ExportJob.user_id == user_id)
                .order_by(ExportJob.created_at.desc())
            )
        )
        .scalars()
        .all()
    )


async def run_export_job(db: AsyncSession, job_id: UUID) -> ExportJob:
    """Generate a JSON export package (local storage). Full zip packaging can replace this."""
    job = await db.get(ExportJob, job_id)
    if not job:
        raise NotFoundError("Export job not found")
    job.status = ExportJobStatus.PROCESSING
    await db.flush()

    settings = get_settings()
    payload: dict = {
        "job_id": str(job.id),
        "job_type": job.job_type.value,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user_id": str(job.user_id),
    }

    user = await db.get(User, job.user_id)
    if user:
        payload["user"] = {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "plan": user.plan.value if hasattr(user.plan, "value") else str(user.plan),
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }

    if job.workspace_id:
        ws = await db.get(Workspace, job.workspace_id)
        docs = (
            await db.execute(
                select(Document).where(
                    Document.workspace_id == job.workspace_id,
                    Document.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        payload["workspace"] = {
            "id": str(ws.id) if ws else str(job.workspace_id),
            "name": ws.name if ws else None,
            "documents": [
                {
                    "id": str(d.id),
                    "filename": d.original_filename,
                    "status": d.status.value if hasattr(d.status, "value") else str(d.status),
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in docs
            ],
        }

    out_dir = Path(settings.local_storage_path) / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{job.id}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    job.storage_path = str(path)
    job.download_url = f"/exports/{job.id}/download"
    job.status = ExportJobStatus.READY
    job.completed_at = datetime.now(timezone.utc)
    job.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.flush()
    return job


async def apply_retention_purge(db: AsyncSession, workspace_id: UUID) -> dict:
    """Soft-delete documents older than retain_days for resource_type=documents."""
    policies = await list_retention(db, workspace_id)
    purged = 0
    now = datetime.now(timezone.utc)
    for policy in policies:
        if not policy.is_active or policy.resource_type != "documents":
            continue
        cutoff = now - timedelta(days=policy.retain_days)
        docs = (
            await db.execute(
                select(Document).where(
                    Document.workspace_id == workspace_id,
                    Document.deleted_at.is_(None),
                    Document.created_at < cutoff,
                )
            )
        ).scalars().all()
        for doc in docs:
            doc.deleted_at = now
            purged += 1
    await db.flush()
    return {"workspace_id": str(workspace_id), "purged_documents": purged}
