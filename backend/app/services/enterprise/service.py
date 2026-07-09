"""Shared links and outbound webhooks (enterprise extras)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.security import hash_password, verify_password
from app.models.domain import (
    SharedLink,
    SharedLinkResourceType,
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookEndpoint,
)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def create_shared_link(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    created_by: UUID,
    resource_type: SharedLinkResourceType | str,
    resource_id: UUID,
    expires_at: datetime | None = None,
    password: str | None = None,
    allow_download: bool = False,
) -> tuple[SharedLink, str]:
    if isinstance(resource_type, str):
        resource_type = SharedLinkResourceType(resource_type)
    raw = secrets.token_urlsafe(24)
    link = SharedLink(
        workspace_id=workspace_id,
        created_by=created_by,
        resource_type=resource_type,
        resource_id=resource_id,
        token_hash=_hash_token(raw),
        password_hash=hash_password(password) if password else None,
        expires_at=expires_at,
        allow_download=allow_download,
    )
    db.add(link)
    await db.flush()
    return link, raw


async def resolve_shared_link(
    db: AsyncSession,
    *,
    token: str,
    password: str | None = None,
) -> SharedLink:
    link = (
        await db.execute(
            select(SharedLink).where(
                SharedLink.token_hash == _hash_token(token),
                SharedLink.deleted_at.is_(None),
                SharedLink.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not link:
        raise NotFoundError("Shared link not found")
    if link.expires_at and link.expires_at < datetime.now(timezone.utc):
        raise ForbiddenError("Shared link has expired")
    if link.password_hash:
        if not password or not verify_password(password, link.password_hash):
            raise ForbiddenError("Invalid share password")
    link.view_count = (link.view_count or 0) + 1
    await db.flush()
    return link


async def list_shared_links(
    db: AsyncSession, workspace_id: UUID
) -> list[SharedLink]:
    return list(
        (
            await db.execute(
                select(SharedLink)
                .where(
                    SharedLink.workspace_id == workspace_id,
                    SharedLink.deleted_at.is_(None),
                    SharedLink.revoked_at.is_(None),
                )
                .order_by(SharedLink.created_at.desc())
            )
        )
        .scalars()
        .all()
    )


async def revoke_shared_link(
    db: AsyncSession, *, workspace_id: UUID, link_id: UUID
) -> None:
    link = await db.get(SharedLink, link_id)
    if not link or link.workspace_id != workspace_id:
        raise NotFoundError("Shared link not found")
    link.revoked_at = datetime.now(timezone.utc)
    await db.flush()


async def create_webhook(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    created_by: UUID,
    url: str,
    event_types: list[str],
    description: str | None = None,
) -> tuple[WebhookEndpoint, str]:
    raw_secret = secrets.token_urlsafe(32)
    endpoint = WebhookEndpoint(
        workspace_id=workspace_id,
        created_by=created_by,
        url=url,
        secret_hash=_hash_token(raw_secret),
        event_types=event_types,
        description=description,
        is_active=True,
    )
    db.add(endpoint)
    await db.flush()
    return endpoint, raw_secret


async def list_webhooks(db: AsyncSession, workspace_id: UUID) -> list[WebhookEndpoint]:
    return list(
        (
            await db.execute(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.workspace_id == workspace_id,
                    WebhookEndpoint.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )


async def delete_webhook(
    db: AsyncSession, *, workspace_id: UUID, endpoint_id: UUID
) -> None:
    ep = await db.get(WebhookEndpoint, endpoint_id)
    if not ep or ep.workspace_id != workspace_id:
        raise NotFoundError("Webhook not found")
    ep.deleted_at = datetime.now(timezone.utc)
    ep.is_active = False
    await db.flush()


async def enqueue_webhook_deliveries(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    event_type: str,
    payload: dict[str, Any],
) -> list[WebhookDelivery]:
    endpoints = await list_webhooks(db, workspace_id)
    deliveries: list[WebhookDelivery] = []
    for ep in endpoints:
        if not ep.is_active:
            continue
        if event_type not in (ep.event_types or []):
            continue
        d = WebhookDelivery(
            endpoint_id=ep.id,
            event_type=event_type,
            payload=payload,
            status=WebhookDeliveryStatus.PENDING,
            attempt_count=0,
        )
        db.add(d)
        deliveries.append(d)
    await db.flush()
    return deliveries


def sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
