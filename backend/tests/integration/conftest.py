"""Integration fixtures: a real, migrated Postgres + pgvector database.

Set TEST_DATABASE_URL (asyncpg URL) to a database that has been migrated with
`alembic upgrade head`. Each test runs inside a transaction that is rolled back.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
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
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
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
