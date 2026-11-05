"""Refresh token rotation (hashed at rest)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.core.security import create_access_token
from app.models.domain import RefreshToken, User


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def issue_refresh_token(
    db: AsyncSession,
    *,
    user_id: UUID,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> str:
    settings = get_settings()
    raw = secrets.token_urlsafe(48)
    row = RefreshToken(
        user_id=user_id,
        token_hash=_hash(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(row)
    await db.flush()
    return raw


async def rotate_refresh_token(
    db: AsyncSession,
    *,
    raw_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, str, User]:
    """Validate refresh token, revoke it, issue new access + refresh pair."""
    row = (
        await db.execute(select(RefreshToken).where(RefreshToken.token_hash == _hash(raw_token)))
    ).scalar_one_or_none()
    if not row:
        raise UnauthorizedError("Invalid refresh token")
    if row.revoked_at is not None:
        # Possible reuse — revoke all tokens for user
        siblings = await db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == row.user_id,
                RefreshToken.revoked_at.is_(None),
            )
        )
        now = datetime.now(timezone.utc)
        for s in siblings.scalars().all():
            s.revoked_at = now
        await db.flush()
        raise UnauthorizedError("Refresh token reuse detected")
    if row.expires_at < datetime.now(timezone.utc):
        raise UnauthorizedError("Refresh token expired")

    user = (await db.execute(select(User).where(User.id == row.user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise UnauthorizedError("User inactive")

    now = datetime.now(timezone.utc)
    row.revoked_at = now
    new_raw = await issue_refresh_token(
        db, user_id=user.id, user_agent=user_agent, ip_address=ip_address
    )
    # Link rotation chain
    new_row = (
        await db.execute(select(RefreshToken).where(RefreshToken.token_hash == _hash(new_raw)))
    ).scalar_one()
    row.replaced_by_id = new_row.id
    await db.flush()

    access = create_access_token(user.id, {"email": user.email})
    return access, new_raw, user


async def revoke_refresh_token(db: AsyncSession, *, raw_token: str) -> None:
    row = (
        await db.execute(select(RefreshToken).where(RefreshToken.token_hash == _hash(raw_token)))
    ).scalar_one_or_none()
    if row and row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        await db.flush()
