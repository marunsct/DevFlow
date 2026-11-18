"""A mechanism that did not run, said so: in the log once and in the run's transcript every time (deep review 2026-11-18, D5).

The graph has a few hundred `except Exception` handlers that log at debug and carry on. Most guard something optional,
but some guard a check, a probe, a gate, a measurement or a snapshot - and when one of those fails the run goes on as
if it had run. That is how a feature is "built but silent": nothing in the run's records says it never fired.

`degraded(name, error, **context)` is what such a handler calls instead of its debug line. It changes nothing in the
handler's control flow: it logs at warning the first time `name` fails in a run (debug after), and appends a
`degraded` record to the run's transcript naming the mechanism, the error's type and a short message. The run doctor
(`run_doctor.diagnose`) sums them per mechanism, so an audit sees which mechanisms did not run, and how often.

**Never raises.** It is called from inside exception handlers that must go on exactly as before.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

#: The transcript kind of a degraded mechanism's record.
KIND = "degraded"
#: Characters of the error's message and of each context value kept in a record.
MESSAGE_CHARS = 300
#: Records kept per mechanism per run in one process: a mechanism failing in a loop must not flood the transcript.
MAX_RECORDS_PER_RUN = 500
#: (run, mechanism) pairs remembered before the memory is cleared (a worker runs for days).
_REMEMBERED = 20_000

#: Fields of a record that a context value never replaces.
_RESERVED = frozenset({"at", "run_id", "stage", "kind", "mechanism", "error_type", "message"})

_seen: dict[tuple[str, str], int] = {}
_lock = threading.Lock()


def _short(value: Any) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= MESSAGE_CHARS else text[: MESSAGE_CHARS - 3] + "..."


def degraded(name: str, error: BaseException | None = None, **context: Any) -> None:
    """Record that the mechanism `name` did not run (or ran in part) in the current run. Never raises."""
    try:
        from app.observability.log_context import current_run

        run_id, stage = current_run()
        with _lock:
            if len(_seen) > _REMEMBERED:
                _seen.clear()
            key = (str(run_id or "-"), name)
            count = _seen[key] = _seen.get(key, 0) + 1
        error_type = type(error).__name__ if error is not None else ""
        message = _short(error) if error is not None else ""
        if count == 1:
            logger.warning("Degraded: %s did not run%s", name, f" ({error_type}: {message})" if error_type else "",
                           exc_info=error if error is not None else None)
        else:
            logger.debug("Degraded again (%d): %s", count, name, exc_info=error if error is not None else None)
        if count <= MAX_RECORDS_PER_RUN and run_id:
            from app.observability.transcript import record

            record(run_id, str(stage or ""), KIND, mechanism=name, error_type=error_type, message=message,
                   **{key: _short(value) for key, value in context.items() if key not in _RESERVED})
    except Exception:  # noqa: BLE001 - recording a failure must never become one
        return


__all__ = ["KIND", "degraded"]
