"""Whether the frontier (judgement) model a run would use is configured and answering.

Owner, 2026-10-19: a run started with "use the frontier model" ticked must not
start when that model is missing from the settings or cannot be reached - the
run would build its specification and reviews on the local model, or fail at
its first judgement stage, with nothing at the start to say so.

Configured: a judgement model is named, and its provider has a key where it
needs one. Answering: its endpoint answers a listing of its models - a read,
never a model call, so it costs nothing and sends no prompt. Kept for a minute,
so a start form that asks on every tick costs the provider one request.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping

from app.models.roles import _KEY_FOR_PROVIDER, judgement_environment, judgement_model_name

#: Where a hosted provider lists its models, when no address is configured.
HOSTED_LISTINGS = {
    "anthropic": "https://api.anthropic.com/v1/models",
    "openai": "https://api.openai.com/v1/models",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
    "google": "https://generativelanguage.googleapis.com/v1beta/models",
}

#: Providers that never work without a key.
NEEDS_A_KEY = frozenset(HOSTED_LISTINGS)

LISTING_TIMEOUT_SECONDS = 6
CACHE_SECONDS = 60

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _request(provider: str, base_url: str, key: str) -> urllib.request.Request:
    if base_url:
        from app.models.endpoints import reached_from_here

        reached, naming = reached_from_here(base_url.rstrip("/"))
        headers = {**naming, **({"Authorization": f"Bearer {key}"} if key else {})}
        return urllib.request.Request(reached + "/models", headers=headers)
    if provider == "anthropic":
        return urllib.request.Request(HOSTED_LISTINGS[provider], headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
    if provider in ("gemini", "google"):
        return urllib.request.Request(HOSTED_LISTINGS[provider], headers={"x-goog-api-key": key})
    return urllib.request.Request(HOSTED_LISTINGS.get(provider, HOSTED_LISTINGS["openai"]), headers={"Authorization": f"Bearer {key}"})


def _answers(request: urllib.request.Request) -> str | None:
    """None when the endpoint answered its listing; otherwise why not, in words."""
    try:
        with urllib.request.urlopen(request, timeout=LISTING_TIMEOUT_SECONDS) as reply:
            json.load(reply)
        return None
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            return f"refused its key (HTTP {error.code})"
        return f"answered HTTP {error.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return f"could not be reached ({getattr(error, 'reason', error)})"
    except ValueError:
        return "answered something that is not a model listing"


def check_frontier(
    environment: Mapping[str, str] | None = None,
    *,
    reader: Callable[[urllib.request.Request], str | None] = _answers,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """{configured, active, model, provider, problem}: `problem` is None only when both hold."""
    if environment is None:
        from app.server.runtime_settings import effective_environment

        environment = effective_environment()
    name = judgement_model_name(environment)
    if not name:
        return {
            "configured": False, "active": False, "model": "", "provider": "",
            "problem": "No frontier model is configured. Name one under Settings → Models, or untick "
                       "\"Use the frontier model\" to run every stage on the local model.",
        }
    built = judgement_environment(environment) or {}
    provider = str(built.get("LLM_PROVIDER") or "local").lower()
    key = str(built.get(_KEY_FOR_PROVIDER.get(provider, "OPENAI_API_KEY")) or "")
    base_url = str(built.get("OPENAI_BASE_URL") or "") if provider not in NEEDS_A_KEY or environment.get("JUDGEMENT_BASE_URL") else ""
    found = {"configured": True, "active": False, "model": name, "provider": provider, "problem": None}
    if provider in NEEDS_A_KEY and not key:
        return {**found, "configured": False,
                "problem": f"The frontier model {name} is set on {provider}, but no key for it is saved. Add one under Settings → Models."}
    cache_key = f"{provider}|{base_url}|{name}|{hash(key)}"
    kept = _CACHE.get(cache_key)
    if kept and clock() - kept[0] < CACHE_SECONDS:
        return kept[1]
    why = reader(_request(provider, base_url, key))
    answer = {**found, "active": why is None,
              "problem": None if why is None else f"The frontier model {name} on {provider} {why}. Check it under Settings → Models."}
    _CACHE[cache_key] = (clock(), answer)
    return answer


def forget() -> None:
    _CACHE.clear()


__all__ = ["check_frontier", "forget"]
