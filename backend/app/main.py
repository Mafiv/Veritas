"""Veritas FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.exceptions import VeritasError, error_payload
from app.db.session import engine
from app.models import domain  # noqa: F401 — register models
from app.models.schemas import HealthResponse
from app.services.monitoring.logger import get_logger, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.debug)
    log = get_logger()
    log.info("veritas.startup", env=settings.app_env, mock_llm=settings.use_mock_llm)

    # Schema is owned by Alembic (`alembic upgrade head`); never create_all here.

    yield
    await engine.dispose()
    log.info("veritas.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Veritas API",
        description="RAG-based Chat with your data — grounded, citation-backed answers.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(VeritasError)
    async def veritas_error_handler(_: Request, exc: VeritasError):
        return JSONResponse(status_code=exc.status_code, content=error_payload(exc))

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", app=settings.app_name, version="0.1.0")

    @app.get("/health/retrieval", tags=["health"])
    async def health_retrieval() -> dict:
        from app.services.retrieval.pgvector import describe_vector_strategy

        return {
            "reranker_backend": settings.reranker_backend,
            "use_mock_llm": settings.use_mock_llm,
            "vector": describe_vector_strategy(),
        }

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
