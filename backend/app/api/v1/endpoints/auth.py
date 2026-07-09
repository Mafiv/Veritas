"""Auth endpoints — register, login, me, refresh, logout."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.domain import User, Workspace, WorkspaceMember, WorkspaceRole
from app.models.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.services.audit.logger import record_login, write_audit
from app.services.identity import tokens as token_service

router = APIRouter(prefix="/auth", tags=["auth"])


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "workspace"


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, ua


@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterRequest, db: DbSession, request: Request) -> TokenResponse:
    existing = await db.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise ConflictError("An account with this email already exists")

    user = User(
        email=body.email.lower(),
        full_name=body.full_name.strip(),
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.flush()

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
    ip, ua = _client_meta(request)
    refresh = await token_service.issue_refresh_token(
        db, user_id=user.id, user_agent=ua, ip_address=ip
    )
    await record_login(db, email=user.email, success=True, user_id=user.id, ip_address=ip, user_agent=ua)
    await write_audit(
        db,
        action="auth.register",
        resource_type="user",
        resource_id=user.id,
        user_id=user.id,
        ip_address=ip,
    )
    await db.flush()

    return TokenResponse(
        access_token=create_access_token(user.id, {"email": user.email}),
        refresh_token=refresh,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: DbSession, request: Request) -> TokenResponse:
    ip, ua = _client_meta(request)
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        await record_login(
            db,
            email=body.email.lower(),
            success=False,
            user_id=user.id if user else None,
            failure_reason="invalid_credentials",
            ip_address=ip,
            user_agent=ua,
        )
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active or user.deleted_at is not None:
        await record_login(
            db,
            email=user.email,
            success=False,
            user_id=user.id,
            failure_reason="inactive",
            ip_address=ip,
            user_agent=ua,
        )
        raise UnauthorizedError("Invalid email or password")

    user.last_login_at = datetime.now(timezone.utc)
    refresh = await token_service.issue_refresh_token(
        db, user_id=user.id, user_agent=ua, ip_address=ip
    )
    await record_login(
        db, email=user.email, success=True, user_id=user.id, ip_address=ip, user_agent=ua
    )
    await write_audit(
        db,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
        user_id=user.id,
        ip_address=ip,
    )
    return TokenResponse(
        access_token=create_access_token(user.id, {"email": user.email}),
        refresh_token=refresh,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: DbSession, request: Request) -> TokenResponse:
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
