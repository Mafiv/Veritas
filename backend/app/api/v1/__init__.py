"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    audit,
    auth,
    billing,
    chat,
    compliance,
    documents,
    enterprise,
    invitations,
    notifications,
    workspaces,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(invitations.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
api_router.include_router(billing.router)
api_router.include_router(audit.router)
api_router.include_router(notifications.router)
api_router.include_router(enterprise.router)
api_router.include_router(compliance.router)
api_router.include_router(admin.router)
