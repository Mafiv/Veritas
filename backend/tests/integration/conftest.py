"""Integration fixtures: a real, migrated Postgres + pgvector database.

Set TEST_DATABASE_URL (asyncpg URL) to a database that has been migrated with
`alembic upgrade head`. Each test runs inside a transaction that is rolled back.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.domain import Document, DocumentStatus, DocumentType, User, Workspace

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
    await engine.dispose()


async def make_workspace(db: AsyncSession) -> tuple[User, Workspace]:
    suffix = uuid.uuid4().hex[:8]
    user = User(email=f"user-{suffix}@example.com", full_name="Test User")
    db.add(user)
    await db.flush()
    ws = Workspace(name=f"WS {suffix}", slug=f"ws-{suffix}", owner_id=user.id)
    db.add(ws)
    await db.flush()
    return user, ws


async def make_document(db: AsyncSession, user: User, ws: Workspace, name: str) -> Document:
    doc = Document(
        workspace_id=ws.id,
        uploaded_by=user.id,
        filename=name,
        original_filename=name,
        content_type="text/plain",
        doc_type=DocumentType.TEXT,
        status=DocumentStatus.READY,
        storage_path=f"/tmp/{name}",
    )
    db.add(doc)
    await db.flush()
    return doc


@pytest.fixture
async def api(db: AsyncSession):
    """HTTP client against the real app, sharing the test transaction.

    Authentication is replaced by a header-selected user so tests can act as
    different people; everything else (roles, quotas, retrieval) is real.
    """
    from httpx import ASGITransport, AsyncClient

    from app.api.deps import get_current_user
    from app.core.exceptions import UnauthorizedError
    from app.db.session import get_db
    from app.main import app

    async def _db() -> AsyncIterator[AsyncSession]:
        yield db
        await db.flush()

    async def _user(request: Request) -> User:
        user_id = request.headers.get("x-test-user")
        if not user_id:
            raise UnauthorizedError("Missing authentication token")
        user = await db.get(User, uuid.UUID(user_id))
        assert user is not None
        return user

    class _SameSession:
        """Stand-in for AsyncSessionLocal() used by the SSE generator."""

        async def __aenter__(self) -> AsyncSession:
            return db

        async def __aexit__(self, *_: object) -> None:
            await db.flush()

    import app.db.session as session_module

    original_factory = session_module.AsyncSessionLocal
    session_module.AsyncSessionLocal = lambda: _SameSession()  # type: ignore[assignment]
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    session_module.AsyncSessionLocal = original_factory


async def add_member(db: AsyncSession, ws: Workspace, user: User, role: str = "owner") -> None:
    from app.models.domain import WorkspaceMember, WorkspaceRole

    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=WorkspaceRole(role)))
    await db.flush()
