"""A model server that is briefly unreachable is waited for, not failed on.

Measured: a run failed outright on `OpenAIAPIError: model_unavailable`. The balancer in front of the owner's two model
instances marked both unhealthy for a moment while the host swapped models, answered 503 with that text, and both
instances answered again within about three minutes - but the client's quick retries were spent in four seconds and
the stage's own retries did not take that text for a passing fault, so the run ended.

So an answer that says the server cannot be reached right now - a balancer's `model_unavailable` or "no routable
endpoints", a proxy's 502, 503 or 504 that came back at once, a refused connection - is asked again with a growing
pause, until `MODEL_OUTAGE_WAIT_SECONDS` (default ten minutes) have passed since the first; then the error is raised as
before and the stage fails as it always did. Only a run's calls wait: a check made outside a run is answered at once. A slow 502 or 504, or a timeout, is not an outage: that is a reply cut off
for taking too long, which `after_a_failed_call` answers by asking for less.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: How long an outage is waited for, in all, unless `MODEL_OUTAGE_WAIT_SECONDS` says otherwise.
WAIT_SECONDS = 600.0
#: A failure slower than this is a reply that took too long, not a server that is not there.
QUICK_SECONDS = 60.0
#: The first pause, doubled each time up to `LONGEST_PAUSE`.
FIRST_PAUSE = 2.0
LONGEST_PAUSE = 30.0

#: What a balancer or server says when no instance can take the request right now.
_SAID = ("model_unavailable", "model unavailable", "no routable endpoints", "no healthy upstream", "no available server",
         "connection refused", "service unavailable", "temporarily unavailable")
#: The statuses a server or a proxy answers with when the server behind it is not there.
_UNAVAILABLE = frozenset({502, 503, 504})


def wait_seconds() -> float:
    """How long an outage is waited for in all."""
    try:
        return max(0.0, float(os.environ.get("MODEL_OUTAGE_WAIT_SECONDS") or WAIT_SECONDS))
    except ValueError:
        return WAIT_SECONDS


def _status(error: BaseException) -> Any:
    return getattr(error, "status_code", None) or getattr(getattr(error, "response", None), "status_code", None)


def is_an_outage(error: BaseException, elapsed: float = 0.0) -> bool:
    """Whether `error` says the model server cannot be reached right now, as opposed to a refusal of the request or a
    reply cut off for taking too long."""
    if elapsed >= QUICK_SECONDS or "timeout" in type(error).__name__.lower():
        return False
    chain = [error, *(e for e in (error.__cause__, error.__context__) if e is not None)]
    text = " ".join(str(e) for e in chain).lower()
    if any(said in text for said in _SAID):
        return True
    if _status(error) in _UNAVAILABLE:
        return True
    # A connection that could not be made at all (a timeout is a subclass, and was ruled out above).
    try:
        import openai

        return isinstance(error, openai.APIConnectionError)
    except ImportError:
        return False


class Outage:
    """One call's wait through an outage: `pause_after(error)` is how long to wait before asking again, or None to
    raise the error. `clock` and `sleep` are the process's own unless a test gives its own."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._began: float | None = None
        self._tries = 0

    def pause_after(self, error: BaseException, elapsed: float = 0.0) -> float | None:
        if not is_an_outage(error, elapsed) or not _in_a_run():
            return None
        now = self._clock()
        if self._began is None:
            self._began = now
            _noted("began", str(error)[:200])
        waited = now - self._began
        if waited >= wait_seconds():
            _noted("gave up", str(error)[:200], waited)
            return None
        pause = min(LONGEST_PAUSE, FIRST_PAUSE * 2 ** self._tries, max(0.0, wait_seconds() - waited))
        self._tries += 1
        logger.warning("The model server cannot be reached (%s); asking again in %.0f s, %.0f s into the outage",
                       str(error)[:120], pause, waited)
        return pause

    def answered(self) -> None:
        """The server answered: an outage that began is over."""
        if self._began is not None:
            _noted("answered again", "", self._clock() - self._began)
            self._began, self._tries = None, 0


def _in_a_run() -> bool:
    """Whether the call is a run's: a check made outside one (the settings page's diagnosis of a model, a health
    check) is answered at once, as before, rather than held for minutes."""
    try:
        from app.observability.log_context import current_run

        return bool(current_run()[0])
    except Exception:  # noqa: BLE001
        return False


def _noted(event: str, error: str, waited: float = 0.0) -> None:
    """One `model_outage` record in the run's transcript, for the audit. Never raises."""
    try:
        from app.observability.log_context import current_run
        from app.observability.transcript import record

        run, stage = current_run()
        record(run, str(stage or ""), "model_outage", event=event, error=error, waited_seconds=round(waited, 1))
    except Exception:  # noqa: BLE001 - a record must never cost the call
        pass


def through_an_outage(call: Callable[[], Any], *, sleep: Callable[[float], None] = time.sleep,
                      clock: Callable[[], float] = time.monotonic, between: Callable[[], None] | None = None) -> Any:
    """`call()`, asked again through an outage of the model server for up to `wait_seconds()`. `between` runs before
    each new attempt (a stopped run raises there, rather than wait on)."""
    outage = Outage(clock=clock)
    while True:
        started = clock()
        try:
            result = call()
        except Exception as error:
            pause = outage.pause_after(error, clock() - started)
            if pause is None:
                raise
            sleep(pause)
            if between is not None:
                between()
            continue
        outage.answered()
        return result


__all__ = ["FIRST_PAUSE", "LONGEST_PAUSE", "Outage", "QUICK_SECONDS", "WAIT_SECONDS", "is_an_outage",
           "through_an_outage", "wait_seconds"]
