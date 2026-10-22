"""Every worker log line names the run and the stage that wrote it.

The worker's lines read `[time: LEVEL/process] message`, and several runs share
one log over a day of runs and deploys: an audit had to filter by time window
and guess which run a "Reverted defect_fix_1_3" belonged to. Each line now
carries `[run stage]` after the process, from the running graph's config - the
same place the transcript takes them from (`app.observability.transcript`) -
or, outside a node, from the run the worker task is executing. A line that
belongs to no run says `-`.
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from typing import Iterator

#: Celery's own worker format, with the run and the stage after the process.
LOG_FORMAT = "[%(asctime)s: %(levelname)s/%(processName)s] [%(run_id)s %(stage)s] %(message)s"

#: The run a worker task is executing, for lines logged outside a graph node.
_TASK_RUN: contextvars.ContextVar[str | None] = contextvars.ContextVar("task_run_id", default=None)

#: Characters of a run id kept: "run-" and the first eight of its uuid.
RUN_CHARS = 12


@contextmanager
def for_the_run(run_id: str | None) -> Iterator[None]:
    """Name `run_id` on every line logged inside, wherever the graph's config does not."""
    token = _TASK_RUN.set(run_id)
    try:
        yield
    finally:
        _TASK_RUN.reset(token)


def _from_the_graph() -> tuple[str | None, str | None]:
    try:
        from langgraph.config import get_config

        from app.tracing import APP_RUN_ID_KEY, APP_STAGE_KEY

        configurable = (get_config() or {}).get("configurable", {})
        return configurable.get(APP_RUN_ID_KEY), configurable.get(APP_STAGE_KEY)
    except Exception:  # noqa: BLE001 - outside a graph run there is no config
        return None, None


class RunContextFilter(logging.Filter):
    """Sets `record.run_id` and `record.stage`; never drops a record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "run_id") or not hasattr(record, "stage"):
            run, stage = _from_the_graph()
            run = run or _TASK_RUN.get()
            record.run_id = str(run)[:RUN_CHARS] if run else "-"
            record.stage = str(stage) if stage else "-"
        return True


def install(logger: logging.Logger | None = None) -> None:
    """Give every handler of `logger` (the root logger by default) the filter and the format.

    Idempotent: a handler that already has the filter is left alone.
    """
    target = logger or logging.getLogger()
    for handler in target.handlers:
        if any(isinstance(existing, RunContextFilter) for existing in handler.filters):
            continue
        handler.addFilter(RunContextFilter())
        handler.setFormatter(logging.Formatter(LOG_FORMAT))


__all__ = ["LOG_FORMAT", "RunContextFilter", "for_the_run", "install"]
