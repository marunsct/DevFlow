"""A run's own model: pin it to the model it last ran on, or let it follow the settings.

The model (server address, model name, context window, reply ceiling, judgement
tier) used to be one global runtime setting that every run followed, so two runs
of one harness could never use two model servers. Each run now carries
`model_pinned` and `model_last` (the run store):

*   `model_last` is a snapshot of the non-secret model keys
    (`runtime_settings.MODEL_KEYS`) the run last ran with. Never a key: the
    credential of an endpoint is resolved server-side, per endpoint, exactly as
    before.
*   Unpinned, the run follows the settings on every request and `model_last` is
    kept equal to what it last ran on (`note_ran_on`).
*   Pinned, the run uses `model_last` whatever the settings say now; it is laid
    over the model keys in `runtime_settings.effective_environment`, so the
    context budget, the reply ceiling and every client built for the run follow
    it, and `PinTransport` sends each request to it.

The toggle works mid-run. A request already sent finishes on the endpoint it was
sent to; every new request asks again which model the run is on (a database read
cached for `STATE_TTL_SECONDS`, because the API process writes the flag and the
worker, another container, reads it).

How a request is rerouted
-------------------------
A client is built for one address and model. `PinTransport` sits under its
httpx client and, per request, asks "which run am I in and what is that run's
model". Only when the answer differs from what the client was built for does it
rewrite the base URL, the `Host` header, the `Authorization` header and the
JSON `model` field; otherwise the request goes on exactly as it was. The
credential is the destination's own: its endpoint key, or none, in which case
the `Authorization` header is removed. The key of one server is never sent to
another.

What it will not do is guess. A destination of another provider, or of another
kind (a hosted API for a self-hosted client), is not rewritten; a state that
cannot be read falls back to the last known one and, with none, to the request
as it was. Each of those says so once per run.
"""

from __future__ import annotations

import contextvars
import json
import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Mapping
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

#: How long a process reuses what it read of a run's pin and of the model it resolves to.
STATE_TTL_SECONDS = 2.0

#: Providers that are not OpenAI-compatible: their clients are not rerouted per request.
_NOT_REROUTED = frozenset({"anthropic", "gemini", "google"})

_AS_THE_RUN: contextvars.ContextVar[str | None] = contextvars.ContextVar("model_pin_run", default=None)


@contextmanager
def as_the_run(run_id: str | None) -> Iterator[None]:
    """Within it, model settings are read as run `run_id` sees them.

    For a process that is not running the run - the API checking, on a resume, that the model a pinned run will
    use is reachable. Without a run id nothing changes.
    """
    token = _AS_THE_RUN.set(run_id or None)
    try:
        yield
    finally:
        _AS_THE_RUN.reset(token)


def current_run_id() -> str:
    """The run this call belongs to: `as_the_run`, else the graph's config, else the worker task's run; "" outside any."""
    explicit = _AS_THE_RUN.get()
    if explicit:
        return str(explicit)
    try:
        from app.observability.log_context import _TASK_RUN, _from_the_graph

        run, _stage = _from_the_graph()
        return str(run or _TASK_RUN.get() or "")
    except Exception:  # noqa: BLE001 - a call outside a run
        return ""


# ---------------------------------------------------------------------------
# The run's pin, from the run store
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelState:
    """Whether a run is pinned, and the model it last ran on (non-secret keys only)."""

    pinned: bool
    last: Mapping[str, str]


_STATE: dict[str, tuple[float, ModelState | None]] = {}
_LOCK = threading.Lock()
_WARNED: set[tuple[str, str]] = set()


def _store() -> Any:
    from app.server.run_store import RunStore

    return RunStore.shared()


def _warn_once(run_id: str, topic: str, text: str) -> None:
    with _LOCK:
        if (run_id, topic) in _WARNED:
            return
        _WARNED.add((run_id, topic))
    logger.warning("%s", text)


def forget(run_id: str | None = None) -> None:
    """Drop what was read (one run's, or everything). For a change made here, and for tests."""
    with _LOCK:
        if run_id is None:
            _STATE.clear()
            _DESTINATIONS.clear()
            _WARNED.clear()
        else:
            _STATE.pop(run_id, None)
            for key in [key for key in _DESTINATIONS if key[0] == run_id]:
                _DESTINATIONS.pop(key, None)


