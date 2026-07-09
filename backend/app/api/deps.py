"""FastAPI dependency injection — JWT + API key auth, role gates, quotas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import ForbiddenError, QuotaExceededError, UnauthorizedError
from app.core.security import safe_decode_token
from app.db.session import get_db
from app.models.domain import User, Workspace, WorkspaceMember, WorkspaceRole
from app.services.identity.api_keys import validate_key

bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

# Request-scoped workspace from API key auth (optional)
API_KEY_WORKSPACE_ATTR = "api_key_workspace_id"


async def get_current_user(
    request: Request,
    db: DbSession,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> User:
    if credentials is None:
        raise UnauthorizedError("Missing authentication token")

    token = credentials.credentials

    # API keys start with vtk_
    if token.startswith("vtk_"):
        validated = await validate_key(db, token)
        setattr(request.state, API_KEY_WORKSPACE_ATTR, validated.api_key.workspace_id)
        setattr(request.state, "api_key_scopes", validated.api_key.scopes)
        return validated.user

    payload = safe_decode_token(token)
    if not payload or payload.get("type") != "access":
        raise UnauthorizedError("Invalid or expired token")
    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    if user.deleted_at is not None:
        raise UnauthorizedError("User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_workspace_membership(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentUser,
    request: Request,
) -> tuple[Workspace, WorkspaceMember]:
    # If authenticated via API key, restrict to that workspace
    key_ws = getattr(request.state, API_KEY_WORKSPACE_ATTR, None)
    if key_ws is not None and key_ws != workspace_id:
        raise ForbiddenError("API key is not valid for this workspace")

    ws = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.deleted_at.is_(None))
    )
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
    """Require membership with one of the given roles. Owner always passes if OWNER in roles or always for owner-only checks.

    Convention: pass the *minimum* allowed roles. Owner is always allowed when
    any elevated role is required (editor/viewer lists). For owner-only endpoints,
    pass only WorkspaceRole.OWNER.
    """

    allowed = set(roles)

    async def _checker(
        workspace_id: UUID,
        db: DbSession,
        user: CurrentUser,
        request: Request,
    ) -> tuple[Workspace, WorkspaceMember]:
        workspace, member = await get_workspace_membership(workspace_id, db, user, request)
        if member.role == WorkspaceRole.OWNER:
            # Owner bypasses editor/viewer requirements; owner-only still OK
            return workspace, member
        if member.role not in allowed:
            raise ForbiddenError("Insufficient workspace permissions")
        return workspace, member

    return _checker


# Convenience aliases for route annotations
RequireViewer = Annotated[
    tuple[Workspace, WorkspaceMember],
    Depends(require_role(WorkspaceRole.VIEWER, WorkspaceRole.EDITOR, WorkspaceRole.OWNER)),
]
RequireEditor = Annotated[
    tuple[Workspace, WorkspaceMember],
    Depends(require_role(WorkspaceRole.EDITOR, WorkspaceRole.OWNER)),
]
RequireOwner = Annotated[
    tuple[Workspace, WorkspaceMember],
    Depends(require_role(WorkspaceRole.OWNER)),
]


async def check_query_quota(user: User, db: AsyncSession) -> None:
    from app.services.billing.service import plan_limits_from_db

    limits = await plan_limits_from_db(db, user.plan)
    now = datetime.now(timezone.utc)
    if user.queries_reset_at is None or user.queries_reset_at.date() < now.date():
        user.queries_today = 0
        user.queries_reset_at = now
        await db.flush()
    if user.queries_today >= limits["queries_per_day"]:
        raise QuotaExceededError(
            f"Daily query limit reached ({limits['queries_per_day']}). Upgrade your plan."
        )


async def check_document_quota(
    user: User, db: AsyncSession, workspace_id: UUID | None = None
) -> None:
    from app.models.domain import Document
    from app.services.billing.service import plan_limits_from_db

    limits = await plan_limits_from_db(db, user.plan)
    count_q = (
        select(func.count())
        .select_from(Document)
        .join(Workspace, Workspace.id == Document.workspace_id)
        .where(Workspace.owner_id == user.id)
        .where(Document.deleted_at.is_(None))
    )
    total = (await db.execute(count_q)).scalar_one()
    if total >= limits["documents"]:
        raise QuotaExceededError(
            f"Document limit reached ({limits['documents']}). Upgrade your plan."
        )


async def optional_auth(
    request: Request,
    db: DbSession,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> User | None:
    if not credentials:
        return None
    try:
        return await get_current_user(request, db, credentials)
    except UnauthorizedError:
        return None
