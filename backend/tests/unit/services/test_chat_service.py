"""Unit tests for chat citation/feedback helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.domain import FeedbackVote
from app.models.schemas import Citation
from app.services.chat import service as chat_service


@pytest.mark.asyncio
async def test_persist_citations():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    citations = [
        Citation(
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_name="a.pdf",
            snippet="hello",
            score=0.9,
            citation_index=1,
        )
    ]
    rows = await chat_service.persist_citations(
        db, message_id=uuid4(), citations=citations
    )
    assert len(rows) == 1
    assert rows[0].snippet == "hello"
    db.add.assert_called()


@pytest.mark.asyncio
async def test_upsert_feedback_create():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    empty = MagicMock()
    empty.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=empty)

    row = await chat_service.upsert_feedback(
        db,
        message_id=uuid4(),
        user_id=uuid4(),
        vote="up",
        comment="good",
    )
    assert row.vote == FeedbackVote.UP
    assert row.comment == "good"
    db.add.assert_called_once()
