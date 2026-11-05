"""Document upload, list, delete, versions, permissions, collections."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import (
    CurrentUser,
    DbSession,
    RequireEditor,
    RequireOwner,
    RequireViewer,
    check_document_quota,
)
from app.core.exceptions import NotFoundError
from app.models.domain import Document, DocumentStatus
from app.models.schemas import DocumentListResponse, DocumentOut
from app.models.schemas.extended import (
    CollectionCreate,
    CollectionOut,
    DocumentPermissionCreate,
    DocumentPermissionOut,
    DocumentVersionOut,
    EntityOut,
    IngestionJobOut,
    SuggestedQuestionOut,
)
from app.services.audit.logger import write_audit
from app.services.documents import service as doc_service
from app.services.ingestion import jobs as job_service
from app.services.ingestion.parser import detect_doc_type
from app.services.ingestion.pipeline import IngestionService

router = APIRouter(tags=["documents"])
ingestion = IngestionService()


class CollectionAddDocument(BaseModel):
    document_id: UUID


@router.get("/workspaces/{workspace_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireViewer,
) -> DocumentListResponse:
    result = await db.execute(
        select(Document)
        .where(Document.workspace_id == workspace_id, Document.deleted_at.is_(None))
        .order_by(Document.created_at.desc())
    )
    items = list(result.scalars().all())
    return DocumentListResponse(items=items, total=len(items))


@router.post("/workspaces/{workspace_id}/documents", response_model=DocumentOut)
async def upload_document(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireEditor,
    file: UploadFile = File(...),
) -> Document:
    await check_document_quota(user, db)

    data = await file.read()
    filename = file.filename or "upload.txt"
    content_type = file.content_type or "application/octet-stream"
    doc_type = detect_doc_type(filename, content_type)

    existing = await db.execute(
        select(Document)
        .where(
            Document.workspace_id == workspace_id,
            Document.original_filename == filename,
            Document.deleted_at.is_(None),
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

    job = await job_service.create_job(
        db,
        workspace_id=workspace_id,
        document_id=doc.id,
    )

    try:
        await ingestion.process_document(db, doc.id, job_id=job.id)
    except Exception:
        pass

    await write_audit(
        db,
        action="document.upload",
        resource_type="document",
        resource_id=doc.id,
        user_id=user.id,
        workspace_id=workspace_id,
        details={"filename": filename, "version": version, "job_id": str(job.id)},
    )
    await db.refresh(doc)
    return doc


@router.get("/workspaces/{workspace_id}/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    workspace_id: UUID,
    document_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireViewer,
) -> Document:
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document not found")
    return doc


@router.get("/workspaces/{workspace_id}/documents/{document_id}/file")
async def get_document_file(
    workspace_id: UUID,
    document_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireViewer,
) -> FileResponse:
    """Stream the original uploaded file for in-app preview / download."""
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document not found")
    path = Path(doc.storage_path)
    if not path.exists():
        raise NotFoundError("Document file not found on storage")
    return FileResponse(
        path,
        media_type=doc.content_type or "application/octet-stream",
        filename=doc.original_filename,
        content_disposition_type="inline",
    )


@router.get(
    "/workspaces/{workspace_id}/documents/{document_id}/status",
    response_model=IngestionJobOut,
)
async def document_ingestion_status(
    workspace_id: UUID,
    document_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireViewer,
) -> IngestionJobOut:
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document not found")
    job = await job_service.latest_job(db, document_id)
    if not job:
        raise NotFoundError("No ingestion job found")
    return IngestionJobOut.model_validate(job)


@router.get(
    "/workspaces/{workspace_id}/documents/{document_id}/versions",
    response_model=list[DocumentVersionOut],
)
async def document_versions(
    workspace_id: UUID,
    document_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireViewer,
) -> list[DocumentVersionOut]:
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document not found")
    versions = await doc_service.list_versions(db, document_id)
    return [DocumentVersionOut.model_validate(v) for v in versions]


@router.get(
    "/workspaces/{workspace_id}/documents/{document_id}/questions",
    response_model=list[SuggestedQuestionOut],
)
async def document_questions(
    workspace_id: UUID,
    document_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireViewer,
) -> list[SuggestedQuestionOut]:
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document not found")
    rows = await doc_service.list_suggested_questions(db, document_id)
    return [SuggestedQuestionOut.model_validate(r) for r in rows]


@router.get(
    "/workspaces/{workspace_id}/documents/{document_id}/entities",
    response_model=list[EntityOut],
)
async def document_entities(
    workspace_id: UUID,
    document_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireViewer,
) -> list[EntityOut]:
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document not found")
    entities = await doc_service.list_document_entities(db, document_id)
    return [EntityOut.model_validate(e) for e in entities]


@router.get(
    "/workspaces/{workspace_id}/documents/{document_id}/permissions",
    response_model=list[DocumentPermissionOut],
)
async def list_document_permissions(
    workspace_id: UUID,
    document_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> list[DocumentPermissionOut]:
    rows = await doc_service.list_permissions(db, document_id)
    return [DocumentPermissionOut.model_validate(r) for r in rows]


@router.post(
    "/workspaces/{workspace_id}/documents/{document_id}/permissions",
    response_model=DocumentPermissionOut,
)
async def create_document_permission(
    workspace_id: UUID,
    document_id: UUID,
    body: DocumentPermissionCreate,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> DocumentPermissionOut:
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document not found")
    row = await doc_service.grant_permission(
        db,
        document_id=document_id,
        user_id=body.user_id,
        granted_by=user.id,
        scope=body.scope,
        page_start=body.page_start,
        page_end=body.page_end,
        section_heading=body.section_heading,
        can_read=body.can_read,
        can_cite=body.can_cite,
    )
    return DocumentPermissionOut.model_validate(row)


@router.delete("/workspaces/{workspace_id}/documents/{document_id}/permissions/{permission_id}")
async def delete_document_permission(
    workspace_id: UUID,
    document_id: UUID,
    permission_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireOwner,
) -> dict:
    await doc_service.revoke_permission(db, document_id=document_id, permission_id=permission_id)
    return {"ok": True}


@router.delete("/workspaces/{workspace_id}/documents/{document_id}")
async def delete_document(
    workspace_id: UUID,
    document_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireEditor,
) -> dict:
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document not found")
    path = Path(doc.storage_path)
    if path.exists():
        path.unlink(missing_ok=True)
    await write_audit(
        db,
        action="document.delete",
        resource_type="document",
        resource_id=doc.id,
        user_id=user.id,
        workspace_id=workspace_id,
        details={"filename": doc.original_filename},
    )
    await db.delete(doc)
    await db.flush()
    return {"ok": True}


@router.post(
    "/workspaces/{workspace_id}/documents/{document_id}/reprocess",
    response_model=DocumentOut,
)
async def reprocess_document(
    workspace_id: UUID,
    document_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireEditor,
) -> Document:
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document not found")
    job = await job_service.create_job(
        db,
        workspace_id=workspace_id,
        document_id=doc.id,
        document_version_id=doc.active_version_id,
    )
    await ingestion.process_document(db, doc.id, job_id=job.id)
    await db.refresh(doc)
    return doc


# ── Collections ───────────────────────────────────────────────────────────────


@router.get("/workspaces/{workspace_id}/collections", response_model=list[CollectionOut])
async def list_collections(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireViewer,
) -> list[CollectionOut]:
    rows = await doc_service.list_collections(db, workspace_id)
    return [
        CollectionOut(
            id=c.id,
            workspace_id=c.workspace_id,
            name=c.name,
            description=c.description,
            created_at=c.created_at,
            document_count=count,
        )
        for c, count in rows
    ]


@router.post("/workspaces/{workspace_id}/collections", response_model=CollectionOut)
async def create_collection(
    workspace_id: UUID,
    body: CollectionCreate,
    db: DbSession,
    user: CurrentUser,
    _access: RequireEditor,
) -> CollectionOut:
    col = await doc_service.create_collection(
        db,
        workspace_id=workspace_id,
        created_by=user.id,
        name=body.name,
        description=body.description,
        document_ids=body.document_ids,
    )
    return CollectionOut(
        id=col.id,
        workspace_id=col.workspace_id,
        name=col.name,
        description=col.description,
        created_at=col.created_at,
        document_count=len(body.document_ids or []),
    )


@router.post(
    "/workspaces/{workspace_id}/collections/{collection_id}/documents",
    response_model=CollectionOut,
)
async def add_collection_document(
    workspace_id: UUID,
    collection_id: UUID,
    body: CollectionAddDocument,
    db: DbSession,
    user: CurrentUser,
    _access: RequireEditor,
) -> CollectionOut:
    col = await doc_service.get_collection(db, collection_id)
    if not col or col.workspace_id != workspace_id:
        raise NotFoundError("Collection not found")
    await doc_service.add_to_collection(
        db,
        collection_id=collection_id,
        document_id=body.document_id,
        added_by=user.id,
    )
    rows = await doc_service.list_collections(db, workspace_id)
    for c, count in rows:
        if c.id == collection_id:
            return CollectionOut(
                id=c.id,
                workspace_id=c.workspace_id,
                name=c.name,
                description=c.description,
                created_at=c.created_at,
                document_count=count,
            )
    raise NotFoundError("Collection not found")


@router.delete("/workspaces/{workspace_id}/collections/{collection_id}/documents/{document_id}")
async def remove_collection_document(
    workspace_id: UUID,
    collection_id: UUID,
    document_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireEditor,
) -> dict:
    col = await doc_service.get_collection(db, collection_id)
    if not col or col.workspace_id != workspace_id:
        raise NotFoundError("Collection not found")
    await doc_service.remove_from_collection(
        db, collection_id=collection_id, document_id=document_id
    )
    return {"ok": True}
