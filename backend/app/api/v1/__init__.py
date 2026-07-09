"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1.endpoints import admin, auth, billing, chat, documents, workspaces

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
api_router.include_router(billing.router)
api_router.include_router(admin.router)
