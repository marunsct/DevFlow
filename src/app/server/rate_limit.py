"""Rate limiting for the API surface.

Two distinct concerns live here:

- a general per-caller request budget applied as middleware, and
- a much stricter failed-login budget, because credential stuffing needs a far
  tighter bound than ordinary API traffic and must be keyed on the account being
  attacked as well as the source address.

Both fail *closed* on the login path and *open* on the general path. That is
deliberate: losing Redis should not lock every user out of a working system, but
it also must not silently turn off brute-force protection, so the login limiter
falls back to an in-process counter rather than to no limit at all.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import threading
import time
from collections import defaultdict

from fastapi import Request

logger = logging.getLogger(__name__)

RATE_LIMIT_MAX_REQUESTS = int(os.environ.get("RATE_LIMIT_MAX_REQUESTS", "300"))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))

LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_WINDOW_SECONDS = int(os.environ.get("LOGIN_WINDOW_SECONDS", "300"))

# Paths excluded from the general budget: long-lived streams would otherwise
# consume a caller's whole allowance on connect, and health probes fire far more
# often than user traffic.
EXEMPT_PREFIXES = ("/api/health", "/metrics")


def _trusted_proxies() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    raw = os.environ.get("TRUSTED_PROXIES", "").strip()
    if not raw:
        return []
    networks = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logger.warning("Ignoring unparseable TRUSTED_PROXIES entry: %r", item)
    return networks


_TRUSTED = _trusted_proxies()


def client_identity(request: Request) -> str:
    """Identify the caller for rate-limiting purposes.

    An authenticated subject is preferred, because keying on IP alone collapses
    every user behind a corporate NAT or an ingress into one shared bucket.
    X-Forwarded-For is honoured only when the immediate peer is a configured
    trusted proxy - otherwise any client could forge it and evade the limit
    entirely.
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        # The token is not verified here; this is a bucketing key, not a
        # security decision, and verification happens in the route dependency.
        return f"tok:{hash(auth[7:]) & 0xFFFFFFFF:08x}"

    peer = request.client.host if request.client else "unknown"
    if _TRUSTED and peer != "unknown":
        try:
            peer_ip = ipaddress.ip_address(peer)
        except ValueError:
            return f"ip:{peer}"
        if any(peer_ip in net for net in _TRUSTED):
            forwarded = request.headers.get("X-Forwarded-For", "")
            if forwarded:
                return f"ip:{forwarded.split(',')[0].strip()}"
    return f"ip:{peer}"


async def enforce_request_budget(request: Request) -> bool:
    """Return True if the request may proceed.

    Uses the async Redis client so the event loop is not blocked; a Redis outage
    logs and allows the request through rather than taking the API down with it.
    """
    if any(request.url.path.startswith(prefix) for prefix in EXEMPT_PREFIXES):
        return True

    from app.server.redis_client import get_async_redis_client

    key = f"rate_limit:{client_identity(request)}"
    try:
        client = get_async_redis_client()
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, RATE_LIMIT_WINDOW_SECONDS, nx=True)
        current, _ = await pipe.execute()
        return int(current) <= RATE_LIMIT_MAX_REQUESTS
    except Exception:  # noqa: BLE001
        logger.warning("Rate limiter unavailable; allowing request", exc_info=True)
        return True


# ---------------------------------------------------------------------------
# Login throttling
# ---------------------------------------------------------------------------

_local_attempts: dict[str, list[float]] = defaultdict(list)
_local_lock = threading.Lock()


def _login_keys(username: str, client_ip: str) -> tuple[str, str]:
    return f"login_fail:user:{username.lower()}", f"login_fail:ip:{client_ip}"


def _local_count(key: str) -> int:
    cutoff = time.monotonic() - LOGIN_WINDOW_SECONDS
    with _local_lock:
        hits = [t for t in _local_attempts[key] if t > cutoff]
        _local_attempts[key] = hits
        return len(hits)


def _local_register(key: str) -> None:
    with _local_lock:
        _local_attempts[key].append(time.monotonic())


def _local_clear(key: str) -> None:
    with _local_lock:
        _local_attempts.pop(key, None)


def check_login_attempt(username: str, client_ip: str) -> bool:
    """Return True if this login attempt is allowed to proceed."""
    from app.server.redis_client import get_redis_client

    user_key, ip_key = _login_keys(username, client_ip)
    try:
        client = get_redis_client()
        counts = client.mget(user_key, ip_key)
        return all(int(c or 0) < LOGIN_MAX_ATTEMPTS for c in counts)
    except Exception:  # noqa: BLE001
        logger.warning("Login limiter falling back to in-process counters", exc_info=True)
        return _local_count(user_key) < LOGIN_MAX_ATTEMPTS and _local_count(ip_key) < LOGIN_MAX_ATTEMPTS


def register_failed_login(username: str, client_ip: str) -> None:
    from app.server.redis_client import get_redis_client

    user_key, ip_key = _login_keys(username, client_ip)
    try:
        client = get_redis_client()
        pipe = client.pipeline()
        for key in (user_key, ip_key):
            pipe.incr(key)
            pipe.expire(key, LOGIN_WINDOW_SECONDS)
        pipe.execute()
    except Exception:  # noqa: BLE001
        _local_register(user_key)
        _local_register(ip_key)


def clear_login_attempts(username: str, client_ip: str) -> None:
    from app.server.redis_client import get_redis_client

    user_key, ip_key = _login_keys(username, client_ip)
    try:
        get_redis_client().delete(user_key, ip_key)
    except Exception:  # noqa: BLE001
        pass
    _local_clear(user_key)
    _local_clear(ip_key)


__all__ = [
    "LOGIN_MAX_ATTEMPTS",
    "RATE_LIMIT_MAX_REQUESTS",
    "check_login_attempt",
    "clear_login_attempts",
    "client_identity",
    "enforce_request_budget",
    "register_failed_login",
]
