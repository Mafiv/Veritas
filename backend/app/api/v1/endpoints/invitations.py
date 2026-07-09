"""Public invitation acceptance (token-based)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.models.schemas import MemberOut
from app.services.identity import invitations as invitation_service
from app.services.identity import members as member_service

router = APIRouter(prefix="/invitations", tags=["invitations"])


class AcceptInvitationBody(BaseModel):
    token: str = Field(min_length=10)


@router.post("/{token}/accept", response_model=MemberOut)
async def accept_invitation_path(
    token: str,
    db: DbSession,
    user: CurrentUser,
) -> MemberOut:
    member = await invitation_service.accept_invitation(db, raw_token=token, user=user)
    rows = await member_service.list_members(db, member.workspace_id)
    for m, u in rows:
        if m.id == member.id:
            return MemberOut(
                id=m.id,
                user_id=u.id,
                email=u.email,
                full_name=u.full_name,
                role=m.role,
            )
    return MemberOut(
        id=member.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=member.role,
    )


@router.post("/accept", response_model=MemberOut)
async def accept_invitation_body(
    body: AcceptInvitationBody,
    db: DbSession,
    user: CurrentUser,
) -> MemberOut:
    return await accept_invitation_path(body.token, db, user)
