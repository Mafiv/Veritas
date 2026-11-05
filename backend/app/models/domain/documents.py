"""Documents, ingestion, collections, and knowledge-graph models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.domain.base import (
    Base,
    DocumentStatus,
    DocumentType,
    EntityType,
    IngestionJobStage,
    IngestionJobStatus,
    JSONType,
    PermissionScope,
    SoftDeleteMixin,
    TimestampMixin,
    UUID,
    new_uuid,
)

if TYPE_CHECKING:
    from app.models.domain.identity import Workspace


class EmbeddingModel(Base, TimestampMixin):
    """Registry of embedding providers/dimensions — avoids splitting embeddings table."""

    __tablename__ = "embedding_models"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    meta: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)


class Document(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_workspace_created", "workspace_id", "created_at"),
        Index("ix_documents_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    doc_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type"), nullable=False
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"),
        default=DocumentStatus.PENDING,
        index=True,
        nullable=False,
    )
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Deliberate denorm for list views — avoid COUNT(*) on every documents list.
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Legacy columns — normalized into document_summaries / suggested_questions.
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_questions: Mapped[Optional[list]] = mapped_column(JSONType, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    active_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey(
            "document_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_documents_active_version",
        ),
        nullable=True,
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="documents")
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        foreign_keys="DocumentChunk.document_id",
    )
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        foreign_keys="DocumentVersion.document_id",
    )
    summaries: Mapped[list[DocumentSummary]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    questions: Mapped[list[SuggestedQuestion]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    permissions: Mapped[list[DocumentPermission]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    ingestion_jobs: Mapped[list[IngestionJob]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentVersion(Base, TimestampMixin):
    """Re-upload history; exactly one is_active version per document (enforced in app + partial unique)."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),
        Index("ix_document_versions_document_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    change_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)

    document: Mapped[Document] = relationship(back_populates="versions", foreign_keys=[document_id])


class DocumentChunk(Base, TimestampMixin):
    """Semantic chunks. Embedding stays on-row (no document_chunk_embeddings split)."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_workspace_document", "workspace_id", "document_id"),
        UniqueConstraint(
            "document_id", "chunk_index", "document_version_id", name="uq_chunk_index_version"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    heading: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Embedding as JSON for portability; pgvector upgrade is a later migration.
    embedding: Mapped[Optional[list]] = mapped_column(JSONType, nullable=True)
    embedding_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("embedding_models.id", ondelete="SET NULL"), nullable=True, index=True
    )
    meta: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)

    document: Mapped[Document] = relationship(back_populates="chunks", foreign_keys=[document_id])
    embedding_model: Mapped[Optional[EmbeddingModel]] = relationship()


class DocumentSummary(Base, TimestampMixin):
    __tablename__ = "document_summaries"
    __table_args__ = (Index("ix_document_summaries_document_id", "document_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    document_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    summary_type: Mapped[str] = mapped_column(String(40), default="auto", nullable=False)
    model_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    document: Mapped[Document] = relationship(back_populates="summaries")


class SuggestedQuestion(Base, TimestampMixin):
    __tablename__ = "suggested_questions"
    __table_args__ = (Index("ix_suggested_questions_document_id", "document_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    document: Mapped[Document] = relationship(back_populates="questions")


class DocumentPermission(Base, TimestampMixin):
    """Granular page/section ACL beyond workspace role."""

    __tablename__ = "document_permissions"
    __table_args__ = (Index("ix_document_permissions_document_user", "document_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    granted_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    scope: Mapped[PermissionScope] = mapped_column(
        Enum(PermissionScope, name="permission_scope"), nullable=False
    )
    page_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    page_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    section_heading: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    can_read: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_cite: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    document: Mapped[Document] = relationship(back_populates="permissions")


class Collection(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "collections"
    __table_args__ = (Index("ix_collections_workspace_id", "workspace_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    documents: Mapped[list[CollectionDocument]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )


class CollectionDocument(Base, TimestampMixin):
    __tablename__ = "collection_documents"
    __table_args__ = (
        UniqueConstraint("collection_id", "document_id", name="uq_collection_document"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    added_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    collection: Mapped[Collection] = relationship(back_populates="documents")


class Entity(Base, TimestampMixin):
    """Knowledge-graph node extracted from documents."""

    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "normalized_name", "entity_type", name="uq_entity_workspace"
        ),
        Index("ix_entities_workspace_type", "workspace_id", "entity_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(300), nullable=False)
    entity_type: Mapped[EntityType] = mapped_column(
        Enum(EntityType, name="entity_type"), nullable=False
    )
    meta: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)


class DocumentEntity(Base, TimestampMixin):
    """Entity mention linked to a document/chunk with optional offsets."""

    __tablename__ = "document_entities"
    __table_args__ = (
        Index("ix_document_entities_entity_id", "entity_id"),
        Index("ix_document_entities_document_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    mention_text: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    start_offset: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_offset: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class EntityRelationship(Base, TimestampMixin):
    """Graph edge between entities (e.g. worked_with, mentions)."""

    __tablename__ = "entity_relationships"
    __table_args__ = (
        Index("ix_entity_relationships_from", "from_entity_id"),
        Index("ix_entity_relationships_to", "to_entity_id"),
        UniqueConstraint(
            "from_entity_id", "to_entity_id", "relationship_type", name="uq_entity_rel"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    to_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(80), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    evidence_chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True
    )
    meta: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)


class IngestionJob(Base, TimestampMixin):
    """Celery pipeline status for parse→chunk→embed→summarize."""

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        Index("ix_ingestion_jobs_document_status", "document_id", "status"),
        Index("ix_ingestion_jobs_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    document_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    status: Mapped[IngestionJobStatus] = mapped_column(
        Enum(IngestionJobStatus, name="ingestion_job_status"),
        default=IngestionJobStatus.QUEUED,
        nullable=False,
    )
    stage: Mapped[IngestionJobStage] = mapped_column(
        Enum(IngestionJobStage, name="ingestion_job_stage"),
        default=IngestionJobStage.PARSE,
        nullable=False,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)

    document: Mapped[Document] = relationship(back_populates="ingestion_jobs")
