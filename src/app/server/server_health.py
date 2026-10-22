"""`GET /api/health/server`: the build model's server as it describes itself (plan BG.5).

The worker reads the server's status once per run segment
(`app.models.server_profile`) and keeps it in its own process, where the API
cannot see it. The page asks the API, so the API reads the status itself: one
request to `/props`, never a model call, kept for a minute, so a header that
asks from every open tab costs the server one small request a minute and the
run on it nothing.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from app.models import server_profile
from app.server.models import ServerHealth

#: How long one reading of the server's status is answered from.
CACHE_SECONDS = 60

#: Providers that are hosted APIs: they have no server status to read.
HOSTED = frozenset({"anthropic", "gemini"})

_CACHE: tuple[float, ServerHealth] | None = None


def read_server_health(
    busy_runs: list[str],
    *,
    clock: Callable[[], float] = time.monotonic,
    reader: Callable[[str, str], server_profile.ServerProfile | None] | None = None,
    settings: Any = None,
) -> ServerHealth:
    """The server's status with the runs on it now; blocking, so a route runs it in a thread."""
    global _CACHE
    now = clock()
    if _CACHE is not None and now - _CACHE[0] < CACHE_SECONDS:
        return _CACHE[1].model_copy(update={"busy_runs": busy_runs})
    if settings is None:
        from app.models import _runtime_settings

        settings = _runtime_settings()
    configured = str(getattr(settings, "model_name", "") or "")
    checked_at = datetime.now(timezone.utc)
    if str(getattr(settings, "llm_provider", "") or "") in HOSTED:
        health = ServerHealth(hosted=True, answered=False, model=configured, checked_at=checked_at)
    else:
        profile = (reader or server_profile.read)(
            str(getattr(settings, "openai_base_url", "") or ""), str(getattr(settings, "openai_api_key", "") or "")
        )
        health = ServerHealth(
            hosted=False,
            answered=profile is not None,
            model=(profile.model if profile is not None and profile.model else configured),
            quantisation=profile.quantisation if profile is not None else "",
            slots=profile.slots if profile is not None else None,
            slot_context=profile.slot_context if profile is not None else None,
            checked_at=checked_at,
        )
    _CACHE = (now, health)
    return health.model_copy(update={"busy_runs": busy_runs})


def forget() -> None:
    global _CACHE
    _CACHE = None


__all__ = ["CACHE_SECONDS", "forget", "read_server_health"]
