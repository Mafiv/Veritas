"""Background summarization tasks."""

from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.summarization_tasks.summarize_document")
def summarize_document(document_id: str) -> dict:
    # Summaries are generated during ingestion; this task is a hook for re-summarization.
    return {"document_id": document_id, "status": "queued"}
