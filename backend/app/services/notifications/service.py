"""In-app notifications and preference-aware delivery."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain.base import NotificationChannel
from app.models.domain.notifications import Notification, NotificationPreference
from app.services.identity.email import get_email_sender

DEFAULT_EVENT_TYPES = (
    "document.ready",
    "document.failed",
    "invitation.received",
    "invitation.accepted",
    "billing.invoice",
)


async def notify_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    workspace_id: UUID | None = None,
    type: str,
    title: str,
    body: str | None = None,
    link_url: str | None = None,
    meta: dict[str, Any] | None = None,
) -> Notification | None:
    """Create an in-app notification (and optional email) respecting preferences."""
    if not await is_channel_enabled(
        db, user_id=user_id, event_type=type, channel=NotificationChannel.IN_APP
    ):
        row = None
    else:
        row = Notification(
            user_id=user_id,
            workspace_id=workspace_id,
            type=type,
            title=title,
            body=body,
            link_url=link_url,
            meta=meta or {},
        )
        db.add(row)
        await db.flush()

    if await is_channel_enabled(
        db, user_id=user_id, event_type=type, channel=NotificationChannel.EMAIL
    ):
        from app.models.domain import User

        user = await db.get(User, user_id)
        if user and user.email:
            sender = get_email_sender()
            await sender.send(
                to=user.email,
                subject=title,
                body=body or title,
            )
    return row


async def list_notifications(
    db: AsyncSession,
    *,
    user_id: UUID,
    unread_only: bool = False,
    limit: int = 50,
) -> list[Notification]:
    q = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    q = q.order_by(Notification.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def mark_read(
    db: AsyncSession,
    *,
    user_id: UUID,
    notification_id: UUID,
) -> Notification | None:
    row = await db.get(Notification, notification_id)
    if not row or row.user_id != user_id:
        return None
    if row.read_at is None:
        row.read_at = datetime.now(timezone.utc)
        await db.flush()
    return row


async def mark_all_read(db: AsyncSession, *, user_id: UUID) -> int:
    rows = await list_notifications(db, user_id=user_id, unread_only=True, limit=500)
    now = datetime.now(timezone.utc)
    for row in rows:
        row.read_at = now
    await db.flush()
    return len(rows)


async def is_channel_enabled(
    db: AsyncSession,
    *,
    user_id: UUID,
    event_type: str,
    channel: NotificationChannel | str,
) -> bool:
    if isinstance(channel, str):
        channel = NotificationChannel(channel)
    row = (
        await db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.event_type == event_type,
                NotificationPreference.channel == channel,
            )
        )
    ).scalar_one_or_none()
    # Opt-out model: missing row means enabled
    return True if row is None else bool(row.enabled)


async def list_preferences(
    db: AsyncSession, *, user_id: UUID
) -> list[NotificationPreference]:
    existing = list(
        (
            await db.execute(
                select(NotificationPreference).where(
                    NotificationPreference.user_id == user_id
                )
            )
        )
        .scalars()
        .all()
    )
    by_key = {(p.event_type, p.channel): p for p in existing}
    # Ensure defaults exist for UI
    created = False
    for event_type in DEFAULT_EVENT_TYPES:
        for channel in (NotificationChannel.IN_APP, NotificationChannel.EMAIL):
            key = (event_type, channel)
            if key not in by_key:
                pref = NotificationPreference(
                    user_id=user_id,
                    event_type=event_type,
                    channel=channel,
                    enabled=True,
                )
                db.add(pref)
                by_key[key] = pref
                created = True
    if created:
        await db.flush()
    return list(by_key.values())


async def upsert_preference(
    db: AsyncSession,
    *,
    user_id: UUID,
    event_type: str,
    channel: str | NotificationChannel,
    enabled: bool,
) -> NotificationPreference:
    if isinstance(channel, str):
        channel = NotificationChannel(channel)
    existing = (
        await db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.event_type == event_type,
                NotificationPreference.channel == channel,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.enabled = enabled
        await db.flush()
        return existing
    row = NotificationPreference(
        user_id=user_id,
        event_type=event_type,
        channel=channel,
        enabled=enabled,
    )
    db.add(row)
    await db.flush()
    return row
