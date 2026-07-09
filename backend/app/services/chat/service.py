"""Chat citations, feedback, comments, and thread document scope."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.domain import (
    ChatThreadDocument,
    FeedbackVote,
    MessageCitation,
    MessageFeedback,
    ThreadComment,
)
from app.models.schemas import Citation


async def persist_citations(
    db: AsyncSession,
    *,
    message_id: UUID,
    citations: list[Citation] | list[dict],
) -> list[MessageCitation]:
    rows: list[MessageCitation] = []
    for i, c in enumerate(citations):
        if hasattr(c, "model_dump"):
            data = c.model_dump(mode="json")
        else:
            data = c
        chunk_id = data.get("chunk_id")
        document_id = data.get("document_id")
        if not chunk_id or not document_id:
            continue
        row = MessageCitation(
            message_id=message_id,
            chunk_id=UUID(str(chunk_id)),
            document_id=UUID(str(document_id)),
            citation_index=int(data.get("citation_index") or i + 1),
            snippet=str(data.get("snippet") or "")[:4000],
            score=float(data.get("score") or 0.0),
            page_number=data.get("page_number"),
            heading=data.get("heading"),
        )
        db.add(row)
        rows.append(row)
    await db.flush()
    return rows


async def upsert_feedback(
    db: AsyncSession,
    *,
    message_id: UUID,
    user_id: UUID,
    vote: FeedbackVote | str,
    comment: str | None = None,
) -> MessageFeedback:
    if isinstance(vote, str):
        # Accept legacy "up"/"down" or thumbs aliases
        normalized = vote.lower().replace("thumbs_", "")
        vote = FeedbackVote(normalized)
    existing = (
        await db.execute(
            select(MessageFeedback).where(
                MessageFeedback.message_id == message_id,
                MessageFeedback.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.vote = vote
        existing.comment = comment
        await db.flush()
        return existing
    row = MessageFeedback(
        message_id=message_id,
        user_id=user_id,
        vote=vote,
        comment=comment,
    )
    db.add(row)
    await db.flush()
    return row


async def add_thread_comment(
    db: AsyncSession,
    *,
    thread_id: UUID,
    user_id: UUID,
    body: str,
    parent_comment_id: UUID | None = None,
) -> ThreadComment:
    row = ThreadComment(
        thread_id=thread_id,
        user_id=user_id,
        body=body,
        parent_comment_id=parent_comment_id,
    )
    db.add(row)
    await db.flush()
    return row


async def list_thread_comments(
    db: AsyncSession, thread_id: UUID
) -> list[ThreadComment]:
    result = await db.execute(
        select(ThreadComment)
        .where(ThreadComment.thread_id == thread_id)
        .order_by(ThreadComment.created_at.asc())
    )
    return list(result.scalars().all())


async def set_thread_documents(
    db: AsyncSession,
    *,
    thread_id: UUID,
    document_ids: list[UUID],
) -> list[ChatThreadDocument]:
    existing = (
        await db.execute(
            select(ChatThreadDocument).where(ChatThreadDocument.thread_id == thread_id)
        )
    ).scalars().all()
    for row in existing:
        await db.delete(row)
    await db.flush()
    rows: list[ChatThreadDocument] = []
    for doc_id in document_ids:
        row = ChatThreadDocument(thread_id=thread_id, document_id=doc_id)
        db.add(row)
        rows.append(row)
    await db.flush()
    return rows


async def get_thread_document_ids(db: AsyncSession, thread_id: UUID) -> list[UUID]:
    result = await db.execute(
        select(ChatThreadDocument.document_id).where(
            ChatThreadDocument.thread_id == thread_id
        )
    )
    return list(result.scalars().all())


async def get_feedback(
    db: AsyncSession, *, message_id: UUID, user_id: UUID
) -> MessageFeedback | None:
    return (
        await db.execute(
            select(MessageFeedback).where(
                MessageFeedback.message_id == message_id,
                MessageFeedback.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
