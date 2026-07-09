"""In-app notifications."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain.notifications import Notification


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
) -> Notification:
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
