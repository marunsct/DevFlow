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
"""
from __future__ import annotations

import os
import re
import uuid
from collections.abc import Mapping

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
    """`MODEL_SESSION_SCOPE`: `request` for a fresh session per request; `conversation` otherwise."""
    values = os.environ if environment is None else environment
    raw = str(values.get("MODEL_SESSION_SCOPE") or "").strip().lower()
    return raw if raw in SCOPES else "conversation"


def _the_conversation() -> str:
    """`<run>:<stage>` of the running call; the run or the stage alone where only one is known; "" outside both."""
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
    value = ":".join(part for part in (run, stage) if part)
    return _UNSAFE.sub("_", value)[:_MOST_CHARS]


def session_headers(environment: Mapping[str, str] | None = None) -> dict[str, str]:
    """The header naming the running call's session; empty when the setting is off, or, by conversation, when no
    conversation is known."""
    name = session_header_name(environment)
    if not name:
        return {}
    conversation = _the_conversation()
    if session_scope(environment) == "request":
        # The conversation kept in front for the balancer's own log; the fresh part makes every request a new session.
        fresh = uuid.uuid4().hex[:12]
        return {name: f"{conversation}:{fresh}" if conversation else fresh}
    return {name: conversation} if conversation else {}


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
    "DEFAULT_SESSION_HEADER", "SCOPES", "session_header_name", "session_headers", "session_scope",
    "with_the_session_named",
]
