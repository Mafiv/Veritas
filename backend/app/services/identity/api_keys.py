"""Workspace-scoped API keys (hash-at-rest, raw returned once)."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, UnauthorizedError
from app.models.domain import ApiKey, User, WorkspaceMember
from app.services.audit.logger import write_audit

KEY_PREFIX = "vtk_"


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class ValidatedApiKey:
    api_key: ApiKey
    user: User
    membership: WorkspaceMember


async def create_key(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    created_by: UUID,
    name: str,
    scopes: list[str],
    expires_at: datetime | None = None,
) -> tuple[ApiKey, str]:
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    display_prefix = raw[:12]
    row = ApiKey(
        workspace_id=workspace_id,
        created_by=created_by,
        name=name.strip(),
        key_prefix=display_prefix,
        key_hash=_hash_key(raw),
        scopes=scopes or ["documents:read", "chat:write"],
        expires_at=expires_at,
    )
    db.add(row)
    await db.flush()
    await write_audit(
        db,
        action="workspace.api_key.create",
        resource_type="api_key",
        resource_id=row.id,
        user_id=created_by,
        workspace_id=workspace_id,
        details={"name": name, "prefix": display_prefix, "scopes": scopes},
    )
    return row, raw


async def list_keys(db: AsyncSession, workspace_id: UUID) -> list[ApiKey]:
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.workspace_id == workspace_id,
            ApiKey.deleted_at.is_(None),
            ApiKey.revoked_at.is_(None),
        ).order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_key(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    key_id: UUID,
    actor_id: UUID,
) -> ApiKey:
    row = (
        await db.execute(
            select(ApiKey).where(
                ApiKey.id == key_id,
                ApiKey.workspace_id == workspace_id,
                ApiKey.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise NotFoundError("API key not found")
    now = datetime.now(timezone.utc)
    row.revoked_at = now
    row.deleted_at = now
    await db.flush()
    await write_audit(
        db,
        action="workspace.api_key.revoke",
        resource_type="api_key",
        resource_id=row.id,
        user_id=actor_id,
        workspace_id=workspace_id,
    )
    return row


async def validate_key(db: AsyncSession, raw_key: str) -> ValidatedApiKey:
    if not raw_key.startswith(KEY_PREFIX):
        raise UnauthorizedError("Invalid API key")
    row = (
        await db.execute(
            select(ApiKey).where(
                ApiKey.key_hash == _hash_key(raw_key),
                ApiKey.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not row or row.revoked_at is not None:
        raise UnauthorizedError("Invalid or revoked API key")
    if row.expires_at and row.expires_at < datetime.now(timezone.utc):
        raise UnauthorizedError("API key expired")

    user = (
        await db.execute(select(User).where(User.id == row.created_by, User.is_active.is_(True)))
    ).scalar_one_or_none()
    if not user:
        raise UnauthorizedError("API key owner inactive")

    membership = (
        await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == row.workspace_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if not membership:
        raise UnauthorizedError("API key owner is not a workspace member")

    row.last_used_at = datetime.now(timezone.utc)
    await db.flush()
    return ValidatedApiKey(api_key=row, user=user, membership=membership)
