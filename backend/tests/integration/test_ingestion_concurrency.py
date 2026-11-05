"""Ingestion under the conditions the Celery worker creates.

Both tests reproduce bugs found while running the full Docker stack: two
documents of one workspace processed at the same time, and a database error
in the middle of processing.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.domain import (
    Document,
    DocumentStatus,
    DocumentType,
    Entity,
    IngestionJob,
    IngestionJobStatus,
    User,
    Workspace,
)
from app.services.ingestion import jobs as job_service
from app.services.ingestion.pipeline import IngestionService

from .conftest import TEST_DATABASE_URL, make_workspace

SHARED_TEXT = (
    "Title\n\nThe Style Guide covers Python Code Layout and Naming Conventions.\n\n"
    "Maximum Line Length is discussed in the Style Guide by Guido van Rossum."
)


async def _new_document(
    db: AsyncSession, user: User, ws: Workspace, name: str, tmp_path: Path
) -> tuple[Document, IngestionJob]:
    path = tmp_path / f"{uuid.uuid4().hex}_{name}"
    path.write_text(SHARED_TEXT + f"\n\nOnly in {name}.")
    doc = Document(
        workspace_id=ws.id,
        uploaded_by=user.id,
        filename=name,
        original_filename=name,
        content_type="text/plain",
        doc_type=DocumentType.TEXT,
        status=DocumentStatus.PENDING,
        storage_path=str(path),
        file_size=path.stat().st_size,
    )
    db.add(doc)
    await db.flush()
    job = await job_service.create_job(db, workspace_id=ws.id, document_id=doc.id)
    return doc, job


async def test_concurrent_documents_share_entities_without_conflict(tmp_path: Path) -> None:
    """Two worker sessions extracting the same entities must both succeed.

    Uses committed data on separate connections (like real worker processes)
    and cleans up afterwards.
    """
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    engine = create_async_engine(TEST_DATABASE_URL)
    async with AsyncSession(engine, expire_on_commit=False) as setup:
        user, ws = await make_workspace(setup)
        doc_a, job_a = await _new_document(setup, user, ws, "a.txt", tmp_path)
        doc_b, job_b = await _new_document(setup, user, ws, "b.txt", tmp_path)
        await setup.commit()

    async def process(doc_id: uuid.UUID, job_id: uuid.UUID) -> DocumentStatus:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            doc = await IngestionService().process_document(session, doc_id, job_id=job_id)
            await session.commit()
            return doc.status

    try:
        statuses = await asyncio.wait_for(
            asyncio.gather(process(doc_a.id, job_a.id), process(doc_b.id, job_b.id)),
            timeout=60,
        )
        assert statuses == [DocumentStatus.READY, DocumentStatus.READY]
        async with AsyncSession(engine) as check:
            names = (
                (
                    await check.execute(
                        select(Entity.normalized_name).where(Entity.workspace_id == ws.id)
                    )
                )
                .scalars()
                .all()
            )
        assert len(names) == len(set(names)) and "style guide" in names
    finally:
        async with engine.begin() as conn:
            for stmt in (
                "DELETE FROM document_entities WHERE document_id IN "
                "(SELECT id FROM documents WHERE workspace_id = :ws)",
                "DELETE FROM entities WHERE workspace_id = :ws",
                "DELETE FROM notifications WHERE workspace_id = :ws",
                "DELETE FROM documents WHERE workspace_id = :ws",
                "DELETE FROM workspaces WHERE id = :ws",
                "DELETE FROM users WHERE id = :user",
            ):
                await conn.execute(text(stmt), {"ws": ws.id, "user": user.id})
        await engine.dispose()


async def test_database_error_marks_document_failed_instead_of_stuck(
    db: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, ws = await make_workspace(db)
    doc, job = await _new_document(db, user, ws, "broken.txt", tmp_path)

    async def failing_entities(self, session, document, body):  # noqa: ANN001
        await session.execute(text("SELECT 1 / 0"))  # any DB-level failure

    monkeypatch.setattr(IngestionService, "_extract_entities", failing_entities)
    with pytest.raises(Exception, match="division by zero"):
        await IngestionService().process_document(db, doc.id, job_id=job.id)

    # Before the SAVEPOINT fix the session was unusable here and the document
    # stayed "pending" forever.
    await db.refresh(doc)
    await db.refresh(job)
    assert doc.status == DocumentStatus.FAILED
    assert "division by zero" in (doc.error_message or "")
    assert job.status == IngestionJobStatus.FAILED
    assert (await db.execute(select(1))).scalar_one() == 1