def run_state(run_id: str) -> ModelState | None:
    """The run's pin and last model, cached briefly; the last known on a failed read; None when there is none."""
    now = time.monotonic()
    with _LOCK:
        hit = _STATE.get(run_id)
    if hit is not None and now - hit[0] < STATE_TTL_SECONDS:
        return hit[1]
    try:
        raw = _store().model_state(run_id)
        state = ModelState(bool(raw[0]), dict(raw[1] or {})) if raw else None
    except Exception:  # noqa: BLE001 - the last known state, else the request as it was
        _warn_once(run_id, "state", "Could not read this run's model pin; using the last known state "
                   "(or the settings when there is none)")
        logger.debug("model pin read failed", exc_info=True)
        state = hit[1] if hit is not None else None
    with _LOCK:
        _STATE[run_id] = (now, state)
    return state


def pinned_snapshot() -> Mapping[str, str] | None:
    """The model of the run this call belongs to when the run is pinned and has one; else None."""
    run = current_run_id()
    if not run:
        return None
    state = run_state(run)
    if state is not None and state.pinned and state.last:
        return state.last
    return None


def note_ran_on(run_id: str, state: ModelState | None) -> ModelState | None:
    """Keep `model_last` equal to the settings for an unpinned run; a pinned run's is left as it is.

    Written only when it changes, and only while the run is unpinned (the store refuses otherwise), so a toggle
    racing with this write cannot be undone by it.
    """
    if state is None or state.pinned:
        return state
    try:
        from app.server.runtime_settings import global_model_snapshot

        now = global_model_snapshot()
    except Exception:  # noqa: BLE001
        return state
    if dict(state.last) == now:
        return state
    try:
        written = bool(_store().set_model_last(run_id, now))
    except Exception:  # noqa: BLE001 - the record of where it ran is an aid
        _warn_once(run_id, "write", "Could not record the model this run last ran on")
        return state
    if not written:
        forget(run_id)
        return state
    fresh = ModelState(False, now)
    with _LOCK:
        _STATE[run_id] = (time.monotonic(), fresh)
    return fresh


# ---------------------------------------------------------------------------
# The model a run is on, as a destination
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Destination:
    provider: str
    base_url: str
    model: str
    #: The credential that belongs to this destination, or None. Never logged, never stored.
    key: str | None = None

    def __repr__(self) -> str:  # a key must not reach a log line by accident
        return f"Destination({self.provider!r}, {self.base_url!r}, {self.model!r})"


_DESTINATIONS: dict[tuple[str, str], tuple[float, Destination | None]] = {}


def destination(role: str, run_id: str) -> Destination | None:
    """Where the run's `role` model ("default" or "judgement") is served now, cached briefly. None when unknown."""
    now = time.monotonic()
    with _LOCK:
        hit = _DESTINATIONS.get((run_id, role))
    if hit is not None and now - hit[0] < STATE_TTL_SECONDS:
        return hit[1]
    found: Destination | None
    try:
        found = _resolve(role)
    except Exception:  # noqa: BLE001
        _warn_once(run_id, "resolve", "Could not resolve the model this run is on; requests go where they were built for")
        found = hit[1] if hit is not None else None
    with _LOCK:
        _DESTINATIONS[(run_id, role)] = (now, found)
    return found


def _resolve(role: str) -> Destination | None:
    from app.models.endpoints import default_address
    from app.models.roles import judgement_environment
    from app.server.runtime_settings import _KEY_VARIABLE, effective_environment

    environment = effective_environment()
    if role == "judgement":
        environment = judgement_environment(environment) or environment
    provider = str(environment.get("LLM_PROVIDER") or "local").strip().lower()
    base = str(environment.get("OPENAI_BASE_URL") or "").strip() or default_address(provider)
    model = str(environment.get("OPENAI_MODEL") or "").strip()
    key = str(environment.get(_KEY_VARIABLE.get(provider, "OPENAI_API_KEY")) or "").strip()
    return Destination(provider, base, model, key or None)


# ---------------------------------------------------------------------------
# The transport
# ---------------------------------------------------------------------------


def _normal(url: str) -> str:
    from app.models.endpoints import reached_from_here

    return reached_from_here(str(url or "").strip())[0].rstrip("/").lower()


@dataclass(frozen=True)
class _Target:
    destination: Destination
    address_changes: bool
    model_changes: bool
    #: The run is pinned: its requests carry the destination's own credential even where the address is the same.
    pinned: bool = False


