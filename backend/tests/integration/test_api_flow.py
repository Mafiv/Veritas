"""End-to-end through HTTP on real Postgres: upload → ingest → ask → cited answer."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import DocumentChunk

from .conftest import add_member, make_workspace

HANDBOOK = b"""# Leave policy

Employees receive 25 days of paid annual leave per calendar year.
Unused leave can be carried over until the end of March.

# Expenses

Travel expenses must be submitted within 30 days with receipts attached.
"""


def _as(user) -> dict[str, str]:  # noqa: ANN001
    return {"x-test-user": str(user.id)}


async def test_upload_ingest_and_ask(api: AsyncClient, db: AsyncSession) -> None:
    user, ws = await make_workspace(db)
    await add_member(db, ws, user, "owner")

    resp = await api.post(
        f"/api/v1/workspaces/{ws.id}/documents",
        files={"file": ("handbook.md", HANDBOOK, "text/markdown")},
        headers=_as(user),
    )
    assert resp.status_code == 202, resp.text
    doc = resp.json()
    assert doc["status"] == "ready"  # INGEST_INLINE=true in tests

    chunks = (
        await db.execute(
            select(func.count(), func.count(DocumentChunk.embedding)).where(
                DocumentChunk.document_id == doc["id"]
            )
        )
    ).one()
    assert chunks[0] > 0 and chunks[0] == chunks[1], "every chunk must be embedded"

    resp = await api.post(
        f"/api/v1/workspaces/{ws.id}/chat",
        json={"question": "How many days of paid annual leave do employees get?"},
        headers=_as(user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    message = body["message"]
    assert message["content"]
    assert body["citations"], "answer must cite at least one source"
    assert all(c["document_name"] == "handbook.md" for c in body["citations"])


async def test_stream_emits_trace_and_persists_message(api: AsyncClient, db: AsyncSession) -> None:
    user, ws = await make_workspace(db)
    await add_member(db, ws, user, "owner")
    await api.post(
        f"/api/v1/workspaces/{ws.id}/documents",
        files={"file": ("handbook.md", HANDBOOK, "text/markdown")},
        headers=_as(user),
    )
    async with api.stream(
        "POST",
        f"/api/v1/workspaces/{ws.id}/chat/stream",
        json={"question": "When must travel expenses be submitted?"},
        headers=_as(user),
    ) as resp:
        assert resp.status_code == 200
        raw = "".join([chunk async for chunk in resp.aiter_text()])
    events = [
        line.removeprefix("event: ") for line in raw.splitlines() if line.startswith("event:")
    ]
    assert events[0] == "thread" and "citations" in events and "done" in events
    assert events[-1] == "message" and "error" not in events


async def test_rejects_spoofed_and_oversized_uploads(api: AsyncClient, db: AsyncSession) -> None:
    user, ws = await make_workspace(db)
    await add_member(db, ws, user, "owner")
    url = f"/api/v1/workspaces/{ws.id}/documents"

    fake_pdf = await api.post(
        url, files={"file": ("report.pdf", b"MZ\x90\x00exe", "application/pdf")}, headers=_as(user)
    )
    assert fake_pdf.status_code == 415

    from app.core.config import get_settings

    too_big = b"a" * (get_settings().max_upload_mb * 1024 * 1024 + 1)
    big = await api.post(url, files={"file": ("big.txt", too_big, "text/plain")}, headers=_as(user))
    assert big.status_code == 413


async def test_viewer_cannot_upload_and_outsider_cannot_read(
    api: AsyncClient, db: AsyncSession
) -> None:
    owner, ws = await make_workspace(db)
    await add_member(db, ws, owner, "owner")
    viewer, _ = await make_workspace(db)
    await add_member(db, ws, viewer, "viewer")
    outsider, _ = await make_workspace(db)

    up = await api.post(
        f"/api/v1/workspaces/{ws.id}/documents",
        files={"file": ("a.txt", b"hello", "text/plain")},
        headers=_as(viewer),
    )
    assert up.status_code == 403

    listing = await api.get(f"/api/v1/workspaces/{ws.id}/documents", headers=_as(outsider))
    assert listing.status_code == 403
