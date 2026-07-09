"""Periodic cleanup tasks."""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.cleanup_tasks.cleanup_orphaned_files")
def cleanup_orphaned_files() -> dict:
    settings = get_settings()
    root = Path(settings.local_storage_path)
    if not root.exists():
        return {"removed": 0}
    # Placeholder: full orphan detection requires DB lookup in async context
    return {"removed": 0, "path": str(root)}
