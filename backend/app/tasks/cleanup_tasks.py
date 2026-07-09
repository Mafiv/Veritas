"""Periodic cleanup tasks — orphaned files + soft-deleted document purge."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import get_settings
from app.tasks.celery_app import celery_app


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.run(coro)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@celery_app.task(name="app.tasks.cleanup_tasks.cleanup_orphaned_files")
def cleanup_orphaned_files() -> dict:
    return _run(_cleanup())


async def _cleanup() -> dict:
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.domain import Document

    settings = get_settings()
    root = Path(settings.local_storage_path)
    if not root.exists():
        return {"removed": 0, "path": str(root)}

    async with AsyncSessionLocal() as session:
        paths = set(
            (
                await session.execute(select(Document.storage_path))
            )
            .scalars()
            .all()
        )

    removed = 0
    scanned = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if "exports" in path.parts:
            continue
        scanned += 1
        if str(path) not in paths:
            try:
                path.unlink(missing_ok=True)
                removed += 1
            except OSError:
                pass
    return {"removed": removed, "scanned": scanned, "path": str(root)}
