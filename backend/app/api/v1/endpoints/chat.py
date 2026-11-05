"""Chat / RAG query endpoints with SSE streaming."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession, RequireEditor, RequireViewer
from app.api.rate_limit import limit_per_user
from app.core.exceptions import NotFoundError
from app.models.domain import (
    ChatMessage,
    ChatThread,
    FeedbackVote,
    MessageRole,
    User,
    WorkspaceRole,
)
from app.models.schemas import (
    ChatQueryRequest,
    ChatQueryResponse,
    FeedbackRequest,
    MessageOut,
    ThreadCreate,
    ThreadOut,
)
from app.models.schemas.extended import (
    MessageFeedbackCreate,
    MessageFeedbackOut,
    ThreadCommentCreate,
    ThreadCommentOut,
)
from app.services.audit.logger import write_audit
from app.services.billing import service as billing_service
from app.services.chat import service as chat_service
from app.services.documents import service as doc_service
from app.services.llm.orchestrator import RAGOrchestrator
from app.services.monitoring.logger import get_logger

router = APIRouter(tags=["chat"])
log = get_logger("veritas.chat")
rag = RAGOrchestrator()


class ThreadDocumentsUpdate(BaseModel):
    document_ids: list[UUID]


def _thread_out(thread: ChatThread, message_count: int = 0) -> ThreadOut:
    return ThreadOut(
        id=thread.id,
        workspace_id=thread.workspace_id,
        title=thread.title,
        is_shared=thread.is_shared,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        message_count=message_count,
    )


@router.get("/workspaces/{workspace_id}/threads", response_model=list[ThreadOut])
async def list_threads(
    workspace_id: UUID, db: DbSession, user: CurrentUser, _access: RequireViewer
) -> list[ThreadOut]:
    result = await db.execute(
        select(ChatThread)
        .where(ChatThread.workspace_id == workspace_id, ChatThread.deleted_at.is_(None))
        .order_by(ChatThread.updated_at.desc())
    )
    threads = result.scalars().all()
    out: list[ThreadOut] = []
    for t in threads:
        count = (
            await db.execute(
                select(func.count()).select_from(ChatMessage).where(ChatMessage.thread_id == t.id)
            )
        ).scalar_one()
        out.append(_thread_out(t, count))
    return out


@router.post("/workspaces/{workspace_id}/threads", response_model=ThreadOut)
async def create_thread(
    workspace_id: UUID, body: ThreadCreate, db: DbSession, user: CurrentUser, _access: RequireEditor
) -> ThreadOut:
    thread = ChatThread(
        workspace_id=workspace_id,
        created_by=user.id,
        title=body.title or "New conversation",
    )
    db.add(thread)
    await db.flush()
    return _thread_out(thread, 0)


@router.put(
    "/workspaces/{workspace_id}/threads/{thread_id}/documents",
    response_model=list[UUID],
)
async def set_thread_documents(
    workspace_id: UUID,
    thread_id: UUID,
    body: ThreadDocumentsUpdate,
    db: DbSession,
    user: CurrentUser,
    _access: RequireEditor,
) -> list[UUID]:
    thread = (
        await db.execute(
            select(ChatThread).where(
                ChatThread.id == thread_id,
                ChatThread.workspace_id == workspace_id,
                ChatThread.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not thread:
        raise NotFoundError("Thread not found")
    await chat_service.set_thread_documents(db, thread_id=thread_id, document_ids=body.document_ids)
    return body.document_ids


@router.get(
    "/workspaces/{workspace_id}/threads/{thread_id}/messages",
    response_model=list[MessageOut],
)
async def list_messages(
    workspace_id: UUID, thread_id: UUID, db: DbSession, user: CurrentUser, _access: RequireViewer
) -> list[ChatMessage]:
    thread = (
        await db.execute(
            select(ChatThread).where(
                ChatThread.id == thread_id, ChatThread.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()
    if not thread:
        raise NotFoundError("Thread not found")
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return list(result.scalars().all())


@router.get(
    "/workspaces/{workspace_id}/threads/{thread_id}/comments",
    response_model=list[ThreadCommentOut],
)
async def list_comments(
    workspace_id: UUID,
    thread_id: UUID,
    db: DbSession,
    user: CurrentUser,
    _access: RequireViewer,
) -> list[ThreadCommentOut]:
    thread = (
        await db.execute(
            select(ChatThread).where(
                ChatThread.id == thread_id, ChatThread.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()
    if not thread:
        raise NotFoundError("Thread not found")
    rows = await chat_service.list_thread_comments(db, thread_id)
    return [ThreadCommentOut.model_validate(r) for r in rows]


@router.post(
    "/workspaces/{workspace_id}/threads/{thread_id}/comments",
    response_model=ThreadCommentOut,
)
async def create_comment(
    workspace_id: UUID,
    thread_id: UUID,
    body: ThreadCommentCreate,
    db: DbSession,
    user: CurrentUser,
    _access: RequireViewer,
) -> ThreadCommentOut:
    thread = (
        await db.execute(
            select(ChatThread).where(
                ChatThread.id == thread_id, ChatThread.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()
    if not thread:
        raise NotFoundError("Thread not found")
    row = await chat_service.add_thread_comment(
        db,
        thread_id=thread_id,
        user_id=user.id,
        body=body.body,
        parent_comment_id=body.parent_comment_id,
    )
    return ThreadCommentOut.model_validate(row)


async def _resolve_document_scope(
    db: DbSession,
    *,
    workspace_id: UUID,
    user: User,
    role: WorkspaceRole,
    thread_id: UUID | None,
    document_ids: list[UUID] | None,
) -> list[UUID] | None:
    scoped = document_ids
    if thread_id and not scoped:
        scoped = await chat_service.get_thread_document_ids(db, thread_id) or None
    return await doc_service.readable_document_ids(
        db,
        workspace_id=workspace_id,
        user_id=user.id,
        role=role,
        document_ids=scoped,
    )


@router.post(
    "/workspaces/{workspace_id}/chat",
    response_model=ChatQueryResponse,
    dependencies=[limit_per_user("chat", "rate_limit_chat_per_minute")],
)
async def chat_query(
    workspace_id: UUID,
    body: ChatQueryRequest,
    db: DbSession,
    user: CurrentUser,
    access: RequireEditor,
) -> ChatQueryResponse:
    await billing_service.check_query_quota_metered(db, user=user, workspace_id=workspace_id)
    _, member = access

    thread = await _get_or_create_thread(db, workspace_id, user.id, body.thread_id, body.question)
    history = await _load_history(db, thread.id)
    doc_ids = await _resolve_document_scope(
        db,
        workspace_id=workspace_id,
        user=user,
        role=member.role,
        thread_id=thread.id,
        document_ids=body.document_ids,
    )

    user_msg = ChatMessage(thread_id=thread.id, role=MessageRole.USER, content=body.question)
    db.add(user_msg)
    await db.flush()

    result = await rag.answer(
        db,
        workspace_id=workspace_id,
        question=body.question,
        document_ids=doc_ids,
        history=history,
        use_hyde=body.use_hyde,
        use_rerank=body.use_rerank,
    )

    assistant = ChatMessage(
        thread_id=thread.id,
        role=MessageRole.ASSISTANT,
        content=result.answer,
        citations=[c.model_dump(mode="json") for c in result.citations],
        latency_ms=result.latency_ms,
        token_usage={
            "retrieved": result.retrieved_count,
            "status": "complete",
            "abstained": result.abstained,
            "trace": result.trace.as_dict(),
        },
    )
    db.add(assistant)
    await db.flush()
    await chat_service.persist_citations(db, message_id=assistant.id, citations=result.citations)

    user.queries_today = (user.queries_today or 0) + 1
    await billing_service.record_usage(
        db,
        user_id=user.id,
        workspace_id=workspace_id,
        event_type="query",
        quantity=1,
        meta={"latency_ms": result.latency_ms},
        meter_key="query",
    )
    await write_audit(
        db,
        action="chat.query",
        resource_type="thread",
        resource_id=thread.id,
        user_id=user.id,
        workspace_id=workspace_id,
        details={"question_len": len(body.question)},
    )

    if thread.title == "New conversation":
        thread.title = body.question[:80]

    await db.flush()
    await db.refresh(assistant)

    return ChatQueryResponse(
        thread_id=thread.id,
        message=MessageOut.model_validate(assistant),
        citations=result.citations,
    )


@router.post(
    "/workspaces/{workspace_id}/chat/stream",
    dependencies=[limit_per_user("chat", "rate_limit_chat_per_minute")],
)
async def chat_stream(
    workspace_id: UUID,
    body: ChatQueryRequest,
    db: DbSession,
    user: CurrentUser,
    access: RequireEditor,
) -> StreamingResponse:
    await billing_service.check_query_quota_metered(db, user=user, workspace_id=workspace_id)
    _, member = access

    thread = await _get_or_create_thread(db, workspace_id, user.id, body.thread_id, body.question)
    history = await _load_history(db, thread.id)
    doc_ids = await _resolve_document_scope(
        db,
        workspace_id=workspace_id,
        user=user,
        role=member.role,
        thread_id=thread.id,
        document_ids=body.document_ids,
    )

    user_msg = ChatMessage(thread_id=thread.id, role=MessageRole.USER, content=body.question)
    db.add(user_msg)
    await db.flush()
    await db.commit()

    thread_id = thread.id
    user_id = user.id

    async def event_generator() -> AsyncIterator[str]:
        from app.db.session import AsyncSessionLocal

        answer = ""
        citations_payload: list = []
        done: dict = {}
        status = "complete"

        yield _sse("thread", {"thread_id": str(thread_id)})

        async with AsyncSessionLocal() as session:
            try:
                async for event in rag.stream_answer(
                    session,
                    workspace_id=workspace_id,
                    question=body.question,
                    document_ids=doc_ids,
                    history=history,
                    use_hyde=body.use_hyde,
                    use_rerank=body.use_rerank,
                ):
                    if event["event"] == "token":
                        answer += event["data"]["token"]
                    elif event["event"] == "done":
                        done = event["data"]
                        answer = done["answer"]
                        citations_payload = done["citations"]
                    yield _sse(event["event"], event["data"])
            except (asyncio.CancelledError, GeneratorExit):
                # Client disconnected / stream closed: keep what was generated, then
                # stop. Yielding is not allowed from here on.
                status = "interrupted"
                raise
            except Exception as exc:  # noqa: BLE001 - surface to the client, never hang
                status = "error"
                log.error("chat.stream_failed", thread_id=str(thread_id), error=str(exc))
                await session.rollback()
                yield _sse(
                    "error",
                    {
                        "message": "The answer could not be completed. Please try again.",
                        "partial": bool(answer),
                    },
                )
            finally:
                if answer or status == "complete":
                    message_id = await asyncio.shield(
                        _persist_stream_result(
                            session,
                            thread_id=thread_id,
                            user_id=user_id,
                            workspace_id=workspace_id,
                            question=body.question,
                            answer=answer,
                            citations=citations_payload,
                            done=done,
                            status=status,
                        )
                    )
                    if status != "interrupted":
                        yield _sse(
                            "message",
                            {"message_id": str(message_id), "thread_id": str(thread_id)},
                        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/workspaces/{workspace_id}/threads/{thread_id}/messages/{message_id}/feedback",
    response_model=MessageOut,
)
async def message_feedback(
    workspace_id: UUID,
    thread_id: UUID,
    message_id: UUID,
    body: FeedbackRequest,
    db: DbSession,
    user: CurrentUser,
    _access: RequireViewer,
) -> ChatMessage:
    msg = (
        await db.execute(
            select(ChatMessage).where(
                ChatMessage.id == message_id, ChatMessage.thread_id == thread_id
            )
        )
    ).scalar_one_or_none()
    if not msg:
        raise NotFoundError("Message not found")
    msg.feedback = body.feedback
    await chat_service.upsert_feedback(
        db,
        message_id=message_id,
        user_id=user.id,
        vote=FeedbackVote(body.feedback),
    )
    await db.flush()
    return msg


@router.post(
    "/workspaces/{workspace_id}/threads/{thread_id}/messages/{message_id}/feedback/v2",
    response_model=MessageFeedbackOut,
)
async def message_feedback_v2(
    workspace_id: UUID,
    thread_id: UUID,
    message_id: UUID,
    body: MessageFeedbackCreate,
    db: DbSession,
    user: CurrentUser,
    _access: RequireViewer,
) -> MessageFeedbackOut:
    msg = (
        await db.execute(
            select(ChatMessage).where(
                ChatMessage.id == message_id, ChatMessage.thread_id == thread_id
            )
        )
    ).scalar_one_or_none()
    if not msg:
        raise NotFoundError("Message not found")
    msg.feedback = body.vote.value
    row = await chat_service.upsert_feedback(
        db,
        message_id=message_id,
        user_id=user.id,
        vote=body.vote,
        comment=body.comment,
    )
    return MessageFeedbackOut.model_validate(row)


async def _get_or_create_thread(
    db: DbSession,
    workspace_id: UUID,
    user_id: UUID,
    thread_id: UUID | None,
    question: str,
) -> ChatThread:
    if thread_id:
        thread = (
            await db.execute(
                select(ChatThread).where(
                    ChatThread.id == thread_id, ChatThread.workspace_id == workspace_id
                )
            )
        ).scalar_one_or_none()
        if not thread:
            raise NotFoundError("Thread not found")
        return thread
    thread = ChatThread(
        workspace_id=workspace_id,
        created_by=user_id,
        title=question[:80] or "New conversation",
    )
    db.add(thread)
    await db.flush()
    return thread


async def _load_history(db: DbSession, thread_id: UUID) -> list[tuple[str, str]]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(12)
    )
    messages = list(reversed(result.scalars().all()))
    return [(m.role.value if hasattr(m.role, "value") else m.role, m.content) for m in messages]


async def _persist_stream_result(
    session: AsyncSession,
    *,
    thread_id: UUID,
    user_id: UUID,
    workspace_id: UUID,
    question: str,
    answer: str,
    citations: list,
    done: dict,
    status: str,
) -> UUID:
    """Save the assistant turn (complete or partial) and meter completed queries."""
    assistant = ChatMessage(
        thread_id=thread_id,
        role=MessageRole.ASSISTANT,
        content=answer,
        citations=citations,
        latency_ms=done.get("latency_ms"),
        token_usage={
            "retrieved": done.get("retrieved_count", 0),
            "status": status,
            "abstained": done.get("abstained", False),
            "trace": done.get("trace"),
        },
    )
    session.add(assistant)
    await session.flush()
    await chat_service.persist_citations(session, message_id=assistant.id, citations=citations)

    if status == "complete":
        u = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
        u.queries_today = (u.queries_today or 0) + 1
        await billing_service.record_usage(
            session,
            user_id=user_id,
            workspace_id=workspace_id,
            event_type="query",
            quantity=1,
            meta={"latency_ms": done.get("latency_ms"), "stream": True},
            meter_key="query",
        )
    t = (await session.execute(select(ChatThread).where(ChatThread.id == thread_id))).scalar_one()
    if t.title == "New conversation":
        t.title = question[:80]
    await session.commit()
    return assistant.id


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
