"""Workspace audit log listing (owner-only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, RequireOwner
from app.models.domain import AuditLog

router = APIRouter(tags=["audit"])


class AuditLogOut(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    workspace_id: Optional[UUID] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    ip_address: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/workspaces/{workspace_id}/audit-logs", response_model=list[AuditLogOut])
async def list_audit_logs(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[AuditLogOut]:
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.workspace_id == workspace_id)
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return [AuditLogOut.model_validate(r) for r in result.scalars().all()]
