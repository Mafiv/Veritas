"""Shared links and webhook endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession, RequireEditor, RequireOwner
from app.models.schemas.extended import (
    SharedLinkCreate,
    SharedLinkOut,
    WebhookEndpointCreate,
    WebhookEndpointOut,
)
from app.services.audit.logger import write_audit
from app.services.enterprise import service as enterprise_service

router = APIRouter(tags=["enterprise"])


class ResolveShareRequest(BaseModel):
    password: str | None = None


@router.get("/workspaces/{workspace_id}/shared-links", response_model=list[SharedLinkOut])
async def list_shared_links(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireEditor,
) -> list[SharedLinkOut]:
    rows = await enterprise_service.list_shared_links(db, workspace_id)
    return [SharedLinkOut.model_validate(r) for r in rows]


@router.post("/workspaces/{workspace_id}/shared-links", response_model=SharedLinkOut)
async def create_shared_link(
    workspace_id: UUID,
    body: SharedLinkCreate,
    db: DbSession,
    user: CurrentUser,
    _access: RequireEditor,
) -> SharedLinkOut:
    link, raw = await enterprise_service.create_shared_link(
        db,
        workspace_id=workspace_id,
        created_by=user.id,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        expires_at=body.expires_at,
        password=body.password,
        allow_download=body.allow_download,
    )
    await write_audit(
        db,
        action="shared_link.create",
        resource_type=body.resource_type.value,
        resource_id=body.resource_id,
        user_id=user.id,
        workspace_id=workspace_id,
    )
    out = SharedLinkOut.model_validate(link)
    out.token = raw
    return out


@router.delete("/workspaces/{workspace_id}/shared-links/{link_id}")
async def revoke_shared_link(
    workspace_id: UUID,
    link_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireEditor,
) -> dict:
    await enterprise_service.revoke_shared_link(
        db, workspace_id=workspace_id, link_id=link_id
    )
    return {"ok": True}


@router.get("/share/{token}", response_model=SharedLinkOut)
async def resolve_shared_link(
    token: str,
    db: DbSession,
    password: str | None = None,
) -> SharedLinkOut:
    link = await enterprise_service.resolve_shared_link(
        db, token=token, password=password
    )
    return SharedLinkOut.model_validate(link)


@router.get("/workspaces/{workspace_id}/webhooks", response_model=list[WebhookEndpointOut])
async def list_webhooks(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> list[WebhookEndpointOut]:
    rows = await enterprise_service.list_webhooks(db, workspace_id)
    return [WebhookEndpointOut.model_validate(r) for r in rows]


@router.post("/workspaces/{workspace_id}/webhooks", response_model=WebhookEndpointOut)
async def create_webhook(
    workspace_id: UUID,
    body: WebhookEndpointCreate,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> WebhookEndpointOut:
    ep, _secret = await enterprise_service.create_webhook(
        db,
        workspace_id=workspace_id,
        created_by=user.id,
        url=body.url,
        event_types=body.event_types,
        description=body.description,
    )
    await write_audit(
        db,
        action="webhook.create",
        resource_type="webhook_endpoint",
        resource_id=ep.id,
        user_id=user.id,
        workspace_id=workspace_id,
        details={"url": body.url, "event_types": body.event_types},
    )
    return WebhookEndpointOut.model_validate(ep)


@router.delete("/workspaces/{workspace_id}/webhooks/{endpoint_id}")
async def delete_webhook(
    workspace_id: UUID,
    endpoint_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> dict:
    await enterprise_service.delete_webhook(
        db, workspace_id=workspace_id, endpoint_id=endpoint_id
    )
    return {"ok": True}
