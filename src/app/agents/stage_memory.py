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

 Everything held in memory reported nothing at all, not
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


def current_stage_key() -> str | None:
    """The running stage's stable identity, or None outside a graph run."""
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


__all__ = ["MAX_STAGES_REMEMBERED", "current_stage_key", "forget_everything", "store"]


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
