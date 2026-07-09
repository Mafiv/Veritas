"""Reusable audit logging — call from any sensitive action."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import AuditLog, LoginHistory


async def write_audit(
    db: AsyncSession,
    *,
    action: str,
    resource_type: str,
    resource_id: str | UUID | None = None,
    user_id: UUID | None = None,
    workspace_id: UUID | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    row = AuditLog(
        user_id=user_id,
        workspace_id=workspace_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        details=details,
        ip_address=ip_address,
    )
    db.add(row)
    await db.flush()
    return row


async def record_login(
    db: AsyncSession,
    *,
    email: str,
    success: bool,
    user_id: UUID | None = None,
    failure_reason: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> LoginHistory:
    row = LoginHistory(
        user_id=user_id,
        email=email.lower(),
        success=success,
        failure_reason=failure_reason,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(row)
    await db.flush()
    return row
