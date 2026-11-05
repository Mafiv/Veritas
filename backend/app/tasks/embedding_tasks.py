"""Background embedding / reprocessing tasks."""

from __future__ import annotations

import asyncio
from uuid import UUID

from app.tasks.celery_app import celery_app


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@celery_app.task(name="app.tasks.embedding_tasks.process_document")
def process_document(document_id: str) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.services.ingestion.pipeline import IngestionService

    async def _inner():
        async with AsyncSessionLocal() as session:
            svc = IngestionService()
            doc = await svc.process_document(session, UUID(document_id))
            await session.commit()
            return {
                "document_id": str(doc.id),
                "status": doc.status.value,
                "chunks": doc.chunk_count,
            }

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.run(_inner())
        return loop.run_until_complete(_inner())
    except RuntimeError:
        return asyncio.run(_inner())
