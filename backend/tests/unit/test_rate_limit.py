"""Redis fixed-window rate limiter (in-memory stand-in for Redis)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.api import rate_limit
from app.api.rate_limit import hit, limit_per_ip, set_rate_limit_client
from app.core.config import get_settings


class FakeRedis:
    def __init__(self, fail: bool = False) -> None:
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.fail = fail

    def pipeline(self, transaction: bool = True) -> FakeRedis._Pipe:
        return FakeRedis._Pipe(self)

    class _Pipe:
        def __init__(self, r: FakeRedis) -> None:
            self.r = r
            self.ops: list[tuple[str, Any]] = []

        def incr(self, name: str) -> None:
            self.ops.append(("incr", name))

        def expire(self, name: str, time: int) -> None:
            self.ops.append(("expire", (name, time)))

        async def execute(self) -> list[Any]:
            if self.r.fail:
                raise RedisConnectionError("redis down")
            out: list[Any] = []
            for op, arg in self.ops:
                if op == "incr":
                    self.r.counts[arg] = self.r.counts.get(arg, 0) + 1
                    out.append(self.r.counts[arg])
                else:
                    self.r.ttls[arg[0]] = arg[1]
                    out.append(True)
            return out


@pytest.fixture
def fake_redis():
    fake = FakeRedis()
    set_rate_limit_client(fake)
    yield fake
    set_rate_limit_client(None)


async def test_allows_up_to_limit_then_blocks(fake_redis: FakeRedis):
    results = [await hit("chat", "user:1", 3, now=1000.0) for _ in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]
    assert results[-1].retry_after == 20  # 1000 % 60 == 40s into the window
    assert all(ttl == 61 for ttl in fake_redis.ttls.values())


async def test_identities_and_scopes_are_independent(fake_redis: FakeRedis):
    assert (await hit("chat", "user:1", 1, now=0.0)).allowed
    assert (await hit("chat", "user:2", 1, now=0.0)).allowed
    assert (await hit("upload", "user:1", 1, now=0.0)).allowed
    assert not (await hit("chat", "user:1", 1, now=0.0)).allowed


async def test_window_rolls_over(fake_redis: FakeRedis):
    assert (await hit("chat", "u", 1, now=59.0)).allowed
    assert not (await hit("chat", "u", 1, now=59.5)).allowed
    assert (await hit("chat", "u", 1, now=60.0)).allowed


async def test_fails_open_when_redis_unavailable():
    set_rate_limit_client(FakeRedis(fail=True))
    try:
        result = await hit("chat", "u", 0, now=0.0)
    finally:
        set_rate_limit_client(None)
    assert result.allowed


async def test_dependency_returns_429_with_retry_after(
    fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_auth_sync_per_minute", 2)
    monkeypatch.setattr(rate_limit.time, "time", lambda: 30.0)

    from app.main import create_app

    app: FastAPI = create_app()

    @app.post("/limited", dependencies=[limit_per_ip("t", "rate_limit_auth_sync_per_minute")])
    async def _limited(request: Request) -> dict:
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        codes = [(await client.post("/limited")).status_code for _ in range(3)]
        blocked = await client.post("/limited")

    assert codes == [200, 200, 429]
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "30"
    assert blocked.json()["error"]["code"] == "rate_limit"


async def test_disabled_limits_never_touch_redis(monkeypatch: pytest.MonkeyPatch):
    set_rate_limit_client(FakeRedis(fail=True))
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", False)
    try:
        await rate_limit._enforce("chat", "u", 1)
    finally:
        set_rate_limit_client(None)