class _Rerouter:
    """What `PinTransport` and `AsyncPinTransport` share: deciding where a request should go, and building it."""

    def __init__(self, built_base: str, built_model: str, role: str = "default", address_only: bool = False) -> None:
        self.built_base = str(built_base or "").strip()
        self.built_model = str(built_model or "").strip()
        self.role = role
        self.address_only = address_only

    def target(self) -> _Target | None:
        """Where this call's requests should go instead of where the client was built for; None to leave them."""
        run = current_run_id()
        if not run:
            return None
        state = note_ran_on(run, run_state(run))
        pinned = bool(state is not None and state.pinned)
        dest = destination(self.role, run)
        if dest is None or not dest.base_url:
            return None
        if dest.provider in _NOT_REROUTED:
            _warn_once(run, "provider", f"This run's model is served by {dest.provider}, which is not rerouted per "
                       "request; its requests go where they were built for")
            return None
        address_changes = _normal(dest.base_url) != _normal(self.built_base)
        model_changes = (not self.address_only) and bool(dest.model) and dest.model != self.built_model
        if not address_changes and not model_changes:
            # A pinned run's client was built for its model, but with whatever key stood in for it (a local server
            # takes a placeholder): the request carries the destination's own key or none (`rewritten`).
            return _Target(dest, False, False, True) if pinned else None
        if address_changes:
            from app.models.endpoints import is_self_hosted

            if is_self_hosted(dest.base_url) != is_self_hosted(self.built_base):
                _warn_once(run, "kind", "This run's model is a hosted API where its client was built for a "
                           "self-hosted server (or the reverse); its requests go where they were built for")
                return None
        return _Target(dest, address_changes, model_changes, pinned)

    def served_by(self) -> tuple[str, str]:
        """(address, model) this call's requests go to: what the client was built for unless rerouted."""
        try:
            target = self.target()
        except Exception:  # noqa: BLE001
            target = None
        if target is None:
            return self.built_base, self.built_model
        return (
            target.destination.base_url if target.address_changes else self.built_base,
            target.destination.model if target.model_changes else self.built_model,
        )

    def rewritten(self, request: httpx.Request, body: bytes) -> httpx.Request | None:
        """The request aimed at the run's model, or None to send it as it was."""
        try:
            target = self.target()
        except Exception:  # noqa: BLE001 - never fail a call for the sake of rerouting it
            logger.debug("model pin could not decide", exc_info=True)
            return None
        if target is None:
            return None
        run = current_run_id()
        url = str(request.url)
        headers = httpx.Headers(request.headers)
        headers.pop("content-length", None)
        if target.address_changes:
            from app.models.endpoints import reached_from_here

            old = self.built_base.rstrip("/")
            if not url.lower().startswith(old.lower()):
                _warn_once(run, "url", "A request was not under the client's address; it was left as it was")
                return None
            reached, naming = reached_from_here(target.destination.base_url)
            url = reached.rstrip("/") + url[len(old):]
            headers.pop("host", None)
            for name, value in naming.items():
                headers[name] = value
        if target.address_changes or target.pinned:
            # The destination's own credential, or none: one server's key never goes to another.
            wanted = f"Bearer {target.destination.key}" if target.destination.key else None
            if headers.get("authorization") != wanted:
                headers.pop("authorization", None)
                if wanted:
                    headers["Authorization"] = wanted
            elif not target.address_changes and not target.model_changes:
                return None
        if target.model_changes:
            try:
                payload = json.loads(body)
                if not isinstance(payload, dict) or "model" not in payload:
                    raise ValueError("no model field")
            except ValueError:
                _warn_once(run, "body", "A request had no model field to point at the run's model; it was left as it was")
                return None
            payload["model"] = target.destination.model
            body = json.dumps(payload).encode("utf-8")
        return httpx.Request(request.method, url, headers=headers, content=body, extensions=request.extensions)


class PinTransport(httpx.BaseTransport):
    """The sync transport under a model client's httpx client; see the module docstring."""

    def __init__(self, rerouter: _Rerouter, inner: httpx.BaseTransport | None = None) -> None:
        self.rerouter = rerouter
        self._inner = inner or httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        body = request.read()
        return self._inner.handle_request(self.rerouter.rewritten(request, body) or request)

    def close(self) -> None:
        self._inner.close()


