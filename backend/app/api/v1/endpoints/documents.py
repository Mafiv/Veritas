"""Document upload, list, delete endpoints."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, UploadFile
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, check_document_quota
from app.core.exceptions import ForbiddenError, NotFoundError
from app.db.session import AsyncSessionLocal
from app.models.domain import Document, DocumentStatus, WorkspaceMember, WorkspaceRole
from app.models.schemas import DocumentListResponse, DocumentOut
from app.services.ingestion.parser import detect_doc_type
from app.services.ingestion.pipeline import IngestionService

router = APIRouter(tags=["documents"])
ingestion = IngestionService()


async def _require_member(
    db: DbSession, workspace_id: UUID, user_id: UUID, write: bool = False
) -> WorkspaceMember:
    mem = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    member = mem.scalar_one_or_none()
    if not member:
        raise ForbiddenError("No access to this workspace")
    if write and member.role == WorkspaceRole.VIEWER:
        raise ForbiddenError("Viewers cannot modify documents")
    return member


async def _process_in_background(document_id: UUID) -> None:
    async with AsyncSessionLocal() as session:
        try:
            await ingestion.process_document(session, document_id)
            await session.commit()
        except Exception:
            await session.rollback()


@router.get("/workspaces/{workspace_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    workspace_id: UUID, db: DbSession, user: CurrentUser
) -> DocumentListResponse:
    await _require_member(db, workspace_id, user.id)
    result = await db.execute(
        select(Document)
        .where(Document.workspace_id == workspace_id)
        .order_by(Document.created_at.desc())
    )
    items = list(result.scalars().all())
    return DocumentListResponse(items=items, total=len(items))


@router.post("/workspaces/{workspace_id}/documents", response_model=DocumentOut)
async def upload_document(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> Document:
    await _require_member(db, workspace_id, user.id, write=True)
    await check_document_quota(user, db)

    data = await file.read()
    filename = file.filename or "upload.txt"
    content_type = file.content_type or "application/octet-stream"
    doc_type = detect_doc_type(filename, content_type)

    # Versioning: same original filename → bump version
    existing = await db.execute(
        select(Document)
        .where(
            Document.workspace_id == workspace_id,
            Document.original_filename == filename,
        )
        .order_by(Document.version.desc())
    )
    prev = existing.scalars().first()
    version = (prev.version + 1) if prev else 1

    storage_path = await ingestion.store_file(workspace_id, filename, data)
    doc = Document(
        workspace_id=workspace_id,
        uploaded_by=user.id,
        filename=Path(storage_path).name,
        original_filename=filename,
        content_type=content_type,
        doc_type=doc_type,
        status=DocumentStatus.PENDING,
        storage_path=storage_path,
        file_size=len(data),
        version=version,
    )
    db.add(doc)
    await db.flush()

    # Process inline for reliability in single-process/dev; also schedule background
    try:
        await ingestion.process_document(db, doc.id)
    except Exception:
        # Status already set to FAILED inside pipeline
        pass

    await db.refresh(doc)
    return doc


@router.get("/workspaces/{workspace_id}/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    workspace_id: UUID, document_id: UUID, db: DbSession, user: CurrentUser
) -> Document:
    await _require_member(db, workspace_id, user.id)
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id, Document.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document not found")
    return doc


@router.delete("/workspaces/{workspace_id}/documents/{document_id}")
async def delete_document(
    workspace_id: UUID, document_id: UUID, db: DbSession, user: CurrentUser
) -> dict:
    await _require_member(db, workspace_id, user.id, write=True)
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id, Document.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document not found")
    path = Path(doc.storage_path)
    if path.exists():
        path.unlink(missing_ok=True)
    await db.delete(doc)
    await db.flush()
    return {"ok": True}


@router.post("/workspaces/{workspace_id}/documents/{document_id}/reprocess", response_model=DocumentOut)
async def reprocess_document(
    workspace_id: UUID, document_id: UUID, db: DbSession, user: CurrentUser
) -> Document:
    await _require_member(db, workspace_id, user.id, write=True)
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id, Document.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document not found")
    await ingestion.process_document(db, doc.id)
    await db.refresh(doc)
    return doc
