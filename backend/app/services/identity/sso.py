"""OIDC / SAML / Google / Microsoft SSO helpers."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import create_access_token, decrypt_secret, encrypt_secret, hash_password
from app.models.domain import (
    SsoConnection,
    SsoProvider,
    User,
    Workspace,
    WorkspaceMember,
    WorkspaceRole,
)
from app.services.identity import tokens as token_service

# In-memory state store (Redis-backed in production). Fine for single-process / mock SSO.
_SSO_STATE: dict[str, dict[str, Any]] = {}


def _purge_expired_state() -> None:
    now = datetime.now(timezone.utc)
    expired = [k for k, v in _SSO_STATE.items() if v.get("expires_at", now) < now]
    for k in expired:
        _SSO_STATE.pop(k, None)


def _callback_base() -> str:
    settings = get_settings()
    return (settings.sso_callback_base_url or settings.frontend_url).rstrip("/")


def _api_callback(provider: str) -> str:
    settings = get_settings()
    # Backend ACS/callback lives on the API; frontend receives tokens via redirect
    # For mock SSO we redirect through API then bounce to frontend with tokens.
    # Use frontend_url host for display; API path is relative to API_V1.
    # Callers pass absolute API base via settings when needed.
    return f"{settings.frontend_url.rstrip('/')}/auth/sso/callback"


async def find_connection_for_email(
    db: AsyncSession, email: str
) -> tuple[SsoConnection, Workspace] | None:
    domain = email.lower().split("@")[-1] if "@" in email else ""
    if not domain:
        return None
    rows = (
        await db.execute(
            select(SsoConnection, Workspace)
            .join(Workspace, Workspace.id == SsoConnection.workspace_id)
            .where(
                SsoConnection.deleted_at.is_(None),
                SsoConnection.is_active.is_(True),
                Workspace.deleted_at.is_(None),
            )
        )
    ).all()
    for conn, ws in rows:
        domains = [d.lower() for d in (conn.domains or [])]
        if domain in domains:
            return conn, ws
    return None


async def password_login_blocked(db: AsyncSession, email: str) -> bool:
    found = await find_connection_for_email(db, email)
    if not found:
        return False
    conn, _ = found
    return bool(conn.is_enforced)


async def upsert_sso(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    provider: str | SsoProvider,
    issuer_url: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    domains: list[str] | None = None,
    is_enforced: bool = False,
    metadata_xml: str | None = None,
    is_active: bool = True,
) -> SsoConnection:
    if isinstance(provider, str):
        provider = SsoProvider(provider)
    existing = (
        await db.execute(
            select(SsoConnection).where(
                SsoConnection.workspace_id == workspace_id,
                SsoConnection.provider == provider,
                SsoConnection.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.issuer_url = issuer_url
        existing.client_id = client_id
        if client_secret:
            existing.client_secret_encrypted = encrypt_secret(client_secret)
        existing.domains = [d.lower().strip() for d in (domains or []) if d.strip()]
        existing.is_enforced = is_enforced
        existing.is_active = is_active
        if metadata_xml is not None:
            existing.metadata_xml = metadata_xml
        await db.flush()
        return existing
    row = SsoConnection(
        workspace_id=workspace_id,
        provider=provider,
        issuer_url=issuer_url,
        client_id=client_id,
        client_secret_encrypted=encrypt_secret(client_secret) if client_secret else None,
        domains=[d.lower().strip() for d in (domains or []) if d.strip()],
        is_enforced=is_enforced,
        is_active=is_active,
        metadata_xml=metadata_xml,
    )
    db.add(row)
    await db.flush()
    return row


async def list_sso(db: AsyncSession, workspace_id: UUID) -> list[SsoConnection]:
    return list(
        (
            await db.execute(
                select(SsoConnection).where(
                    SsoConnection.workspace_id == workspace_id,
                    SsoConnection.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )


async def soft_delete_sso(
    db: AsyncSession, *, workspace_id: UUID, provider: str | SsoProvider
) -> None:
    if isinstance(provider, str):
        provider = SsoProvider(provider)
    row = (
        await db.execute(
            select(SsoConnection).where(
                SsoConnection.workspace_id == workspace_id,
                SsoConnection.provider == provider,
                SsoConnection.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise NotFoundError("SSO connection not found")
    row.deleted_at = datetime.now(timezone.utc)
    row.is_active = False
    await db.flush()


def create_sso_state(
    *,
    connection_id: UUID,
    workspace_id: UUID,
    provider: str,
    email: str | None = None,
    nonce: str | None = None,
) -> str:
    _purge_expired_state()
    settings = get_settings()
    state = secrets.token_urlsafe(24)
    _SSO_STATE[state] = {
        "connection_id": str(connection_id),
        "workspace_id": str(workspace_id),
        "provider": provider,
        "email": email,
        "nonce": nonce or secrets.token_urlsafe(16),
        "expires_at": datetime.now(timezone.utc)
        + timedelta(seconds=settings.sso_state_ttl_seconds),
    }
    return state


def pop_sso_state(state: str) -> dict[str, Any]:
    _purge_expired_state()
    data = _SSO_STATE.pop(state, None)
    if not data:
        raise UnauthorizedError("Invalid or expired SSO state")
    return data


async def build_authorize_redirect(
    db: AsyncSession,
    *,
    email: str | None = None,
    workspace_id: UUID | None = None,
    provider: str | None = None,
) -> dict[str, str]:
    """Return {authorize_url, state, provider} for browser redirect."""
    settings = get_settings()
    conn: SsoConnection | None = None
    ws: Workspace | None = None

    if email:
        found = await find_connection_for_email(db, email)
        if found:
            conn, ws = found
    if conn is None and workspace_id and provider:
        conn = (
            await db.execute(
                select(SsoConnection).where(
                    SsoConnection.workspace_id == workspace_id,
                    SsoConnection.provider == SsoProvider(provider),
                    SsoConnection.deleted_at.is_(None),
                    SsoConnection.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if conn:
            ws = await db.get(Workspace, workspace_id)

    if not conn or not ws:
        raise NotFoundError("No SSO connection found for this email/domain")

    state = create_sso_state(
        connection_id=conn.id,
        workspace_id=ws.id,
        provider=conn.provider.value,
        email=email,
    )

    # Mock SSO: bounce through our own mock authorize page on the API
    if settings.use_mock_sso or not conn.issuer_url:
        params = urlencode(
            {
                "state": state,
                "email": email or f"user@{(conn.domains or ['example.com'])[0]}",
                "provider": conn.provider.value,
            }
        )
        return {
            "authorize_url": f"/api/v1/auth/sso/mock/authorize?{params}",
            "state": state,
            "provider": conn.provider.value,
            "mock": "true",
        }

    # Real OIDC authorize URL (discovery simplified — use issuer + /authorize)
    redirect_uri = f"{settings.frontend_url.rstrip('/')}/api/proxy-not-used"
    # Prefer API callback for code exchange
    # Callers should hit GET /auth/sso/oidc/callback on the API
    api_redirect = "{api}/auth/sso/oidc/callback"  # filled by endpoint with request.base_url
    params = {
        "client_id": conn.client_id or "",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "redirect_uri": api_redirect,
        "nonce": _SSO_STATE[state]["nonce"],
    }
    authorize = f"{conn.issuer_url.rstrip('/')}/authorize?{urlencode(params)}"
    return {
        "authorize_url": authorize,
        "state": state,
        "provider": conn.provider.value,
        "mock": "false",
        "redirect_uri_placeholder": "true",
    }


async def complete_sso_login(
    db: AsyncSession,
    *,
    state: str,
    email: str,
    full_name: str | None = None,
    subject: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict[str, str]:
    """JIT provision user + membership, issue tokens."""
    settings = get_settings()
    data = pop_sso_state(state)
    connection_id = UUID(data["connection_id"])
    workspace_id = UUID(data["workspace_id"])
    conn = await db.get(SsoConnection, connection_id)
    if not conn or conn.deleted_at is not None or not conn.is_active:
        raise ForbiddenError("SSO connection inactive")

    email_l = email.lower().strip()
    domain = email_l.split("@")[-1]
    if conn.domains and domain not in [d.lower() for d in conn.domains]:
        raise ForbiddenError("Email domain not allowed for this SSO connection")

    user = (
        await db.execute(select(User).where(User.email == email_l))
    ).scalar_one_or_none()
    if not user:
        # Random unusable password — SSO-only account
        user = User(
            email=email_l,
            full_name=(full_name or email_l.split("@")[0]).strip()[:200],
            hashed_password=hash_password(secrets.token_urlsafe(32)),
        )
        db.add(user)
        await db.flush()

    member = (
        await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if not member:
        role = (
            WorkspaceRole.EDITOR
            if settings.sso_jit_default_role == "editor"
            else WorkspaceRole.VIEWER
        )
        db.add(
            WorkspaceMember(
                workspace_id=workspace_id,
                user_id=user.id,
                role=role,
            )
        )
        await db.flush()

    refresh = await token_service.issue_refresh_token(
        db, user_id=user.id, user_agent=user_agent, ip_address=ip_address
    )
    access = create_access_token(user.id, {"email": user.email, "sso": data["provider"]})
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "provider": data["provider"],
        "subject": subject or hashlib.md5(email_l.encode()).hexdigest(),
    }


async def exchange_oidc_code(
    db: AsyncSession,
    *,
    code: str,
    state: str,
    redirect_uri: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict[str, str]:
    """Exchange authorization code (or mock code) for tokens + user claims."""
    settings = get_settings()
    data = _SSO_STATE.get(state)
    if not data:
        # pop will raise; peek first for connection
        raise UnauthorizedError("Invalid or expired SSO state")

    conn = await db.get(SsoConnection, UUID(data["connection_id"]))
    if not conn:
        raise NotFoundError("SSO connection not found")

    if settings.use_mock_sso or code.startswith("mock_"):
        # Mock code format: mock_<email>
        email = code.removeprefix("mock_")
        if "@" not in email:
            email = data.get("email") or f"user@{(conn.domains or ['example.com'])[0]}"
        return await complete_sso_login(
            db,
            state=state,
            email=email,
            full_name=email.split("@")[0].replace(".", " ").title(),
            subject=f"mock:{email}",
            ip_address=ip_address,
            user_agent=user_agent,
        )

    # Real OIDC token exchange
    import httpx

    secret = (
        decrypt_secret(conn.client_secret_encrypted)
        if conn.client_secret_encrypted
        else ""
    )
    token_url = f"{(conn.issuer_url or '').rstrip('/')}/token"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": conn.client_id or "",
                "client_secret": secret,
            },
        )
        if resp.status_code >= 400:
            raise UnauthorizedError(f"OIDC token exchange failed: {resp.text[:200]}")
        token_payload = resp.json()
        # Prefer userinfo
        email = None
        full_name = None
        sub = None
        access = token_payload.get("access_token")
        if access and conn.issuer_url:
            ui = await client.get(
                f"{conn.issuer_url.rstrip('/')}/userinfo",
                headers={"Authorization": f"Bearer {access}"},
            )
            if ui.status_code < 400:
                claims = ui.json()
                email = claims.get("email")
                full_name = claims.get("name")
                sub = claims.get("sub")
        if not email:
            raise UnauthorizedError("OIDC provider did not return an email claim")
    return await complete_sso_login(
        db,
        state=state,
        email=email,
        full_name=full_name,
        subject=sub,
        ip_address=ip_address,
        user_agent=user_agent,
    )


async def complete_saml_assertion(
    db: AsyncSession,
    *,
    state: str,
    email: str,
    full_name: str | None = None,
    name_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict[str, str]:
    """SAML ACS completion — assertion already validated by caller."""
    return await complete_sso_login(
        db,
        state=state,
        email=email,
        full_name=full_name,
        subject=name_id or email,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def parse_saml_mock_assertion(body: dict[str, Any]) -> dict[str, str]:
    """Dev/mock SAML ACS body: {state, email, full_name?, name_id?}."""
    email = body.get("email") or body.get("NameID")
    if not email:
        raise UnauthorizedError("SAML assertion missing email/NameID")
    return {
        "email": str(email),
        "full_name": str(body.get("full_name") or body.get("displayName") or email.split("@")[0]),
        "name_id": str(body.get("name_id") or body.get("NameID") or email),
        "state": str(body.get("state") or ""),
    }
