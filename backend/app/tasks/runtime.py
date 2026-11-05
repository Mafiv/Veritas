"""Async runtime for Celery tasks.

Each task runs its coroutine with ``asyncio.run`` (a fresh event loop) and a
``NullPool`` engine. asyncpg connections are bound to the loop that created
them, so reusing the API's pooled engine across task loops fails
intermittently ("attached to a different loop").
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


@asynccontextmanager
async def worker_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            yield session
    finally:
        await engine.dispose()
