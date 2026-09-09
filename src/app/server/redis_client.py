"""Redis clients, sync and async, sharing one URL resolution.

The sync client exists for Celery-side code that has no event loop. Anything on
the request path must use the async client: a synchronous Redis call inside an
async handler blocks the whole event loop for the duration of the round trip.

Both are created lazily so that the URL is read when it is first needed rather
than at import, which lets tests point them at a container.
"""

from __future__ import annotations

import os
from typing import Optional

import redis
import redis.asyncio as aioredis

_sync_pool: Optional[redis.ConnectionPool] = None

# Async clients are cached per event loop, not globally. A redis.asyncio client
# binds its connections to the loop that created them, so a single module-level
# instance breaks the moment a second loop appears - which happens in tests, and
# whenever a worker restarts its loop.
_async_clients: "dict[int, aioredis.Redis]" = {}


def redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def get_redis_client() -> redis.Redis:
    """Blocking client. Only for worker-side code, never a request handler."""
    global _sync_pool
    if _sync_pool is None:
        _sync_pool = redis.ConnectionPool.from_url(
            redis_url(), decode_responses=True, health_check_interval=30
        )
    return redis.Redis(connection_pool=_sync_pool)


def get_async_redis_client() -> aioredis.Redis:
    """Non-blocking client for anything running on the event loop."""
    import asyncio

    try:
        loop_key = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_key = 0

    client = _async_clients.get(loop_key)
    if client is None:
        client = aioredis.from_url(redis_url(), decode_responses=True, health_check_interval=30)
        _async_clients[loop_key] = client
    return client


def close_redis_pool() -> None:
    global _sync_pool
    if _sync_pool is not None:
        _sync_pool.disconnect()
        _sync_pool = None


async def close_async_redis() -> None:
    """Close the client for the current loop, if there is one.

    Tolerates an already-closed loop: shutdown must never raise out of a
    lifespan handler.
    """
    import asyncio

    try:
        loop_key = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_key = 0

    client = _async_clients.pop(loop_key, None)
    if client is not None:
        try:
            await client.aclose()
        except (RuntimeError, ConnectionError):
            pass


def reset_clients() -> None:
    """Drop cached clients so the next call re-reads REDIS_URL (tests)."""
    global _sync_pool
    if _sync_pool is not None:
        _sync_pool.disconnect()
    _sync_pool = None
    _async_clients.clear()


__all__ = [
    "close_async_redis",
    "close_redis_pool",
    "get_async_redis_client",
    "get_redis_client",
    "redis_url",
    "reset_clients",
]
