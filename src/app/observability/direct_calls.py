"""Model calls made outside an agent loop, recorded as the run's own.

Fast delivery drafts files and rewrites fixes with one model call each, in a
thread pool, and those calls carried no callbacks: measured on one gate run,
61 drafted files and every rewrite were missing from the transcript, the cost
and the activity stream, so the run's KPIs counted 16 build calls and "neither
model nor tool busy" 40% of the time; and a pool thread does not inherit the
caller's context, so even the call gate named their run "none".
"""
from __future__ import annotations

import contextvars
import logging
from typing import Any, Callable, Iterable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


def config_for_this_run(stage: str) -> dict[str, Any]:
    """`invoke`'s keyword arguments to record a direct call as this run's: `{"config": ...}`, or {} outside a run."""
    try:
        from app.observability.log_context import _TASK_RUN, _from_the_graph
        from app.server.agent_stream import build_activity_callbacks

        run, here = _from_the_graph()
        run = run or _TASK_RUN.get()
        if not run:
            return {}
        callbacks = build_activity_callbacks(str(run), str(here or stage))
        return {"config": {"callbacks": callbacks}} if callbacks else {}
    except Exception:  # noqa: BLE001 - a record must never cost the call
        logger.debug("Could not build the callbacks for a direct model call", exc_info=True)
        return {}


def mapped_in_this_context(pool: Any, function: Callable[[T], R], items: Iterable[T]) -> list[R]:
    """`pool.map(function, items)`, each call run in a copy of the caller's context.

    One copy per call, taken here in the caller's thread: a context cannot be
    entered by two threads at once.
    """
    jobs = [(contextvars.copy_context(), item) for item in items]
    return list(pool.map(lambda job: job[0].run(function, job[1]), jobs))


__all__ = ["config_for_this_run", "mapped_in_this_context"]
