"""Chat, citations, feedback, and shared-thread discussion models."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
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
    enum_values,
    Base,
    FeedbackVote,
    JSONType,
    MessageRole,
    SoftDeleteMixin,
    TimestampMixin,
    UUID,
    new_uuid,
)

if TYPE_CHECKING:
    from app.models.domain.identity import Workspace


class ChatThread(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "chat_threads"
    __table_args__ = (
        Index("ix_chat_threads_workspace_created", "workspace_id", "created_at"),
        Index("ix_chat_threads_workspace_updated", "workspace_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), default="New conversation", nullable=False)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    workspace: Mapped["Workspace"] = relationship(back_populates="threads")
    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )
    scoped_documents: Mapped[list[ChatThreadDocument]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )
    comments: Mapped[list[ThreadComment]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )


class ChatThreadDocument(Base, TimestampMixin):
    """Optional retrieval scope: which documents a thread may search."""

    __tablename__ = "chat_thread_documents"
    __table_args__ = (UniqueConstraint("thread_id", "document_id", name="uq_thread_document"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    thread: Mapped[ChatThread] = relationship(back_populates="scoped_documents")


class ChatMessage(Base, TimestampMixin):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_thread_created", "thread_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, values_callable=enum_values, name="message_role"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Legacy JSON blob — normalized into message_citations / message_feedback.
    citations: Mapped[Optional[list]] = mapped_column(JSONType, nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    token_usage: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    thread: Mapped[ChatThread] = relationship(back_populates="messages")
    citation_rows: Mapped[list[MessageCitation]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )
    feedback_rows: Mapped[list[MessageFeedback]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class MessageCitation(Base, TimestampMixin):
    """Queryable evidence links: which chunks backed which assistant message."""

    __tablename__ = "message_citations"
    __table_args__ = (
        Index("ix_message_citations_message_id", "message_id"),
        Index("ix_message_citations_chunk_id", "chunk_id"),
        UniqueConstraint("message_id", "citation_index", name="uq_message_citation_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="RESTRICT"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    citation_index: Mapped[int] = mapped_column(Integer, nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    heading: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    message: Mapped[ChatMessage] = relationship(back_populates="citation_rows")


class MessageFeedback(Base, TimestampMixin):
    """Thumbs + optional comment for retrieval/reranker tuning signals."""

    __tablename__ = "message_feedback"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_feedback_user"),
        Index("ix_message_feedback_message_id", "message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vote: Mapped[FeedbackVote] = mapped_column(
        Enum(FeedbackVote, values_callable=enum_values, name="feedback_vote"), nullable=False
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    message: Mapped[ChatMessage] = relationship(back_populates="feedback_rows")


class ThreadComment(Base, TimestampMixin):
    """Team discussion on shared research threads."""

    __tablename__ = "thread_comments"
    __table_args__ = (Index("ix_thread_comments_thread_created", "thread_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_comment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("thread_comments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)

    thread: Mapped[ChatThread] = relationship(back_populates="comments")
