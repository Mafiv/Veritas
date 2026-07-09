"""Shared links and webhook endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

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


class WebhookEndpointUpdate(BaseModel):
    url: Optional[str] = Field(default=None, min_length=8, max_length=1000)
    event_types: Optional[list[str]] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class WebhookEndpointCreated(WebhookEndpointOut):
    secret: Optional[str] = None


class WebhookDeliveryOut(BaseModel):
    id: UUID
    endpoint_id: UUID
    event_type: str
    status: str
    http_status: Optional[int] = None
    attempt_count: int
    created_at: datetime
    delivered_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SharePreviewOut(BaseModel):
    id: UUID
    workspace_id: UUID
    resource_type: str
    resource_id: UUID
    view_count: int
    allow_download: bool
    expires_at: Optional[datetime] = None
    preview: dict[str, Any]


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


@router.get("/share/{token}", response_model=SharePreviewOut)
async def resolve_shared_link(
    token: str,
    db: DbSession,
    password: str | None = None,
) -> SharePreviewOut:
    link = await enterprise_service.resolve_shared_link(
        db, token=token, password=password
    )
    preview = await enterprise_service.shared_link_preview(db, link)
    return SharePreviewOut(
        id=link.id,
        workspace_id=link.workspace_id,
        resource_type=link.resource_type.value
        if hasattr(link.resource_type, "value")
        else str(link.resource_type),
        resource_id=link.resource_id,
        view_count=link.view_count,
        allow_download=link.allow_download,
        expires_at=link.expires_at,
        preview=preview,
    )


@router.get("/workspaces/{workspace_id}/webhooks", response_model=list[WebhookEndpointOut])
async def list_webhooks(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> list[WebhookEndpointOut]:
    rows = await enterprise_service.list_webhooks(db, workspace_id)
    return [WebhookEndpointOut.model_validate(r) for r in rows]


@router.post(
    "/workspaces/{workspace_id}/webhooks",
    response_model=WebhookEndpointCreated,
)
async def create_webhook(
    workspace_id: UUID,
    body: WebhookEndpointCreate,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> WebhookEndpointCreated:
    ep, secret = await enterprise_service.create_webhook(
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
    out = WebhookEndpointCreated.model_validate(ep)
    out.secret = secret
    return out


@router.patch(
    "/workspaces/{workspace_id}/webhooks/{endpoint_id}",
    response_model=WebhookEndpointOut,
)
async def update_webhook(
    workspace_id: UUID,
    endpoint_id: UUID,
    body: WebhookEndpointUpdate,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> WebhookEndpointOut:
    ep = await enterprise_service.update_webhook(
        db,
        workspace_id=workspace_id,
        endpoint_id=endpoint_id,
        url=body.url,
        event_types=body.event_types,
        description=body.description,
        is_active=body.is_active,
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


@router.get(
    "/workspaces/{workspace_id}/webhooks/{endpoint_id}/deliveries",
    response_model=list[WebhookDeliveryOut],
)
async def list_webhook_deliveries(
    workspace_id: UUID,
    endpoint_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[WebhookDeliveryOut]:
    rows = await enterprise_service.list_deliveries(
        db, workspace_id=workspace_id, endpoint_id=endpoint_id, limit=limit
    )
    return [
        WebhookDeliveryOut(
            id=r.id,
            endpoint_id=r.endpoint_id,
            event_type=r.event_type,
            status=r.status.value if hasattr(r.status, "value") else str(r.status),
            http_status=r.http_status,
            attempt_count=r.attempt_count,
            created_at=r.created_at,
            delivered_at=r.delivered_at,
        )
        for r in rows
    ]


@router.post(
    "/workspaces/{workspace_id}/webhooks/deliveries/{delivery_id}/retry",
    response_model=WebhookDeliveryOut,
)
async def retry_webhook_delivery(
    workspace_id: UUID,
    delivery_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> WebhookDeliveryOut:
    r = await enterprise_service.retry_delivery(
        db, workspace_id=workspace_id, delivery_id=delivery_id
    )
    return WebhookDeliveryOut(
        id=r.id,
        endpoint_id=r.endpoint_id,
        event_type=r.event_type,
        status=r.status.value if hasattr(r.status, "value") else str(r.status),
        http_status=r.http_status,
        attempt_count=r.attempt_count,
        created_at=r.created_at,
        delivered_at=r.delivered_at,
    )
