"""Facts asked of public data services - OSV's advisories, endoflife.date's support dates (plan HK.6, HK.8, LF.1300).

One request path for both: the request leaves by the lookups' own fetch (`lookups._get`, which the tests stand in
for), a service that refuses is held until the time it gave (`source_breaker`, plan KS.3), and anything else that
goes wrong - no network, a timeout, an answer that is not data - is `NotKnown`, never an empty answer: a caller says
"not known", not "none". What a caller sends is recorded by the one outbound gate (`app.tools.outbound`); only
public package names, their versions, advisory ids and product names are ever sent. An answer is kept in this process
for the time the caller gives, so a run asking again within it costs no request.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

_KEPT: dict[tuple[str, str], tuple[float, Any]] = {}
_LOCK = threading.Lock()
#: Answers kept at most; the oldest go first.
MOST_KEPT = 512
#: Seconds a service that could not be reached at all is left alone.
UNREACHABLE_HOLD = 300.0


class NotKnown(Exception):
    """A public data service could not answer: refused, unreachable, or answered with nothing readable."""


def ask(source: str, url: str, body: Any = None, *, channel: str, said: str, removed: int = 0,
        kept_for: float = 0.0) -> Any:
    """The JSON a service answers for `url` (a POST of `body` when one is given); None for its "no such thing" (404).
    A request that leaves is one `outbound` record (`channel`, `said`: what it asks, in words; `removed`: names kept
    back); an answer kept, or a hold, sends nothing and records nothing. Raises `NotKnown` with the reason when it
    cannot answer."""
    from urllib.parse import urlsplit

    from app.tools import lookups, outbound, source_breaker

    sent = json.dumps(body, sort_keys=True) if body is not None else None
    key = (url, sent or "")
    if kept_for:
        with _LOCK:
            kept = _KEPT.get(key)
        if kept and time.time() - kept[0] < kept_for:
            return kept[1]
    until = source_breaker.held_until(source)
    if until:
        raise NotKnown(f"{source} not asked until {time.strftime('%H:%M UTC', time.gmtime(until))}: it refused or "
                       "could not be reached")
    headers = {"Accept": "application/json"}
    outbound.record(channel, said, to=urlsplit(url).hostname or "", removed=removed)
    try:
        got = lookups._get(url, headers) if sent is None else lookups._get(url, headers, sent)  # noqa: SLF001
        status, text, answered = lookups._reply(got)  # noqa: SLF001
        source_breaker.after(source, status, answered, text)
    except source_breaker.Refused as refused:
        raise NotKnown(str(refused)) from refused
    except Exception as error:  # noqa: BLE001 - no network, a timeout: not known
        # Left alone a while, so every install of a run with no network does not wait on it again.
        source_breaker.hold(source, UNREACHABLE_HOLD, refused=False)
        raise NotKnown(f"{source} could not be read ({type(error).__name__})") from error
    if status == 404:
        data = None
    elif status != 200:
        raise NotKnown(f"{source} answered {status}")
    else:
        try:
            data = json.loads(text)
        except ValueError as error:
            raise NotKnown(f"{source} answered with nothing readable") from error
    if kept_for:
        with _LOCK:
            if len(_KEPT) >= MOST_KEPT:
                _KEPT.pop(min(_KEPT, key=lambda k: _KEPT[k][0]))
            _KEPT[key] = (time.time(), data)
    return data


def forget() -> None:
    """Drop every kept answer."""
    with _LOCK:
        _KEPT.clear()


__all__ = ["NotKnown", "ask", "forget"]
