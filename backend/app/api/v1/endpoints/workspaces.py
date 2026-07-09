"""Workspace endpoints."""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, QuotaExceededError
from app.models.domain import Document, User, Workspace, WorkspaceMember, WorkspaceRole
from app.models.schemas import MemberInvite, MemberOut, WorkspaceCreate, WorkspaceOut
from app.services.payment.stripe_client import plan_limits

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"


async def _to_out(db: DbSession, ws: Workspace) -> WorkspaceOut:
    members = (
        await db.execute(
            select(func.count()).select_from(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ws.id
            )
        )
    ).scalar_one()
    docs = (
        await db.execute(
            select(func.count()).select_from(Document).where(Document.workspace_id == ws.id)
        )
    ).scalar_one()
    return WorkspaceOut(
        id=ws.id,
        name=ws.name,
        slug=ws.slug,
        description=ws.description,
        owner_id=ws.owner_id,
        created_at=ws.created_at,
        member_count=members,
        document_count=docs,
    )


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(db: DbSession, user: CurrentUser) -> list[WorkspaceOut]:
    result = await db.execute(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(Workspace.created_at.desc())
    )
    workspaces = result.scalars().all()
    return [await _to_out(db, ws) for ws in workspaces]


@router.post("", response_model=WorkspaceOut)
async def create_workspace(
    body: WorkspaceCreate, db: DbSession, user: CurrentUser
) -> WorkspaceOut:
    limits = plan_limits(user.plan)
    owned = (
        await db.execute(
            select(func.count()).select_from(Workspace).where(Workspace.owner_id == user.id)
        )
    ).scalar_one()
    if owned >= limits["workspaces"]:
        raise QuotaExceededError(
            f"Workspace limit reached ({limits['workspaces']}). Upgrade your plan."
        )

    base = _slugify(body.name)
    slug = base
    i = 1
    while True:
        clash = await db.execute(select(Workspace).where(Workspace.slug == slug))
        if not clash.scalar_one_or_none():
            break
        slug = f"{base}-{i}"
        i += 1

    ws = Workspace(
        name=body.name.strip(),
        slug=slug,
        description=body.description,
        owner_id=user.id,
    )
    db.add(ws)
    await db.flush()
    db.add(
        WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=WorkspaceRole.OWNER)
    )
    await db.flush()
    return await _to_out(db, ws)


@router.get("/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(workspace_id: UUID, db: DbSession, user: CurrentUser) -> WorkspaceOut:
    mem = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if not mem.scalar_one_or_none():
        raise ForbiddenError("No access to this workspace")
    ws = (
        await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ).scalar_one_or_none()
    if not ws:
        raise NotFoundError("Workspace not found")
    return await _to_out(db, ws)


@router.get("/{workspace_id}/members", response_model=list[MemberOut])
async def list_members(workspace_id: UUID, db: DbSession, user: CurrentUser) -> list[MemberOut]:
    mem = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if not mem.scalar_one_or_none():
        raise ForbiddenError("No access")
    rows = await db.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace_id)
    )
    out: list[MemberOut] = []
    for member, u in rows.all():
        out.append(
            MemberOut(
                id=member.id,
                user_id=u.id,
                email=u.email,
                full_name=u.full_name,
                role=member.role,
            )
        )
    return out


@router.post("/{workspace_id}/members", response_model=MemberOut)
async def invite_member(
    workspace_id: UUID, body: MemberInvite, db: DbSession, user: CurrentUser
) -> MemberOut:
    mem = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    actor = mem.scalar_one_or_none()
    if not actor or actor.role not in (WorkspaceRole.OWNER, WorkspaceRole.EDITOR):
        raise ForbiddenError("Only owners and editors can invite members")

    target = (
        await db.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()
    if not target:
        raise NotFoundError("User with that email does not exist. They must register first.")

    existing = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == target.id,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError("User is already a member")

    member = WorkspaceMember(
        workspace_id=workspace_id, user_id=target.id, role=body.role
    )
    db.add(member)
    await db.flush()
    return MemberOut(
        id=member.id,
        user_id=target.id,
        email=target.email,
        full_name=target.full_name,
        role=member.role,
    )
