"""Shared links and outbound webhooks (enterprise extras)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.security import decrypt_secret, encrypt_secret, hash_password, verify_password
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


async def shared_link_preview(db: AsyncSession, link: SharedLink) -> dict[str, Any]:
    """Safe public preview payload for a resolved share link."""
    preview: dict[str, Any] = {
        "resource_type": link.resource_type.value
        if hasattr(link.resource_type, "value")
        else str(link.resource_type),
        "resource_id": str(link.resource_id),
        "view_count": link.view_count,
        "allow_download": link.allow_download,
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
        "requires_password": bool(link.password_hash),
    }
    if link.resource_type == SharedLinkResourceType.DOCUMENT:
        from app.models.domain import Document

        doc = await db.get(Document, link.resource_id)
        if doc and doc.deleted_at is None:
            preview["title"] = doc.original_filename
            preview["summary"] = doc.summary
            preview["status"] = (
                doc.status.value if hasattr(doc.status, "value") else str(doc.status)
            )
            preview["suggested_questions"] = (doc.suggested_questions or [])[:5]
    elif link.resource_type == SharedLinkResourceType.THREAD:
        from app.models.domain import ChatThread

        thread = await db.get(ChatThread, link.resource_id)
        if thread and thread.deleted_at is None:
            preview["title"] = thread.title
            preview["is_shared"] = thread.is_shared
    elif link.resource_type == SharedLinkResourceType.COLLECTION:
        from app.models.domain import Collection, CollectionDocument

        col = await db.get(Collection, link.resource_id)
        if col and col.deleted_at is None:
            count = (
                await db.execute(
                    select(CollectionDocument).where(
                        CollectionDocument.collection_id == col.id
                    )
                )
            ).scalars().all()
            preview["title"] = col.name
            preview["description"] = col.description
            preview["document_count"] = len(count)
    return preview


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
        # Store encrypted reversible secret for signing deliveries; hash kept for lookup
        secret_hash=encrypt_secret(raw_secret),
        event_types=event_types,
        description=description,
        is_active=True,
    )
    db.add(endpoint)
    await db.flush()
    return endpoint, raw_secret


def webhook_signing_secret(endpoint: WebhookEndpoint) -> str:
    return decrypt_secret(endpoint.secret_hash)


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


async def update_webhook(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    endpoint_id: UUID,
    url: str | None = None,
    event_types: list[str] | None = None,
    description: str | None = None,
    is_active: bool | None = None,
) -> WebhookEndpoint:
    ep = await db.get(WebhookEndpoint, endpoint_id)
    if not ep or ep.workspace_id != workspace_id or ep.deleted_at is not None:
        raise NotFoundError("Webhook not found")
    if url is not None:
        ep.url = url
    if event_types is not None:
        ep.event_types = event_types
    if description is not None:
        ep.description = description
    if is_active is not None:
        ep.is_active = is_active
    await db.flush()
    return ep


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


async def list_deliveries(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    endpoint_id: UUID | None = None,
    limit: int = 50,
) -> list[WebhookDelivery]:
    q = (
        select(WebhookDelivery)
        .join(WebhookEndpoint, WebhookEndpoint.id == WebhookDelivery.endpoint_id)
        .where(
            WebhookEndpoint.workspace_id == workspace_id,
            WebhookEndpoint.deleted_at.is_(None),
        )
    )
    if endpoint_id:
        q = q.where(WebhookDelivery.endpoint_id == endpoint_id)
    q = q.order_by(WebhookDelivery.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def retry_delivery(
    db: AsyncSession, *, workspace_id: UUID, delivery_id: UUID
) -> WebhookDelivery:
    delivery = await db.get(WebhookDelivery, delivery_id)
    if not delivery:
        raise NotFoundError("Delivery not found")
    ep = await db.get(WebhookEndpoint, delivery.endpoint_id)
    if not ep or ep.workspace_id != workspace_id:
        raise NotFoundError("Delivery not found")
    delivery.status = WebhookDeliveryStatus.PENDING
    delivery.next_retry_at = None
    await db.flush()
    return delivery


def sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def schedule_retry(delivery: WebhookDelivery) -> None:
    settings = get_settings()
    attempt = delivery.attempt_count or 0
    if attempt >= settings.webhook_max_attempts:
        delivery.status = WebhookDeliveryStatus.FAILED
        return
    # Exponential backoff: 1m, 2m, 4m, ...
    delay = min(3600, 60 * (2 ** max(0, attempt - 1)))
    delivery.status = WebhookDeliveryStatus.PENDING
    delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