class AsyncPinTransport(httpx.AsyncBaseTransport):
    """The async transport under a model client's httpx client; see the module docstring."""

    def __init__(self, rerouter: _Rerouter, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self.rerouter = rerouter
        self._inner = inner or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        return await self._inner.handle_async_request(self.rerouter.rewritten(request, body) or request)

    async def aclose(self) -> None:
        await self._inner.aclose()


class PinnedClient(httpx.Client):
    """An httpx client that knows what its transport reroutes to (`served_by`)."""

    rerouter: _Rerouter


class PinnedAsyncClient(httpx.AsyncClient):
    rerouter: _Rerouter


_CLIENTS: dict[tuple[str, str, str, bool], tuple[PinnedClient, PinnedAsyncClient]] = {}

#: What the OpenAI client's own default http client uses, so a pinned build behaves the same under load.
_LIMITS = httpx.Limits(max_connections=1000, max_keepalive_connections=100)


def clients_for(built_base: str, built_model: str, *, role: str = "default", address_only: bool = False) -> dict[str, Any]:
    """`http_client` and `http_async_client` for a client built for (`built_base`, `built_model`).

    One pair per built destination and role, shared by the clients built for it, as the OpenAI client shares its
    own default: a stage builds its model again on every node, and a new connection pool each time would leak.
    """
    key = (str(built_base or ""), str(built_model or ""), role, bool(address_only))
    with _LOCK:
        pair = _CLIENTS.get(key)
        if pair is None:
            rerouter = _Rerouter(*key[:2], role=role, address_only=address_only)
            sync = PinnedClient(transport=PinTransport(rerouter), follow_redirects=True, limits=_LIMITS)
            asynchronous = PinnedAsyncClient(transport=AsyncPinTransport(rerouter), follow_redirects=True, limits=_LIMITS)
            sync.rerouter = asynchronous.rerouter = rerouter
            pair = _CLIENTS[key] = (sync, asynchronous)
    return {"http_client": pair[0], "http_async_client": pair[1]}


def served_by(client: Any, built: tuple[str, str]) -> tuple[str, str]:
    """(address, model) a chat model's next request goes to; `built` when it is not rerouted. Never raises."""
    rerouter = getattr(getattr(client, "http_client", None), "rerouter", None)
    if rerouter is None:
        return built
    try:
        return rerouter.served_by()
    except Exception:  # noqa: BLE001
        return built


# ---------------------------------------------------------------------------
# Snapshots the API sets and shows
# ---------------------------------------------------------------------------


def clean_base_url(value: str | None) -> str:
    """A model server address worth pinning a run to; ValueError otherwise (http or https, no credentials in it)."""
    text = str(value or "").strip()
    if not text or len(text) > 300 or any(ch.isspace() or ord(ch) < 32 for ch in text):
        raise ValueError("base_url must be an http or https address")
    try:
        parsed = urlparse(text)
        parsed.port  # noqa: B018 - raises on a bad port
    except ValueError as error:
        raise ValueError("base_url is not a valid address") from error
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("base_url must be an http or https address")
    if parsed.username or parsed.password or "@" in parsed.netloc:
        raise ValueError("base_url must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("base_url must not carry a query or fragment")
    return text


def clean_model_name(value: str | None) -> str:
    """A model name worth pinning a run to; ValueError when empty."""
    text = str(value or "").strip()
    if not text or len(text) > 200 or any(ord(ch) < 32 for ch in text):
        raise ValueError("model must not be empty")
    return text


def snapshot_for(base: Mapping[str, str], base_url: str | None = None, model: str | None = None) -> dict[str, str]:
    """`base` (a model snapshot) with the address and the model name replaced; the rest, the provider included, stays.

    A judgement model with no address of its own was served from the default model's, so it keeps that address
    rather than following the default model to its new one.
    """
    snapshot = {key: str(value or "") for key, value in base.items()}
    if base_url:
        if (snapshot.get("JUDGEMENT_MODEL") and not snapshot.get("JUDGEMENT_BASE_URL")
                and snapshot.get("JUDGEMENT_PROVIDER", "") in ("", snapshot.get("LLM_PROVIDER", ""))):
            snapshot["JUDGEMENT_BASE_URL"] = snapshot.get("OPENAI_BASE_URL", "")
        snapshot["OPENAI_BASE_URL"] = base_url
    if model:
        snapshot["OPENAI_MODEL"] = model
    return snapshot


def summary_of(last: Mapping[str, str] | None) -> dict[str, str] | None:
    """The model name and host:port of a snapshot - all the status response says of it. None for no snapshot."""
    if not last:
        return None
    base = str(last.get("OPENAI_BASE_URL") or "")
    try:
        parsed = urlparse(base)
        where = f"{parsed.hostname}:{parsed.port}" if parsed.hostname and parsed.port else (parsed.hostname or "")
    except ValueError:
        where = ""
    return {"model": str(last.get("OPENAI_MODEL") or ""), "endpoint": where}


__all__ = [
    "AsyncPinTransport",
    "Destination",
    "ModelState",
    "PinTransport",
    "STATE_TTL_SECONDS",
    "as_the_run",
    "clean_base_url",
    "clean_model_name",
    "clients_for",
    "current_run_id",
    "destination",
    "forget",
    "note_ran_on",
    "pinned_snapshot",
    "run_state",
    "served_by",
    "snapshot_for",
    "summary_of",
]
