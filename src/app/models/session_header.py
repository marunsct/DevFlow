"""The conversation a model request belongs to, named in a header a load balancer keeps sessions by.

A balancer in front of several model servers (olla in front of two llama.cpp instances) sends one session to one
server, so the server's prompt cache is reused. Without a session header it keys on the first 512 bytes of the
request, which is nearly the same system-prompt opening for every stage of every run: measured, 149 requests went
to one server and 82 to the other, and at times both slots of one GPU were busy with a third request queued while
the other GPU sat idle. Naming each stage's conversation (`<run>:<stage>`) keeps one conversation on its server and
lets two conversations - parallel fixers, two runs - go to different ones.

`MODEL_SESSION_HEADER` names the header (default `X-Olla-Session-ID`, olla's); set it empty to send none. A server
that does not know the header ignores it. `MODEL_SESSION_SCOPE` says what one session is: `conversation` (the default,
`<run>:<stage>`) keeps a conversation's prompt cache on one server; `request` gives every request a fresh value, so the
balancer picks the least-busy server for each call and the cache affinity is given up - the owner judged that three
requests sharing one GPU are no faster than a lost cache. Sent only to a self-hosted server (`CompatibleChatOpenAI`), never to a
hosted API.

Which calls share a session, by conversation (LF.1576). Measured with olla over two llama.cpp instances of two slots
each: every one-shot rewrite of one run went out as the run alone, olla kept that one session on one instance, and
four calls sat there for 214-656 s while the other instance was idle. So:

- **an agent's conversation** - a stage known (`<run>:<stage>`) - keeps one session, for its prompt cache; a one-call
  request made inside an agent's turn (a tool's or a middleware's) shares it, since the agent waits for it;
- **a call with no conversation to reuse** - no stage known: a graph node's one-shot call, a measurement outside any
  run - gets a fresh session per request, the run kept in front (`<run>:<fresh>`), as `request` scope does;
- **the parts of a fan-out** (`app.observability.direct_calls.mapped_in_this_context`: candidate fixes, drafted
  files, parts of a specification) each get a session of their own (`<run>[:<stage>]:<part>`), so the balancer can
  put side-by-side calls on different servers; a part's later calls (a retry) keep its session.
"""
from __future__ import annotations

import contextvars
import os
import re
import uuid
from collections.abc import Callable, Mapping
from typing import TypeVar

#: olla's session header; its sticky sessions read it before falling back to a hash of the request's opening bytes.
DEFAULT_SESSION_HEADER = "X-Olla-Session-ID"

#: Longest value sent; a run id and a stage name are far shorter.
_MOST_CHARS = 200

_UNSAFE = re.compile(r"[^A-Za-z0-9._:\-]")


def session_header_name(environment: Mapping[str, str] | None = None) -> str:
    """The header's name: `MODEL_SESSION_HEADER`, olla's when unset; "" (none sent) when set empty."""
    values = os.environ if environment is None else environment
    raw = values.get("MODEL_SESSION_HEADER")
    if raw is None:
        return DEFAULT_SESSION_HEADER
    return str(raw).strip()


#: The scopes `MODEL_SESSION_SCOPE` takes; anything else is the default, `conversation`.
SCOPES = ("conversation", "request")


def session_scope(environment: Mapping[str, str] | None = None) -> str:
    """`MODEL_SESSION_SCOPE`: `request` for a fresh session per request; `conversation` otherwise.

    For the process's own environment, the scope the owner set for the serving model on the settings page comes
    first, and where neither that nor `MODEL_SESSION_SCOPE` is set, the scope its concurrency probe measured
    (`speed_profile`, DX.6; behind `PROFILE_FROM_DIAGNOSIS`)."""
    values = os.environ if environment is None else environment
    profile = None
    if environment is None:
        try:
            from app.models import diagnosis_profile as profile
        except Exception:  # noqa: BLE001
            profile = None
    owner = profile.owner("session_scope") if profile is not None else None
    if owner in SCOPES:
        return str(owner)
    raw = str(values.get("MODEL_SESSION_SCOPE") or "").strip().lower()
    if raw in SCOPES:
        return raw
    measured = profile.applied("session_scope") if profile is not None else None
    return str(measured) if measured in SCOPES else "conversation"


#: The part of a fan-out the running call belongs to (`as_a_part_of_its_own`); "" outside one.
_PART: contextvars.ContextVar[str] = contextvars.ContextVar("model_session_part", default="")

T = TypeVar("T")
R = TypeVar("R")


def as_a_part_of_its_own(function: Callable[[T], R], item: T) -> R:
    """`function(item)` as one part of a fan-out: its model requests get a session no sibling part shares.

    Run inside the part's own context copy (`mapped_in_this_context`), so the mark ends with the part.
    """
    _PART.set(uuid.uuid4().hex[:10])
    return function(item)


def _the_conversation() -> tuple[str, str]:
    """The running call's run and stage; "" for either not known."""
    run = stage = ""
    try:
        from app.observability.transcript import _run_id_from_config, _stage_from_config

        run, stage = str(_run_id_from_config() or ""), str(_stage_from_config("") or "")
    except Exception:  # noqa: BLE001 - no conversation to name
        pass
    if not run:
        try:
            from app.models.model_pin import current_run_id

            run = current_run_id()
        except Exception:  # noqa: BLE001
            run = ""
    return run, stage


def session_value(run: str, stage: str, part: str, scope: str, fresh: str) -> str:
    """The session a request is sent under (see the module's notes): `<run>:<stage>` for an agent's conversation, with
    `:<part>` in a fan-out; `<run>:<part>` for a fan-out part with no stage; `<run>:<fresh>` for a call with no
    conversation to reuse, and under `request` scope `<run>:<stage>:<fresh>`. The run is kept in front where known."""
    known = ":".join(p for p in (run, stage) if p)
    if scope == "request" or not (stage or part):
        tail = fresh
    else:
        tail = part
    kept = _UNSAFE.sub("_", known)[:_MOST_CHARS - len(tail) - 1]
    return f"{kept}:{tail}" if kept and tail else (kept or tail)


def session_headers(environment: Mapping[str, str] | None = None) -> dict[str, str]:
    """The header naming the running call's session; empty when the setting is off."""
    name = session_header_name(environment)
    if not name:
        return {}
    run, stage = _the_conversation()
    value = session_value(run, stage, _PART.get(), session_scope(environment), uuid.uuid4().hex[:12])
    return {name: value} if value else {}


def with_the_session_named(payload: dict, address: str, environment: Mapping[str, str] | None = None) -> None:
    """Add the session header to a request bound for `address`, when that is a self-hosted model server."""
    if not str(address or "").strip():
        return
    from app.models.endpoints import is_self_hosted

    if not is_self_hosted(address, environment):
        return
    headers = session_headers(environment)
    if headers:
        payload["extra_headers"] = {**(payload.get("extra_headers") or {}), **headers}


__all__ = [
    "DEFAULT_SESSION_HEADER", "SCOPES", "as_a_part_of_its_own", "session_header_name", "session_headers",
    "session_scope", "session_value", "with_the_session_named",
]
