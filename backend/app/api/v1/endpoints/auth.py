"""Auth endpoints — Better Auth bootstrap, me, legacy refresh/logout."""

from __future__ import annotations

import re
import secrets

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.better_auth import verify_better_auth_jwt
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.core.security import hash_password
from app.models.domain import User, Workspace, WorkspaceMember, WorkspaceRole
from app.models.schemas import TokenResponse, UserOut
from app.services.audit.logger import write_audit
from app.services.identity import tokens as token_service

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)
OptionalBearer = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class BootstrapRequest(BaseModel):
    auth_user_id: str = Field(min_length=1, max_length=128)
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    avatar_url: str | None = None

    @field_validator("full_name")
    @classmethod
    def full_name_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("full_name must not be blank")
        return stripped


class BootstrapResponse(BaseModel):
    id: str
    email: EmailStr
    created: bool


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "workspace"


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, ua


async def _provision_veritas_user(
    db: AsyncSession,
    *,
    auth_user_id: str,
    email: str,
    full_name: str,
    avatar_url: str | None = None,
) -> BootstrapResponse:
    """Idempotent Veritas user + personal workspace provisioning."""
    email = email.lower()
    full_name = full_name.strip()
    existing = await db.execute(
        select(User).where((User.auth_user_id == auth_user_id) | (User.email == email))
    )
    user = existing.scalar_one_or_none()
    if user:
        changed = False
        if not user.auth_user_id:
            user.auth_user_id = auth_user_id
            changed = True
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
            changed = True
        if full_name and not user.full_name.strip():
            user.full_name = full_name
            changed = True
        if changed:
            await db.flush()
        return BootstrapResponse(id=str(user.id), email=user.email, created=False)

    user = User(
        email=email,
        full_name=full_name or email.split("@")[0],
        hashed_password=hash_password(secrets.token_urlsafe(32)),
        auth_user_id=auth_user_id,
        avatar_url=avatar_url,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        # Concurrent provisioning (bootstrap hook vs client /auth/sync) lost the
        # insert race — clear this session and return the winner's row.
        await db.rollback()
        raced = await db.execute(
            select(User).where((User.auth_user_id == auth_user_id) | (User.email == email))
        )
        winner = raced.scalar_one_or_none()
        if winner is None:
            raise
        return BootstrapResponse(id=str(winner.id), email=winner.email, created=False)

    base_slug = _slugify(f"{user.full_name}-workspace")
    slug = base_slug
    i = 1
    while True:
        clash = await db.execute(select(Workspace).where(Workspace.slug == slug))
        if not clash.scalar_one_or_none():
            break
        slug = f"{base_slug}-{i}"
        i += 1

    workspace = Workspace(
        name="Personal",
        slug=slug,
        description="Your personal research workspace",
        owner_id=user.id,
    )
    db.add(workspace)
    await db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role=WorkspaceRole.OWNER,
        )
    )
    await write_audit(
        db,
        action="auth.bootstrap",
        resource_type="user",
        resource_id=user.id,
        user_id=user.id,
    )
    await db.flush()
    return BootstrapResponse(id=str(user.id), email=user.email, created=True)


@router.post("/bootstrap", response_model=BootstrapResponse)
async def bootstrap_user(
    body: BootstrapRequest,
    db: DbSession,
    x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret"),
) -> BootstrapResponse:
    """Provision a Veritas user + personal workspace after Better Auth signup.

    Called by the Next.js Better Auth hook with a shared internal secret.
    Idempotent: returns existing user when auth_user_id or email already exists.
    """
    settings = get_settings()
    expected = settings.internal_auth_bootstrap_secret
    if (
        not expected
        or not x_internal_secret
        or not secrets.compare_digest(x_internal_secret, expected)
    ):
        raise UnauthorizedError("Invalid bootstrap secret")

    return await _provision_veritas_user(
        db,
        auth_user_id=body.auth_user_id,
        email=body.email,
        full_name=body.full_name,
        avatar_url=body.avatar_url,
    )


@router.post("/sync", response_model=BootstrapResponse)
async def sync_user(
    db: DbSession,
    credentials: OptionalBearer,
) -> BootstrapResponse:
    """Provision Veritas user from a valid Better Auth JWT (client-side recovery).

    Use after signup/login when the internal bootstrap hook failed or raced.
    """
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Missing authentication token")
    claims = verify_better_auth_jwt(credentials.credentials)
    auth_user_id = str(claims.get("sub") or claims.get("id") or "")
    email = str(claims.get("email") or "").lower()
    if not auth_user_id or not email:
        raise UnauthorizedError("Token missing subject or email")
    name = str(claims.get("name") or email.split("@")[0])
    image = claims.get("image")
    avatar = str(image) if image else None
    return await _provision_veritas_user(
        db,
        auth_user_id=auth_user_id,
        email=email,
        full_name=name,
        avatar_url=avatar,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: DbSession, request: Request) -> TokenResponse:
    """Legacy refresh — prefer Better Auth session + JWT token endpoint."""

    ip, ua = _client_meta(request)
    access, new_refresh, user = await token_service.rotate_refresh_token(
        db, raw_token=body.refresh_token, user_agent=ua, ip_address=ip
    )
    return TokenResponse(access_token=access, refresh_token=new_refresh)


@router.post("/logout")
async def logout(body: LogoutRequest, db: DbSession, user: CurrentUser) -> dict:
    await token_service.revoke_refresh_token(db, raw_token=body.refresh_token)
    await write_audit(
        db,
        action="auth.logout",
        resource_type="user",
        resource_id=user.id,
        user_id=user.id,
    )
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user
