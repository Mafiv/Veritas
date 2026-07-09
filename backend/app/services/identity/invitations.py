"""Workspace email invitations with expiring tokens."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, VeritasError
from app.models.domain import (
    Invitation,
    InvitationStatus,
    User,
    Workspace,
    WorkspaceMember,
    WorkspaceRole,
)
from app.services.audit.logger import write_audit
from app.services.identity.email import get_email_sender
from app.services.identity.members import get_membership


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def create_invitation(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    email: str,
    role: WorkspaceRole,
    invited_by: UUID,
    expires_days: int = 7,
) -> tuple[Invitation, str]:
    if role == WorkspaceRole.OWNER:
        raise ForbiddenError("Cannot invite someone as owner")

    email_l = email.lower().strip()
    existing_user = (
        await db.execute(select(User).where(User.email == email_l))
    ).scalar_one_or_none()
    if existing_user:
        mem = await get_membership(db, workspace_id, existing_user.id)
        if mem:
            raise ConflictError("User is already a member of this workspace")

    prior = await db.execute(
        select(Invitation).where(
            Invitation.workspace_id == workspace_id,
            Invitation.email == email_l,
            Invitation.status == InvitationStatus.PENDING,
            Invitation.deleted_at.is_(None),
        )
    )
    for inv in prior.scalars().all():
        inv.status = InvitationStatus.REVOKED

    raw = secrets.token_urlsafe(32)
    invitation = Invitation(
        workspace_id=workspace_id,
        email=email_l,
        role=role,
        invited_by=invited_by,
        token_hash=_hash_token(raw),
        status=InvitationStatus.PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_days),
    )
    db.add(invitation)
    await db.flush()

    ws = (await db.execute(select(Workspace).where(Workspace.id == workspace_id))).scalar_one()
    settings = get_settings()
    accept_url = f"{settings.frontend_url}/invitations/accept?token={raw}"
    await get_email_sender().send(
        to=email_l,
        subject=f"You're invited to {ws.name} on Veritas",
        body=(
            f"You've been invited to join the workspace \"{ws.name}\" as {role.value}.\n\n"
            f"Accept: {accept_url}\n\n"
            f"This link expires at {invitation.expires_at.isoformat()}."
        ),
    )
    # In-app notification if invitee already has an account
    if existing_user:
        from app.services.notifications.service import notify_user

        await notify_user(
            db,
            user_id=existing_user.id,
            workspace_id=workspace_id,
            type="invitation.received",
            title=f"Invited to {ws.name}",
            body=f"You've been invited as {role.value}.",
            link_url="/settings",
            meta={"invitation_id": str(invitation.id)},
        )
    await write_audit(
        db,
        action="workspace.invitation.create",
        resource_type="invitation",
        resource_id=invitation.id,
        user_id=invited_by,
        workspace_id=workspace_id,
        details={"email": email_l, "role": role.value},
    )
    return invitation, raw


async def list_invitations(
    db: AsyncSession, workspace_id: UUID, *, pending_only: bool = True
) -> list[Invitation]:
    stmt = select(Invitation).where(
        Invitation.workspace_id == workspace_id,
        Invitation.deleted_at.is_(None),
    )
    if pending_only:
        stmt = stmt.where(Invitation.status == InvitationStatus.PENDING)
    stmt = stmt.order_by(Invitation.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def accept_invitation(
    db: AsyncSession,
    *,
    raw_token: str,
    user: User,
) -> WorkspaceMember:
    token_hash = _hash_token(raw_token)
    invitation = (
        await db.execute(
            select(Invitation).where(
                Invitation.token_hash == token_hash,
                Invitation.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not invitation:
        raise NotFoundError("Invitation not found")
    if invitation.status != InvitationStatus.PENDING:
        raise VeritasError("Invitation is no longer pending", code="invitation_invalid")
    if invitation.expires_at < datetime.now(timezone.utc):
        invitation.status = InvitationStatus.EXPIRED
        await db.flush()
        raise VeritasError("Invitation has expired", code="invitation_expired")
    if invitation.email.lower() != user.email.lower():
        raise ForbiddenError("This invitation was sent to a different email address")

    existing = await get_membership(db, invitation.workspace_id, user.id)
    if existing:
        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_at = datetime.now(timezone.utc)
        invitation.accepted_by = user.id
        await db.flush()
        return existing

    member = WorkspaceMember(
        workspace_id=invitation.workspace_id,
        user_id=user.id,
        role=invitation.role,
    )
    db.add(member)
    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_at = datetime.now(timezone.utc)
    invitation.accepted_by = user.id
    await db.flush()
    await write_audit(
        db,
        action="workspace.invitation.accept",
        resource_type="invitation",
        resource_id=invitation.id,
        user_id=user.id,
        workspace_id=invitation.workspace_id,
        details={"role": invitation.role.value},
    )
    if invitation.invited_by:
        from app.services.notifications.service import notify_user

        await notify_user(
            db,
            user_id=invitation.invited_by,
            workspace_id=invitation.workspace_id,
            type="invitation.accepted",
            title="Invitation accepted",
            body=f"{user.email} joined the workspace.",
            link_url="/settings",
            meta={"invitation_id": str(invitation.id)},
        )
    return member


async def revoke_invitation(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    invitation_id: UUID,
    actor_id: UUID,
) -> Invitation:
    invitation = (
        await db.execute(
            select(Invitation).where(
                Invitation.id == invitation_id,
                Invitation.workspace_id == workspace_id,
                Invitation.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not invitation:
        raise NotFoundError("Invitation not found")
    invitation.status = InvitationStatus.REVOKED
    invitation.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    await write_audit(
        db,
        action="workspace.invitation.revoke",
        resource_type="invitation",
        resource_id=invitation.id,
        user_id=actor_id,
        workspace_id=workspace_id,
    )
    return invitation
