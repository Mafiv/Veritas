"""Periodic cleanup tasks — orphaned files + soft-deleted document purge."""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.tasks.celery_app import celery_app
from app.tasks.runtime import run_async


@celery_app.task(name="app.tasks.cleanup_tasks.cleanup_orphaned_files")
def cleanup_orphaned_files() -> dict:
    return run_async(_cleanup())


async def _cleanup() -> dict:
    from sqlalchemy import select

    from app.tasks.runtime import worker_session
    from app.models.domain import Document

    settings = get_settings()
    root = Path(settings.local_storage_path)
    if not root.exists():
        return {"removed": 0, "path": str(root)}

    async with worker_session() as session:
        paths = set((await session.execute(select(Document.storage_path))).scalars().all())

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
