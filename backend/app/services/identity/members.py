"""Workspace member management."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.domain import User, WorkspaceMember, WorkspaceRole
from app.services.audit.logger import write_audit


async def list_members(db: AsyncSession, workspace_id: UUID) -> list[tuple[WorkspaceMember, User]]:
    result = await db.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(WorkspaceMember.created_at.asc())
    )
    return list(result.all())


async def get_membership(
    db: AsyncSession, workspace_id: UUID, user_id: UUID
) -> WorkspaceMember | None:
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def count_owners(db: AsyncSession, workspace_id: UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(WorkspaceMember)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.role == WorkspaceRole.OWNER,
            )
        )
    ).scalar_one()


async def add_existing_member(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    email: str,
    role: WorkspaceRole,
    actor_id: UUID,
) -> tuple[WorkspaceMember, User]:
    if role == WorkspaceRole.OWNER:
        raise ForbiddenError(
            "Cannot directly assign owner via add member; transfer ownership separately"
        )

    target = (
        await db.execute(select(User).where(User.email == email.lower()))
    ).scalar_one_or_none()
    if not target:
        raise NotFoundError("User with that email does not exist. Send an invitation instead.")

    existing = await get_membership(db, workspace_id, target.id)
    if existing:
        raise ConflictError("User is already a member")

    member = WorkspaceMember(workspace_id=workspace_id, user_id=target.id, role=role)
    db.add(member)
    await db.flush()
    await write_audit(
        db,
        action="workspace.member.add",
        resource_type="workspace_member",
        resource_id=member.id,
        user_id=actor_id,
        workspace_id=workspace_id,
        details={"target_user_id": str(target.id), "role": role.value},
    )
    return member, target


async def change_role(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    target_user_id: UUID,
    new_role: WorkspaceRole,
    actor_id: UUID,
) -> WorkspaceMember:
    member = await get_membership(db, workspace_id, target_user_id)
    if not member:
        raise NotFoundError("Member not found")

    if member.role == WorkspaceRole.OWNER and new_role != WorkspaceRole.OWNER:
        if await count_owners(db, workspace_id) <= 1:
            raise ForbiddenError("Cannot demote the last owner")

    old = member.role
    member.role = new_role
    await db.flush()
    await write_audit(
        db,
        action="workspace.member.role_change",
        resource_type="workspace_member",
        resource_id=member.id,
        user_id=actor_id,
        workspace_id=workspace_id,
        details={
            "target_user_id": str(target_user_id),
            "from": old.value,
            "to": new_role.value,
        },
    )
    return member


async def remove_member(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    target_user_id: UUID,
    actor_id: UUID,
) -> None:
    member = await get_membership(db, workspace_id, target_user_id)
    if not member:
        raise NotFoundError("Member not found")

    if member.role == WorkspaceRole.OWNER and await count_owners(db, workspace_id) <= 1:
        raise ForbiddenError("Cannot remove the last owner")

    await write_audit(
        db,
        action="workspace.member.remove",
        resource_type="workspace_member",
        resource_id=member.id,
        user_id=actor_id,
        workspace_id=workspace_id,
        details={"target_user_id": str(target_user_id), "role": member.role.value},
    )
    await db.delete(member)
    await db.flush()
