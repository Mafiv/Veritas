"""Auth endpoints — register, login, me, refresh, logout, SSO."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.domain import User, Workspace, WorkspaceMember, WorkspaceRole
from app.models.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.services.audit.logger import record_login, write_audit
from app.services.identity import sso as sso_service
from app.services.identity import tokens as token_service

router = APIRouter(prefix="/auth", tags=["auth"])


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class SsoStartRequest(BaseModel):
    email: EmailStr | None = None
    workspace_id: UUID | None = None
    provider: str | None = None


class SsoDiscoverResponse(BaseModel):
    sso_available: bool
    provider: str | None = None
    enforced: bool = False
    authorize_url: str | None = None


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
    await record_login(
        db, email=user.email, success=True, user_id=user.id, ip_address=ip, user_agent=ua
    )
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
    if await sso_service.password_login_blocked(db, body.email.lower()):
        await record_login(
            db,
            email=body.email.lower(),
            success=False,
            failure_reason="sso_enforced",
            ip_address=ip,
            user_agent=ua,
        )
        raise ForbiddenError(
            "Password login is disabled for this domain. Use Continue with SSO."
        )

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


# ── SSO ───────────────────────────────────────────────────────────────────────


@router.get("/sso/discover", response_model=SsoDiscoverResponse)
async def sso_discover(
    db: DbSession,
    email: EmailStr = Query(...),
) -> SsoDiscoverResponse:
    found = await sso_service.find_connection_for_email(db, str(email))
    if not found:
        return SsoDiscoverResponse(sso_available=False)
    conn, _ws = found
    return SsoDiscoverResponse(
        sso_available=True,
        provider=conn.provider.value,
        enforced=bool(conn.is_enforced),
    )


@router.post("/sso/start")
async def sso_start(body: SsoStartRequest, db: DbSession, request: Request) -> dict[str, Any]:
    result = await sso_service.build_authorize_redirect(
        db,
        email=str(body.email) if body.email else None,
        workspace_id=body.workspace_id,
        provider=body.provider,
    )
    url = result["authorize_url"]
    if url.startswith("/"):
        base = str(request.base_url).rstrip("/")
        result["authorize_url"] = f"{base}{url}"
    elif result.get("redirect_uri_placeholder") == "true":
        from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

        callback = f"{str(request.base_url).rstrip('/')}/api/v1/auth/sso/oidc/callback"
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        qs["redirect_uri"] = [callback]
        flat = {k: v[0] for k, v in qs.items()}
        result["authorize_url"] = urlunparse(parsed._replace(query=urlencode(flat)))
        result.pop("redirect_uri_placeholder", None)
    return result


@router.get("/sso/mock/authorize", response_class=HTMLResponse)
async def sso_mock_authorize(
    state: str = Query(...),
    email: str = Query("user@example.com"),
    provider: str = Query("oidc"),
) -> str:
    """Dev IdP page — Continue posts to OIDC callback with a mock code."""
    return f"""<!doctype html>
<html><head><title>Veritas Mock IdP</title>
<style>
body{{font-family:system-ui;background:#f4f7f5;display:flex;min-height:100vh;align-items:center;justify-content:center}}
.card{{background:#fff;border:1px solid #d7e0db;border-radius:16px;padding:2rem;max-width:420px;width:100%}}
h1{{font-size:1.25rem;margin:0 0 .5rem}}
p{{color:#5b6b63;font-size:.9rem}}
button{{background:#0f766e;color:#fff;border:0;border-radius:10px;padding:.75rem 1rem;width:100%;font-weight:600;cursor:pointer}}
input{{width:100%;padding:.6rem;margin:.5rem 1rem;border:1px solid #d7e0db;border-radius:8px;box-sizing:border-box}}
</style></head>
<body><div class="card">
<h1>Mock {provider.upper()} IdP</h1>
<p>Development SSO — no external identity provider required.</p>
<form method="get" action="/api/v1/auth/sso/oidc/callback">
  <input type="hidden" name="state" value="{state}" />
  <label>Email</label>
  <input name="code" value="mock_{email}" />
  <p style="font-size:.75rem">Code is <code>mock_&lt;email&gt;</code> for local exchange.</p>
  <button type="submit">Continue with SSO</button>
</form>
</div></body></html>"""


@router.get("/sso/oidc/callback")
async def sso_oidc_callback(
    db: DbSession,
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
) -> RedirectResponse:
    ip, ua = _client_meta(request)
    redirect_uri = f"{str(request.base_url).rstrip('/')}/api/v1/auth/sso/oidc/callback"
    tokens = await sso_service.exchange_oidc_code(
        db,
        code=code,
        state=state,
        redirect_uri=redirect_uri,
        ip_address=ip,
        user_agent=ua,
    )
    settings = get_settings()
    dest = (
        f"{settings.frontend_url.rstrip('/')}/auth/sso/callback"
        f"#access_token={tokens['access_token']}"
        f"&refresh_token={tokens['refresh_token']}"
        f"&provider={tokens.get('provider', 'oidc')}"
    )
    await write_audit(
        db,
        action="auth.sso_login",
        resource_type="user",
        details={"provider": tokens.get("provider")},
        ip_address=ip,
    )
    return RedirectResponse(url=dest, status_code=302)


@router.post("/sso/saml/acs")
async def sso_saml_acs(
    db: DbSession,
    request: Request,
    state: str = Form(default=""),
    email: str = Form(default=""),
    full_name: str = Form(default=""),
    NameID: str = Form(default=""),
) -> RedirectResponse:
    """SAML Assertion Consumer Service — accepts form-encoded mock/real assertions."""
    ip, ua = _client_meta(request)
    body = {
        "state": state,
        "email": email or NameID,
        "full_name": full_name,
        "name_id": NameID or email,
    }
    parsed = sso_service.parse_saml_mock_assertion(body)
    if not parsed["state"]:
        raise UnauthorizedError("Missing SAML RelayState/state")
    tokens = await sso_service.complete_saml_assertion(
        db,
        state=parsed["state"],
        email=parsed["email"],
        full_name=parsed["full_name"],
        name_id=parsed["name_id"],
        ip_address=ip,
        user_agent=ua,
    )
    settings = get_settings()
    dest = (
        f"{settings.frontend_url.rstrip('/')}/auth/sso/callback"
        f"#access_token={tokens['access_token']}"
        f"&refresh_token={tokens['refresh_token']}"
        f"&provider=saml"
    )
    return RedirectResponse(url=dest, status_code=302)
