"""Redis fixed-window rate limiting as FastAPI dependencies.

Each (scope, identity) pair gets a counter keyed by the current window number,
so keys roll over on their own and expire shortly after. Counts are shared by
every API worker because they live in Redis, not process memory.

If Redis is unreachable the request is allowed and a warning is logged: a cache
outage should degrade protection, not take chat and uploads down with it.
Per-day plan quotas (``check_query_quota``) are enforced separately in Postgres.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import Depends, Request
from redis import asyncio as aioredis
from redis.exceptions import RedisError

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.exceptions import RateLimitError
from app.services.monitoring.logger import get_logger

WINDOW_SECONDS = 60


class _Pipeline(Protocol):
    def incr(self, name: str) -> Any: ...
    def expire(self, name: str, time: int) -> Any: ...
    async def execute(self) -> list[Any]: ...


class RedisLike(Protocol):
    def pipeline(self, transaction: bool = True) -> _Pipeline: ...


_client: RedisLike | None = None


def get_rate_limit_client() -> RedisLike:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            get_settings().redis_url,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
    return _client


def set_rate_limit_client(client: RedisLike | None) -> None:
    """Swap the Redis client (tests); ``None`` resets to the configured URL."""
    global _client
    _client = client


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    count: int
    retry_after: int


async def hit(
    scope: str,
    identity: str,
    limit: int,
    *,
    window: int = WINDOW_SECONDS,
    now: float | None = None,
) -> RateLimitResult:
    """Count one request and report whether it is within ``limit`` per ``window``."""
    now = time.time() if now is None else now
    bucket = int(now // window)
    retry_after = max(1, window - int(now % window))
    key = f"rl:{scope}:{identity}:{bucket}"
    try:
        pipe = get_rate_limit_client().pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, window + 1)
        count, _ = await pipe.execute()
    except (RedisError, OSError) as exc:
        get_logger().warning("rate_limit.redis_unavailable", scope=scope, error=str(exc))
        return RateLimitResult(allowed=True, count=0, retry_after=0)
    count = int(count)
    return RateLimitResult(allowed=count <= limit, count=count, retry_after=retry_after)


async def _enforce(scope: str, identity: str, limit: int) -> None:
    settings = get_settings()
    if not settings.rate_limit_enabled or limit <= 0:
        return
    result = await hit(scope, identity, limit)
    if not result.allowed:
        raise RateLimitError(
            f"Too many requests — limit is {limit} per minute. Try again in {result.retry_after}s.",
            retry_after=result.retry_after,
        )


def _client_ip(request: Request) -> str:
    # Uses the socket peer. Behind a reverse proxy, run uvicorn with
    # --proxy-headers and --forwarded-allow-ips so this is the real client.
    return request.client.host if request.client else "unknown"


def limit_per_user(scope: str, setting: str):
    """Dependency: ``getattr(settings, setting)`` requests/minute per user."""

    async def _dep(user: CurrentUser) -> None:
        await _enforce(scope, f"user:{user.id}", getattr(get_settings(), setting))

    return Depends(_dep)


def limit_per_ip(scope: str, setting: str):
    """Dependency: ``getattr(settings, setting)`` requests/minute per client IP."""

    async def _dep(request: Request) -> None:
        await _enforce(scope, f"ip:{_client_ip(request)}", getattr(get_settings(), setting))

    return Depends(_dep)
