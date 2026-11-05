"""Auth endpoints — Better Auth bootstrap/sync and /me."""

from __future__ import annotations

import re
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.api.rate_limit import limit_per_ip
from app.core.better_auth import verify_better_auth_jwt
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.core.security import hash_password
from app.models.domain import User, Workspace, WorkspaceMember, WorkspaceRole
from app.models.schemas import UserOut
from app.services.audit.logger import write_audit
from app.services.identity.linking import email_verified_from_claims, find_linked_user

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)
OptionalBearer = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


class BootstrapRequest(BaseModel):
    auth_user_id: str = Field(min_length=1, max_length=128)
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    avatar_url: str | None = None
    # Better Auth's user.emailVerified. Trusted because the caller holds the
    # internal bootstrap secret; gates linking to a pre-existing account.
    email_verified: bool = False

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


async def _provision_veritas_user(
    db: AsyncSession,
    *,
    auth_user_id: str,
    email: str,
    full_name: str,
    avatar_url: str | None = None,
    email_verified: bool = False,
) -> BootstrapResponse:
    """Idempotent Veritas user + personal workspace provisioning."""
    email = email.lower()
    full_name = full_name.strip()
    user = await find_linked_user(
        db, auth_user_id=auth_user_id, email=email, email_verified=email_verified
    )
    if user:
        changed = False
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
        winner = await find_linked_user(
            db, auth_user_id=auth_user_id, email=email, email_verified=email_verified
        )
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
    Idempotent: returns the existing user for this auth_user_id. An existing
    account with the same email is linked only if the email is verified.
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
        email_verified=body.email_verified,
    )


@router.post(
    "/sync",
    response_model=BootstrapResponse,
    dependencies=[limit_per_ip("auth_sync", "rate_limit_auth_sync_per_minute")],
)
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
        email_verified=email_verified_from_claims(claims),
    )


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user
