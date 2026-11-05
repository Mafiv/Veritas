"""Every workspace-scoped route must refuse users who are not members.

Routes are discovered from the app, so a new endpoint that forgets its
membership dependency fails this test without anyone remembering to add it.
"""

from __future__ import annotations

import re
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app

from .conftest import add_member, make_workspace

# Routes intentionally reachable without membership (none today).
PUBLIC_WORKSPACE_ROUTES: set[tuple[str, str]] = set()


def _workspace_routes() -> list[tuple[str, str]]:
    # The OpenAPI schema is the public, stable view of every mounted route.
    out = []
    for path, ops in app.openapi()["paths"].items():
        if "{workspace_id}" not in path:
            continue
        for method in ops:
            key = (method.upper(), path)
            if key not in PUBLIC_WORKSPACE_ROUTES:
                out.append(key)
    return sorted(out)


ROUTES = _workspace_routes()


def test_discovers_workspace_routes() -> None:
    assert len(ROUTES) >= 20, ROUTES


@pytest.mark.parametrize(("method", "path"), ROUTES, ids=[f"{m} {p}" for m, p in ROUTES])
async def test_non_member_is_refused(
    api: AsyncClient, db: AsyncSession, method: str, path: str
) -> None:
    owner, ws = await make_workspace(db)
    await add_member(db, ws, owner, "owner")
    outsider, _ = await make_workspace(db)

    url = path.replace("{workspace_id}", str(ws.id))
    url = re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), url)
    resp = await api.request(
        method, url, headers={"x-test-user": str(outsider.id)}, json={} if method != "GET" else None
    )
    assert resp.status_code in (403, 404), (
        f"{method} {path} -> {resp.status_code}: {resp.text[:200]}"
    )
