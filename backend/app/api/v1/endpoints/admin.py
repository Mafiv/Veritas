"""Admin / usage overview endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import desc, func, select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import ForbiddenError
from app.models.domain import AuditLog, Document, PlanTier, UsageEvent, User, Workspace

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
async def admin_stats(db: DbSession, user: CurrentUser) -> dict:
    # Simple gate: only team-plan owners for now (or any user in debug)
    from app.core.config import get_settings

    if user.plan != PlanTier.TEAM and not get_settings().debug:
        raise ForbiddenError("Admin access requires Team plan")

    users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    workspaces = (await db.execute(select(func.count()).select_from(Workspace))).scalar_one()
    documents = (await db.execute(select(func.count()).select_from(Document))).scalar_one()
    queries = (
        await db.execute(
            select(func.count()).select_from(UsageEvent).where(UsageEvent.event_type == "query")
        )
    ).scalar_one()
    return {
        "users": users,
        "workspaces": workspaces,
        "documents": documents,
        "queries": queries,
    }


@router.get("/audit")
async def recent_audit(db: DbSession, user: CurrentUser, limit: int = 50) -> list[dict]:
    from app.core.config import get_settings

    if user.plan != PlanTier.TEAM and not get_settings().debug:
        raise ForbiddenError("Admin access requires Team plan")

    result = await db.execute(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit))
    logs = result.scalars().all()
    return [
        {
            "id": str(log.id),
            "user_id": str(log.user_id) if log.user_id else None,
            "workspace_id": str(log.workspace_id) if log.workspace_id else None,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
