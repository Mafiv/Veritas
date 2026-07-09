"""Workspace, members, invitations, and API key endpoints."""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import (
    CurrentUser,
    DbSession,
    RequireEditor,
    RequireOwner,
    RequireViewer,
)
from app.core.exceptions import QuotaExceededError
from app.models.domain import Document, Workspace, WorkspaceMember, WorkspaceRole
from app.models.schemas import (
    MemberInvite,
    MemberOut,
    WorkspaceCreate,
    WorkspaceOut,
)
from app.models.schemas.extended import (
    ApiKeyCreate,
    ApiKeyOut,
    InvitationCreate,
    InvitationOut,
)
from app.services.identity import api_keys as api_key_service
from app.services.identity import invitations as invitation_service
from app.services.identity import members as member_service
from app.services.payment.stripe_client import plan_limits

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class MemberRoleUpdate(BaseModel):
    role: WorkspaceRole


class AcceptInvitationRequest(BaseModel):
    token: str


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"


async def _to_out(db: DbSession, ws: Workspace) -> WorkspaceOut:
    members = (
        await db.execute(
            select(func.count())
            .select_from(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == ws.id)
        )
    ).scalar_one()
    docs = (
        await db.execute(
            select(func.count())
            .select_from(Document)
            .where(Document.workspace_id == ws.id, Document.deleted_at.is_(None))
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


def _member_out(member: WorkspaceMember, user) -> MemberOut:
    return MemberOut(
        id=member.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=member.role,
    )


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(db: DbSession, user: CurrentUser) -> list[WorkspaceOut]:
    result = await db.execute(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id, Workspace.deleted_at.is_(None))
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
            select(func.count())
            .select_from(Workspace)
            .where(Workspace.owner_id == user.id, Workspace.deleted_at.is_(None))
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
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=WorkspaceRole.OWNER))
    await db.flush()
    return await _to_out(db, ws)


@router.get("/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireViewer,
) -> WorkspaceOut:
    ws = _access[0]
    return await _to_out(db, ws)


# ── Members ───────────────────────────────────────────────────────────────────


@router.get("/{workspace_id}/members", response_model=list[MemberOut])
async def list_members(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireViewer,
) -> list[MemberOut]:
    rows = await member_service.list_members(db, workspace_id)
    return [_member_out(m, u) for m, u in rows]


@router.post("/{workspace_id}/members", response_model=MemberOut)
async def add_member(
    workspace_id: UUID,
    body: MemberInvite,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> MemberOut:
    """Add an already-registered user by email. Prefer invitations for new users."""
    member, target = await member_service.add_existing_member(
        db,
        workspace_id=workspace_id,
        email=body.email,
        role=body.role,
        actor_id=user.id,
    )
    return _member_out(member, target)


@router.patch("/{workspace_id}/members/{user_id}", response_model=MemberOut)
async def update_member_role(
    workspace_id: UUID,
    user_id: UUID,
    body: MemberRoleUpdate,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> MemberOut:
    member = await member_service.change_role(
        db,
        workspace_id=workspace_id,
        target_user_id=user_id,
        new_role=body.role,
        actor_id=user.id,
    )
    rows = await member_service.list_members(db, workspace_id)
    for m, u in rows:
        if m.id == member.id:
            return _member_out(m, u)
    return MemberOut(
        id=member.id,
        user_id=user_id,
        email="",
        full_name="",
        role=member.role,
    )


@router.delete("/{workspace_id}/members/{user_id}")
async def remove_member(
    workspace_id: UUID,
    user_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> dict:
    await member_service.remove_member(
        db,
        workspace_id=workspace_id,
        target_user_id=user_id,
        actor_id=user.id,
    )
    return {"ok": True}


# ── Invitations ───────────────────────────────────────────────────────────────


@router.post("/{workspace_id}/invitations", response_model=InvitationOut)
async def create_invitation(
    workspace_id: UUID,
    body: InvitationCreate,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> InvitationOut:
    invitation, _raw = await invitation_service.create_invitation(
        db,
        workspace_id=workspace_id,
        email=body.email,
        role=body.role,
        invited_by=user.id,
    )
    return InvitationOut.model_validate(invitation)


@router.get("/{workspace_id}/invitations", response_model=list[InvitationOut])
async def list_invitations(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> list[InvitationOut]:
    rows = await invitation_service.list_invitations(db, workspace_id)
    return [InvitationOut.model_validate(r) for r in rows]


@router.delete("/{workspace_id}/invitations/{invitation_id}", response_model=InvitationOut)
async def revoke_invitation(
    workspace_id: UUID,
    invitation_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> InvitationOut:
    invitation = await invitation_service.revoke_invitation(
        db,
        workspace_id=workspace_id,
        invitation_id=invitation_id,
        actor_id=user.id,
    )
    return InvitationOut.model_validate(invitation)


# ── API keys ──────────────────────────────────────────────────────────────────


@router.post("/{workspace_id}/api-keys", response_model=ApiKeyOut)
async def create_api_key(
    workspace_id: UUID,
    body: ApiKeyCreate,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> ApiKeyOut:
    row, raw = await api_key_service.create_key(
        db,
        workspace_id=workspace_id,
        created_by=user.id,
        name=body.name,
        scopes=body.scopes,
        expires_at=body.expires_at,
    )
    out = ApiKeyOut.model_validate(row)
    out.secret = raw
    return out


@router.get("/{workspace_id}/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> list[ApiKeyOut]:
    rows = await api_key_service.list_keys(db, workspace_id)
    return [ApiKeyOut.model_validate(r) for r in rows]


@router.delete("/{workspace_id}/api-keys/{key_id}", response_model=ApiKeyOut)
async def revoke_api_key(
    workspace_id: UUID,
    key_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> ApiKeyOut:
    row = await api_key_service.revoke_key(
        db, workspace_id=workspace_id, key_id=key_id, actor_id=user.id
    )
    return ApiKeyOut.model_validate(row)
