"""Whether an outside source refused, and until when it is left alone: one breaker per source (plan KS.3, LF.1294).

Measured before it: every source's reader returned an empty list for any status other than 200, and the fetch threw
the response headers away, so a source that refused - Stack Exchange's throttle, GitHub's rate limit, a 429 - read as
"nothing found" and was asked again by the next lookup, inside the very window it had named. Each source states its
own rule, and this module reads them:

- any source: HTTP 429, or a 403 or 503 with `Retry-After`, is a refusal; `Retry-After` (seconds or a date) says
  until when;
- GitHub: `x-ratelimit-remaining: 0` with `x-ratelimit-reset` (a Unix time) - a refusal on a 403 or 429, and on a
  200 the next request would be one, so the source is held until the reset all the same;
- Stack Exchange: a `backoff` field in the body holds the source for that many seconds even on an answer, and an
  error body with `error_id` 502 (throttle violation) is a refusal.

A refusal with no stated time holds the source for an exponential backoff with jitter, capped. An answer clears the
count. The holds are kept in `DATA_DIR/lookups/holds.json`, so every process on one host respects them; a held
source is skipped and the lookup says "refused until ..." - never "0 found" - and a refusal is never remembered as
"nothing found" (`lookups`).
"""

from __future__ import annotations

import email.utils
import json
import os
import random
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Seconds of the first hold after a refusal that states no time; doubled for each refusal in a row.
FIRST_BACKOFF = 60.0
#: The longest hold a refusal that states no time earns.
LONGEST_BACKOFF = 3_600.0
#: The longest hold any stated time is taken for: a broken header never holds a source for days.
LONGEST_STATED = 86_400.0
#: Share of a backoff added or taken away at random, so concurrent runs do not come back at the same second.
JITTER = 0.2

#: What one request to a source came to.
ANSWERED = "answered"
NOTHING_FOUND = "nothing found"
REFUSED = "refused"
FAILED = "failed"

_LOCK = threading.Lock()


@dataclass(frozen=True)
class Verdict:
    """What one reply says of its source: refused or not, and how many seconds it asks to be left alone (0 for none
    stated, `None` for no hold at all)."""

    refused: bool
    hold: float | None


class Refused(Exception):
    """A source refused a request, or is held from an earlier refusal: `source` and `until` (a Unix time)."""

    def __init__(self, source: str, until: float, status: int = 0) -> None:
        self.source, self.until, self.status = source, until, status
        super().__init__(f"{source} refused{f' ({status})' if status else ''} until {_clock(until)}")


def _clock(at: float) -> str:
    return time.strftime("%H:%M UTC", time.gmtime(at))


def _number(text: Any) -> float | None:
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return None


def _retry_after(value: Any, now: float) -> float | None:
    """Seconds `Retry-After` asks for: a number of seconds, or an HTTP date; None when absent or unreadable."""
    if value in (None, ""):
        return None
    seconds = _number(value)
    if seconds is not None:
        return max(0.0, seconds)
    try:
        when = email.utils.parsedate_to_datetime(str(value))
    except (TypeError, ValueError):
        return None
    return max(0.0, when.timestamp() - now) if when is not None else None


def _body(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def read(status: int, headers: dict[str, str] | None, body: str = "", *, now: float | None = None) -> Verdict:
    """What one reply says of its source (see the module's note)."""
    now = time.time() if now is None else now
    found = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    retry = _retry_after(found.get("retry-after"), now)
    remaining = _number(found.get("x-ratelimit-remaining"))
    reset = _number(found.get("x-ratelimit-reset"))
    until_reset = max(0.0, reset - now) if reset is not None and remaining == 0 else None
    said = _body(body) if body and body.lstrip().startswith("{") else {}
    backoff = _number(said.get("backoff"))
    throttled = str(said.get("error_id") or "") == "502" or str(said.get("error_name") or "") == "throttle_violation"
    if status == 429 or (status in {403, 503} and (retry is not None or until_reset is not None)) or throttled:
        stated = [s for s in (retry, until_reset, backoff) if s is not None]
        return Verdict(True, max(stated) if stated else 0.0)
    held = [s for s in (until_reset, backoff) if s]
    return Verdict(False, max(held) if held else None)


# --- the holds, shared by the processes on one host ------------------------------------------------------------------

def _path() -> Path:
    return Path(os.environ.get("DATA_DIR") or "data") / "lookups" / "holds.json"


def _read_holds() -> dict[str, dict[str, float]]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def _write_holds(holds: dict[str, dict[str, float]]) -> None:
    try:
        _path().parent.mkdir(parents=True, exist_ok=True)
        temporary = _path().with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(holds), encoding="utf-8")
        temporary.replace(_path())
    except OSError:
        pass


def held_until(source: str, *, now: float | None = None) -> float:
    """The Unix time until which `source` is left alone, or 0 when it may be asked now."""
    now = time.time() if now is None else now
    until = float((_read_holds().get(source) or {}).get("until") or 0)
    return until if until > now else 0.0


def hold(source: str, seconds: float | None, *, refused: bool, now: float | None = None) -> float:
    """Leave `source` alone for `seconds` (a refusal with 0 earns the backoff); the time it is held until."""
    now = time.time() if now is None else now
    with _LOCK:
        holds = _read_holds()
        entry = holds.get(source) or {}
        refusals = int(entry.get("refusals") or 0) + (1 if refused else 0)
        if refused and not seconds:
            backoff = min(LONGEST_BACKOFF, FIRST_BACKOFF * 2 ** max(0, refusals - 1))
            seconds = backoff * (1 + random.uniform(-JITTER, JITTER))
        until = now + min(float(seconds or 0), LONGEST_STATED)
        holds[source] = {"until": max(until, float(entry.get("until") or 0)), "refusals": refusals}
        _write_holds(holds)
        return holds[source]["until"]


def answered(source: str) -> None:
    """`source` answered: the count of refusals in a row starts again (a hold it stated stays)."""
    with _LOCK:
        holds = _read_holds()
        if int((holds.get(source) or {}).get("refusals") or 0):
            holds[source] = {**holds[source], "refusals": 0}
            _write_holds(holds)


def after(source: str, status: int, headers: dict[str, str] | None, body: str = "") -> None:
    """Act on one reply from `source`: hold it as the reply asks; raise `Refused` when it refused."""
    verdict = read(status, headers, body)
    if verdict.refused:
        raise Refused(source, hold(source, verdict.hold, refused=True), status)
    if verdict.hold:
        hold(source, verdict.hold, refused=False)
    if 200 <= status < 300:
        answered(source)


__all__ = ["ANSWERED", "FAILED", "NOTHING_FOUND", "REFUSED", "Refused", "Verdict", "after", "answered", "hold",
           "held_until", "read"]
