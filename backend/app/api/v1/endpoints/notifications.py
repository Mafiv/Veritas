"""In-app notification endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.models.schemas.extended import (
    NotificationOut,
    NotificationPreferenceOut,
    NotificationPreferenceUpdate,
)
from app.services.notifications import service as notif_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
async def list_my_notifications(
    db: DbSession,
    user: CurrentUser,
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[NotificationOut]:
    rows = await notif_service.list_notifications(
        db, user_id=user.id, unread_only=unread_only, limit=limit
    )
    return [NotificationOut.model_validate(r) for r in rows]


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_read(
    notification_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> NotificationOut:
    row = await notif_service.mark_read(
        db, user_id=user.id, notification_id=notification_id
    )
    if not row:
        raise NotFoundError("Notification not found")
    return NotificationOut.model_validate(row)


@router.post("/read-all")
async def mark_all_notifications_read(db: DbSession, user: CurrentUser) -> dict:
    count = await notif_service.mark_all_read(db, user_id=user.id)
    return {"ok": True, "marked": count}


@router.get("/preferences", response_model=list[NotificationPreferenceOut])
async def get_preferences(
    db: DbSession, user: CurrentUser
) -> list[NotificationPreferenceOut]:
    rows = await notif_service.list_preferences(db, user_id=user.id)
    return [
        NotificationPreferenceOut(
            id=r.id,
            event_type=r.event_type,
            channel=r.channel.value if hasattr(r.channel, "value") else str(r.channel),
            enabled=r.enabled,
        )
        for r in rows
    ]


@router.put("/preferences", response_model=NotificationPreferenceOut)
async def update_preference(
    body: NotificationPreferenceUpdate,
    db: DbSession,
    user: CurrentUser,
) -> NotificationPreferenceOut:
    row = await notif_service.upsert_preference(
        db,
        user_id=user.id,
        event_type=body.event_type,
        channel=body.channel,
        enabled=body.enabled,
    )
    return NotificationPreferenceOut(
        id=row.id,
        event_type=row.event_type,
        channel=row.channel.value if hasattr(row.channel, "value") else str(row.channel),
        enabled=row.enabled,
    )
