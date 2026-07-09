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
        "app.tasks.webhook_tasks",
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
        "deliver-pending-webhooks": {
            "task": "app.tasks.webhook_tasks.deliver_pending_webhooks",
            "schedule": 60.0,
        },
        "rollup-usage-meters-hourly": {
            "task": "app.tasks.webhook_tasks.rollup_usage_meters",
            "schedule": 60 * 60,
        },
        "retention-purge-daily": {
            "task": "app.tasks.webhook_tasks.run_retention_purge_all",
            "schedule": 60 * 60 * 24,
        },
        "pgvector-backfill-hourly": {
            "task": "app.tasks.webhook_tasks.backfill_pgvector",
            "schedule": 60 * 60,
        },
    },
)
