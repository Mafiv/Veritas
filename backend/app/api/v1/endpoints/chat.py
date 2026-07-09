"""Chat / RAG query endpoints with SSE streaming."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, check_query_quota
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.domain import (
    AuditLog,
    MessageRole,
    ChatMessage,
    ChatThread,
    UsageEvent,
    User,
    WorkspaceMember,
)
from app.models.schemas import (
    ChatQueryRequest,
    ChatQueryResponse,
    FeedbackRequest,
    MessageOut,
    ThreadCreate,
    ThreadOut,
)
from app.services.llm.orchestrator import RAGOrchestrator

router = APIRouter(tags=["chat"])
rag = RAGOrchestrator()


async def _require_member(db: DbSession, workspace_id: UUID, user_id: UUID) -> None:
    mem = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    if not mem.scalar_one_or_none():
        raise ForbiddenError("No access to this workspace")


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
    workspace_id: UUID, db: DbSession, user: CurrentUser
) -> list[ThreadOut]:
    await _require_member(db, workspace_id, user.id)
    result = await db.execute(
        select(ChatThread)
        .where(ChatThread.workspace_id == workspace_id)
        .order_by(ChatThread.updated_at.desc())
    )
    threads = result.scalars().all()
    out: list[ThreadOut] = []
    for t in threads:
        count = (
            await db.execute(
                select(func.count())
                .select_from(ChatMessage)
                .where(ChatMessage.thread_id == t.id)
            )
        ).scalar_one()
        out.append(_thread_out(t, count))
    return out


@router.post("/workspaces/{workspace_id}/threads", response_model=ThreadOut)
async def create_thread(
    workspace_id: UUID, body: ThreadCreate, db: DbSession, user: CurrentUser
) -> ThreadOut:
    await _require_member(db, workspace_id, user.id)
    thread = ChatThread(
        workspace_id=workspace_id,
        created_by=user.id,
        title=body.title or "New conversation",
    )
    db.add(thread)
    await db.flush()
    return _thread_out(thread, 0)


@router.get(
    "/workspaces/{workspace_id}/threads/{thread_id}/messages",
    response_model=list[MessageOut],
)
async def list_messages(
    workspace_id: UUID, thread_id: UUID, db: DbSession, user: CurrentUser
) -> list[ChatMessage]:
    await _require_member(db, workspace_id, user.id)
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


@router.post("/workspaces/{workspace_id}/chat", response_model=ChatQueryResponse)
async def chat_query(
    workspace_id: UUID, body: ChatQueryRequest, db: DbSession, user: CurrentUser
) -> ChatQueryResponse:
    await _require_member(db, workspace_id, user.id)
    await check_query_quota(user, db)

    thread = await _get_or_create_thread(db, workspace_id, user.id, body.thread_id, body.question)
    history = await _load_history(db, thread.id)

    user_msg = ChatMessage(thread_id=thread.id, role=MessageRole.USER, content=body.question)
    db.add(user_msg)
    await db.flush()

    result = await rag.answer(
        db,
        workspace_id=workspace_id,
        question=body.question,
        document_ids=body.document_ids,
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
        token_usage={"retrieved": result.retrieved_count},
    )
    db.add(assistant)

    user.queries_today = (user.queries_today or 0) + 1
    db.add(
        UsageEvent(
            user_id=user.id,
            workspace_id=workspace_id,
            event_type="query",
            quantity=1,
            meta={"latency_ms": result.latency_ms},
        )
    )
    db.add(
        AuditLog(
            user_id=user.id,
            workspace_id=workspace_id,
            action="chat.query",
            resource_type="thread",
            resource_id=str(thread.id),
            details={"question_len": len(body.question)},
        )
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


@router.post("/workspaces/{workspace_id}/chat/stream")
async def chat_stream(
    workspace_id: UUID, body: ChatQueryRequest, db: DbSession, user: CurrentUser
) -> StreamingResponse:
    await _require_member(db, workspace_id, user.id)
    await check_query_quota(user, db)

    thread = await _get_or_create_thread(db, workspace_id, user.id, body.thread_id, body.question)
    history = await _load_history(db, thread.id)

    user_msg = ChatMessage(thread_id=thread.id, role=MessageRole.USER, content=body.question)
    db.add(user_msg)
    await db.flush()
    # Commit early so stream generator can open a fresh session if needed
    await db.commit()

    thread_id = thread.id
    user_id = user.id

    async def event_generator():
        from app.db.session import AsyncSessionLocal

        full_answer = ""
        citations_payload: list = []
        latency_ms = 0.0
        retrieved = 0

        yield _sse("thread", {"thread_id": str(thread_id)})

        async with AsyncSessionLocal() as session:
            async for event in rag.stream_answer(
                session,
                workspace_id=workspace_id,
                question=body.question,
                document_ids=body.document_ids,
                history=history,
                use_hyde=body.use_hyde,
                use_rerank=body.use_rerank,
            ):
                if event["event"] == "citations":
                    citations_payload = event["data"]["citations"]
                elif event["event"] == "token":
                    full_answer += event["data"]["token"]
                elif event["event"] == "done":
                    full_answer = event["data"]["answer"]
                    citations_payload = event["data"]["citations"]
                    latency_ms = event["data"]["latency_ms"]
                    retrieved = event["data"]["retrieved_count"]
                yield _sse(event["event"], event["data"])

            assistant = ChatMessage(
                thread_id=thread_id,
                role=MessageRole.ASSISTANT,
                content=full_answer,
                citations=citations_payload,
                latency_ms=latency_ms,
                token_usage={"retrieved": retrieved},
            )
            session.add(assistant)

            u = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
            u.queries_today = (u.queries_today or 0) + 1
            session.add(
                UsageEvent(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    event_type="query",
                    quantity=1,
                    meta={"latency_ms": latency_ms, "stream": True},
                )
            )
            t = (
                await session.execute(select(ChatThread).where(ChatThread.id == thread_id))
            ).scalar_one()
            if t.title == "New conversation":
                t.title = body.question[:80]
            await session.commit()
            yield _sse(
                "message",
                {
                    "message_id": str(assistant.id),
                    "thread_id": str(thread_id),
                },
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
) -> ChatMessage:
    await _require_member(db, workspace_id, user.id)
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
    await db.flush()
    return msg


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


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
