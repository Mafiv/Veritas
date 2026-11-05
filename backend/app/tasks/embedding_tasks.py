"""Document ingestion task (parse → chunk → embed → summarize)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from app.tasks.celery_app import celery_app
from app.tasks.runtime import run_async, worker_session

# Retry only failures that are plausibly transient; a corrupt PDF will not fix itself.
TRANSIENT_ERRORS = (httpx.TransportError, ConnectionError, TimeoutError)


async def _process(document_id: UUID, job_id: UUID | None) -> dict[str, Any]:
    from app.services.ingestion.pipeline import IngestionService

    async with worker_session() as session:
        try:
            doc = await IngestionService().process_document(session, document_id, job_id=job_id)
        finally:
            # The pipeline records FAILED status before re-raising; keep it.
            await session.commit()
        return {"document_id": str(doc.id), "status": doc.status.value, "chunks": doc.chunk_count}


@celery_app.task(
    name="app.tasks.embedding_tasks.process_document",
    autoretry_for=TRANSIENT_ERRORS,
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def process_document(document_id: str, job_id: str | None = None) -> dict[str, Any]:
    return run_async(_process(UUID(document_id), UUID(job_id) if job_id else None))
