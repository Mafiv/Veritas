"""Celery application configuration."""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "veritas",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.embedding_tasks",
        "app.tasks.summarization_tasks",
        "app.tasks.cleanup_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    beat_schedule={
        "cleanup-orphaned-files-daily": {
            "task": "app.tasks.cleanup_tasks.cleanup_orphaned_files",
            "schedule": 60 * 60 * 24,
        },
    },
)
