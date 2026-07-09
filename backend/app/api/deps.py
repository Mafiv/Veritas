"""FastAPI dependency injection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import ForbiddenError, QuotaExceededError, UnauthorizedError
from app.core.security import safe_decode_token
from app.db.session import get_db
from app.models.domain import PlanTier, User, Workspace, WorkspaceMember, WorkspaceRole
from app.services.payment.stripe_client import plan_limits

bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


async def get_current_user(
    db: DbSession,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> User:
    if credentials is None:
        raise UnauthorizedError("Missing authentication token")
    payload = safe_decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise UnauthorizedError("Invalid or expired token")
    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_workspace_membership(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> tuple[Workspace, WorkspaceMember]:
    ws = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace = ws.scalar_one_or_none()
    if not workspace:
        raise ForbiddenError("Workspace not found")
    mem = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    member = mem.scalar_one_or_none()
    if not member:
        raise ForbiddenError("You do not have access to this workspace")
    return workspace, member


def require_role(*roles: WorkspaceRole):
    async def _checker(
        workspace_id: UUID,
        db: DbSession,
        user: CurrentUser,
    ) -> tuple[Workspace, WorkspaceMember]:
        workspace, member = await get_workspace_membership(workspace_id, db, user)
        if member.role not in roles and member.role != WorkspaceRole.OWNER:
            # Owner always allowed; otherwise must match
            if WorkspaceRole.OWNER not in roles and member.role not in roles:
                raise ForbiddenError("Insufficient workspace permissions")
        return workspace, member

    return _checker


async def check_query_quota(user: User, db: AsyncSession) -> None:
    limits = plan_limits(user.plan)
    now = datetime.now(timezone.utc)
    if user.queries_reset_at is None or user.queries_reset_at.date() < now.date():
        user.queries_today = 0
        user.queries_reset_at = now
        await db.flush()
    if user.queries_today >= limits["queries_per_day"]:
        raise QuotaExceededError(
            f"Daily query limit reached ({limits['queries_per_day']}). Upgrade your plan."
        )


async def check_document_quota(user: User, db: AsyncSession, workspace_id: UUID | None = None) -> None:
    from app.models.domain import Document

    limits = plan_limits(user.plan)
    # Count docs across owned workspaces for free tier simplicity
    count_q = (
        select(func.count())
        .select_from(Document)
        .join(Workspace, Workspace.id == Document.workspace_id)
        .where(Workspace.owner_id == user.id)
    )
    total = (await db.execute(count_q)).scalar_one()
    if total >= limits["documents"]:
        raise QuotaExceededError(
            f"Document limit reached ({limits['documents']}). Upgrade your plan."
        )


async def optional_auth(
    db: DbSession,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> User | None:
    if not credentials:
        return None
    try:
        return await get_current_user(db, credentials)
    except UnauthorizedError:
        return None
