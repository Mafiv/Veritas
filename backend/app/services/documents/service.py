"""Document versions, permissions, collections, and entity helpers."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.domain import (
    Collection,
    CollectionDocument,
    Document,
    DocumentEntity,
    DocumentPermission,
    DocumentVersion,
    Entity,
    PermissionScope,
    SuggestedQuestion,
    WorkspaceRole,
)


async def list_versions(db: AsyncSession, document_id: UUID) -> list[DocumentVersion]:
    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
    )
    return list(result.scalars().all())


async def list_suggested_questions(db: AsyncSession, document_id: UUID) -> list[SuggestedQuestion]:
    result = await db.execute(
        select(SuggestedQuestion)
        .where(SuggestedQuestion.document_id == document_id)
        .order_by(SuggestedQuestion.rank.asc())
    )
    return list(result.scalars().all())


async def list_document_entities(db: AsyncSession, document_id: UUID) -> list[Entity]:
    result = await db.execute(
        select(Entity)
        .join(DocumentEntity, DocumentEntity.entity_id == Entity.id)
        .where(DocumentEntity.document_id == document_id)
        .order_by(Entity.name.asc())
    )
    return list(result.scalars().unique().all())


async def grant_permission(
    db: AsyncSession,
    *,
    document_id: UUID,
    user_id: UUID,
    granted_by: UUID,
    scope: str | PermissionScope = PermissionScope.DOCUMENT,
    page_start: int | None = None,
    page_end: int | None = None,
    section_heading: str | None = None,
    can_read: bool = True,
    can_cite: bool = True,
) -> DocumentPermission:
    if isinstance(scope, str):
        scope = PermissionScope(scope)
    row = DocumentPermission(
        document_id=document_id,
        user_id=user_id,
        granted_by=granted_by,
        scope=scope,
        page_start=page_start,
        page_end=page_end,
        section_heading=section_heading,
        can_read=can_read,
        can_cite=can_cite,
    )
    db.add(row)
    await db.flush()
    return row


async def list_permissions(db: AsyncSession, document_id: UUID) -> list[DocumentPermission]:
    result = await db.execute(
        select(DocumentPermission).where(DocumentPermission.document_id == document_id)
    )
    return list(result.scalars().all())


async def revoke_permission(db: AsyncSession, *, document_id: UUID, permission_id: UUID) -> None:
    row = await db.get(DocumentPermission, permission_id)
    if not row or row.document_id != document_id:
        raise NotFoundError("Permission not found")
    await db.delete(row)
    await db.flush()


async def readable_document_ids(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    role: WorkspaceRole,
    document_ids: list[UUID] | None = None,
) -> list[UUID] | None:
    """
    Return document IDs the user may read, or None if all workspace docs are allowed.

    When any DocumentPermission rows exist for a document, only listed users may read it
    (owners/editors still see everything).
    """
    if role in (WorkspaceRole.OWNER, WorkspaceRole.EDITOR):
        return document_ids

    # Viewer: exclude docs that have ACL rows the user is not on
    restricted = (
        (
            await db.execute(
                select(DocumentPermission.document_id)
                .join(Document, Document.id == DocumentPermission.document_id)
                .where(Document.workspace_id == workspace_id, Document.deleted_at.is_(None))
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    if not restricted:
        return document_ids

    allowed_restricted = (
        (
            await db.execute(
                select(DocumentPermission.document_id).where(
                    DocumentPermission.document_id.in_(list(restricted)),
                    DocumentPermission.user_id == user_id,
                    DocumentPermission.can_read.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    blocked = set(restricted) - set(allowed_restricted)

    base_q = select(Document.id).where(
        Document.workspace_id == workspace_id,
        Document.deleted_at.is_(None),
    )
    if document_ids:
        base_q = base_q.where(Document.id.in_(document_ids))
    all_ids = list((await db.execute(base_q)).scalars().all())
    return [d for d in all_ids if d not in blocked]


async def create_collection(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    created_by: UUID,
    name: str,
    description: str | None = None,
    document_ids: list[UUID] | None = None,
) -> Collection:
    col = Collection(
        workspace_id=workspace_id,
        created_by=created_by,
        name=name,
        description=description,
    )
    db.add(col)
    await db.flush()
    for doc_id in document_ids or []:
        db.add(
            CollectionDocument(
                collection_id=col.id,
                document_id=doc_id,
                added_by=created_by,
            )
        )
    await db.flush()
    return col


async def list_collections(db: AsyncSession, workspace_id: UUID) -> list[tuple[Collection, int]]:
    result = await db.execute(
        select(Collection, func.count(CollectionDocument.id))
        .outerjoin(CollectionDocument, CollectionDocument.collection_id == Collection.id)
        .where(Collection.workspace_id == workspace_id, Collection.deleted_at.is_(None))
        .group_by(Collection.id)
        .order_by(Collection.created_at.desc())
    )
    return [(row[0], int(row[1] or 0)) for row in result.all()]


async def add_to_collection(
    db: AsyncSession,
    *,
    collection_id: UUID,
    document_id: UUID,
    added_by: UUID,
) -> CollectionDocument:
    existing = (
        await db.execute(
            select(CollectionDocument).where(
                CollectionDocument.collection_id == collection_id,
                CollectionDocument.document_id == document_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    row = CollectionDocument(
        collection_id=collection_id,
        document_id=document_id,
        added_by=added_by,
    )
    db.add(row)
    await db.flush()
    return row


async def remove_from_collection(
    db: AsyncSession, *, collection_id: UUID, document_id: UUID
) -> None:
    row = (
        await db.execute(
            select(CollectionDocument).where(
                CollectionDocument.collection_id == collection_id,
                CollectionDocument.document_id == document_id,
            )
        )
    ).scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.flush()


async def get_collection(db: AsyncSession, collection_id: UUID) -> Collection | None:
    return (
        await db.execute(
            select(Collection).where(
                Collection.id == collection_id, Collection.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
