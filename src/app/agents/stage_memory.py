"""Memory that survives an approval pause, keyed by the stage it belongs to.

Every repeat notice in this harness counts something per stage: how many times
a file has returned the same bytes, how many times a listing has answered
identically, how many no-op writes a stage has been forgiven. Each of those
counters lived on the middleware or backend *instance*.

Those instances do not survive. With `auto_approve`, every gated tool -
`write_artifact`, `edit_artifact`, `run_terminal_command` - interrupts the
graph, and the workflow node then runs again from the top on resume, calling
`create_specialist_agent` afresh. A new agent means new middleware, a new
backend, and an empty counter. So a stage that writes a file between two reads
- which is what a working stage does - starts every counter from zero again.

Measured on one run, which had 73 byte-identical repeated tool calls,
32% of its model calls:

    middleware query-repeat notes:      0
    middleware no-op write refusals:    0
    read withheld after five repeats:   0
    ledger command notices:             9

Nine, and all nine from the execution ledger - the one mechanism that keeps
its count in a file. Everything held in memory reported nothing at all, not
because the checks were wrong but because they were counting to one over and
over.

The inner agent's `thread_id` is the stage's identity and is stable across
resumes: `_run_gated_agent` reuses `pending_inner_thread_id` rather than
generating a new one, precisely so a pause resumes the same conversation. That
makes it the right key, and it changes between stages and between restarts of
one stage, which is what "per stage" has always meant here.

Outside a graph run there is no thread id, and callers fall back to their own
instance state - which is what every test does, and what the behaviour was
before this existed.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)

#: Stages kept before the oldest is dropped. A run is a few dozen stages and
#: each holds a handful of digests; this is a ceiling against a process that
#: serves many runs, not a working limit.
MAX_STAGES_REMEMBERED = 64

_MEMORY: OrderedDict[tuple[str, str], dict] = OrderedDict()


#: The key the workflow has declared for the agent it is running, if any. Set
#: around each inner agent invocation and preferred over `get_config`, because
#: under a parallel fan-out `get_config` does not answer per worker.
#:
#: Measured on one run's first milestone, a seven-task parallel sprint. The
#: redundant-read refusals carry an ordinal, and across six concurrent
#: specialists they formed one interleaved sequence:
#:
#:   specialist_backend_2 12, specialist_testing_5 13, specialist_testing_4 14,
#:   specialist_backend_2 15, specialist_testing_6 16, specialist_testing_5 17,
#:   ... specialist_ui_ux_0 33, specialist_testing_5 34
#:
#: while the sequential stages after them each restarted at 12 - `test_round_0`
#: 12-17, `defect_fix_1_0` 12-14. So the key resolved per stage when stages ran
#: one at a time and collapsed to one shared slot when they ran at once: every
#: `Send` in a superstep sees the parent's config, not its own.
#:
#: The cost is not only a wrong number. This memory holds which lines of which
#: files a stage has been given, so a pooled slot means one specialist is
#: refused a read because another specialist read that file, and is told it has
#: "already been given" content it has never seen.
_DECLARED: Any = None


def _declared_key_holder() -> Any:
    """The context variable holding `_DECLARED`, created on first use."""
    global _DECLARED
    if _DECLARED is None:
        import contextvars

        _DECLARED = contextvars.ContextVar("stage_memory_declared_key", default=None)
    return _DECLARED


def remembering(key: str) -> Any:
    """Declare the stage key for everything called inside this block.

    A context manager. `contextvars` copy into the thread or task a fan-out
    starts, so a worker that sets this before invoking its agent is read
    correctly by the tools that agent runs, whichever thread they run on.

    Falls back to nothing if the key is empty, so a caller without one leaves
    the previous behaviour exactly as it was.
    """
    from contextlib import contextmanager

    @contextmanager
    def _scope():
        if not key:
            yield
            return
        holder = _declared_key_holder()
        token = holder.set(str(key))
        try:
            yield
        finally:
            holder.reset(token)

    return _scope()


def current_stage_key() -> str | None:
    """The running stage's stable identity, or None outside a graph run.

    The declared key wins. `get_config` is kept behind it because it is right
    whenever a stage runs alone, and because a caller that never declares one -
    every test, and any path that reaches a tool outside `_run_gated_agent` -
    must keep working as before.
    """
    declared = _declared_key_holder().get()
    if declared:
        return str(declared)
    try:
        from langgraph.config import get_config

        configurable = (get_config() or {}).get("configurable") or {}
        thread = configurable.get("thread_id")
        return str(thread) if thread else None
    except Exception:  # noqa: BLE001 - outside a graph run there is no config
        return None


def store(purpose: str, fallback: dict) -> dict:
    """The dict `purpose` should count in for the running stage.

    `fallback` is returned unchanged when there is no stage to key on, so a
    caller that owns per-instance state keeps using it outside a graph run.
    """
    key = current_stage_key()
    if key is None:
        return fallback
    slot = _MEMORY.get((key, purpose))
    if slot is None:
        slot = {}
        _MEMORY[(key, purpose)] = slot
        while len(_MEMORY) > MAX_STAGES_REMEMBERED:
            _MEMORY.popitem(last=False)
    else:
        _MEMORY.move_to_end((key, purpose))
    return slot


def forget_everything() -> None:
    """Drop all remembered stages. For tests, which must not leak into each other."""
    _MEMORY.clear()


__all__ = [
    "MAX_STAGES_REMEMBERED",
    "current_stage_key",
    "forget_everything",
    "remembering",
    "store",
]


def recall(thread_id: str, purpose: str) -> dict:
    """What `thread_id` remembered for `purpose`, or `{}`.

    `store` answers for the stage that is running. This answers for one that
    has finished, which is what a restart needs: the attempt that just died
    holds the only record of what it read and ran, and its key is about to stop
    being anybody's `current_stage_key`.

    Returns a copy. The caller is summarising a dead attempt, not continuing
    it, and handing out the live dict would let a summary mutate the record it
    is summarising.
    """
    slot = _MEMORY.get((thread_id, purpose))
    return dict(slot) if slot else {}
