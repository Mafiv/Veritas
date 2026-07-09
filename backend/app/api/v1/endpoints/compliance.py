"""Compliance endpoints — SSO, retention, GDPR exports."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, RequireOwner
from app.core.exceptions import NotFoundError
from app.models.domain import ExportJob, ExportJobType
from app.models.schemas.extended import (
    DataRetentionPolicyOut,
    DataRetentionPolicyUpsert,
    ExportJobCreate,
    ExportJobOut,
    SsoConnectionCreate,
    SsoConnectionOut,
)
from app.services.audit.logger import write_audit
from app.services.compliance import service as compliance_service

router = APIRouter(tags=["compliance"])


@router.get("/workspaces/{workspace_id}/sso", response_model=list[SsoConnectionOut])
async def list_sso(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> list[SsoConnectionOut]:
    rows = await compliance_service.list_sso(db, workspace_id)
    return [SsoConnectionOut.model_validate(r) for r in rows]


@router.put("/workspaces/{workspace_id}/sso", response_model=SsoConnectionOut)
async def upsert_sso(
    workspace_id: UUID,
    body: SsoConnectionCreate,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> SsoConnectionOut:
    row = await compliance_service.upsert_sso(
        db,
        workspace_id=workspace_id,
        provider=body.provider,
        issuer_url=body.issuer_url,
        client_id=body.client_id,
        client_secret=body.client_secret,
        domains=body.domains,
        is_enforced=body.is_enforced,
        metadata_xml=body.metadata_xml,
        is_active=body.is_active,
    )
    await write_audit(
        db,
        action="sso.upsert",
        resource_type="sso_connection",
        resource_id=row.id,
        user_id=user.id,
        workspace_id=workspace_id,
        details={"provider": body.provider},
    )
    return SsoConnectionOut.model_validate(row)


@router.delete("/workspaces/{workspace_id}/sso/{provider}")
async def delete_sso(
    workspace_id: UUID,
    provider: str,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> dict:
    await compliance_service.soft_delete_sso(
        db, workspace_id=workspace_id, provider=provider
    )
    await write_audit(
        db,
        action="sso.delete",
        resource_type="sso_connection",
        user_id=user.id,
        workspace_id=workspace_id,
        details={"provider": provider},
    )
    return {"ok": True}


@router.get(
    "/workspaces/{workspace_id}/retention-policies",
    response_model=list[DataRetentionPolicyOut],
)
async def list_retention(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> list[DataRetentionPolicyOut]:
    rows = await compliance_service.list_retention(db, workspace_id)
    return [DataRetentionPolicyOut.model_validate(r) for r in rows]


@router.put(
    "/workspaces/{workspace_id}/retention-policies",
    response_model=DataRetentionPolicyOut,
)
async def upsert_retention(
    workspace_id: UUID,
    body: DataRetentionPolicyUpsert,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> DataRetentionPolicyOut:
    row = await compliance_service.upsert_retention(
        db,
        workspace_id=workspace_id,
        resource_type=body.resource_type,
        retain_days=body.retain_days,
        hard_delete=body.hard_delete,
        notes=body.notes,
    )
    return DataRetentionPolicyOut.model_validate(row)


@router.post(
    "/workspaces/{workspace_id}/retention-policies/purge",
)
async def run_retention_purge(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> dict:
    result = await compliance_service.apply_retention_purge(db, workspace_id)
    await write_audit(
        db,
        action="retention.purge",
        resource_type="workspace",
        resource_id=workspace_id,
        user_id=user.id,
        workspace_id=workspace_id,
        details=result,
    )
    return result


@router.post("/exports", response_model=ExportJobOut)
async def create_export(
    body: ExportJobCreate,
    db: DbSession,
    user: CurrentUser,
) -> ExportJobOut:
    job = await compliance_service.create_export_job(
        db,
        user_id=user.id,
        workspace_id=body.workspace_id,
        job_type=body.job_type or ExportJobType.GDPR_USER_EXPORT,
    )
    # Run inline for reliability in mock/dev; Celery task also available
    job = await compliance_service.run_export_job(db, job.id)
    await write_audit(
        db,
        action="export.create",
        resource_type="export_job",
        resource_id=job.id,
        user_id=user.id,
        workspace_id=body.workspace_id,
        details={"job_type": job.job_type.value},
    )
    return ExportJobOut.model_validate(job)


@router.get("/exports", response_model=list[ExportJobOut])
async def list_exports(db: DbSession, user: CurrentUser) -> list[ExportJobOut]:
    rows = await compliance_service.list_export_jobs(db, user.id)
    return [ExportJobOut.model_validate(r) for r in rows]


@router.get("/exports/{job_id}/download")
async def download_export(
    job_id: UUID,
    db: DbSession,
    user: CurrentUser,
):
    job = (
        await db.execute(
            select(ExportJob).where(ExportJob.id == job_id, ExportJob.user_id == user.id)
        )
    ).scalar_one_or_none()
    if not job:
        raise NotFoundError("Export job not found")
    if not job.storage_path or not Path(job.storage_path).exists():
        raise NotFoundError("Export file not ready")
    return FileResponse(
        job.storage_path,
        media_type="application/json",
        filename=f"veritas-export-{job_id}.json",
    )
