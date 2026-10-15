"""A stage a restart killed carries on in its own conversation, from its last saved step.

Each visit to a stage starts a new conversation on purpose: a retry or a
revision should not drown in the attempt before it. But a worker that stops -
a deploy, a crash, a restart of the machine - is not a new attempt. Recovery
resumed the run from the last checkpoint of the outer graph, which is before
the stage, and the stage started a new conversation from nothing; its own
conversation, saved step by step, was never read again. Measured on one run:
a deploy that waited for a 10-minute frontier call to return - 47,669 tokens
of the revised specification - restarted the worker 50 seconds later, and the
architect began again at 14k tokens of context instead of 75k.

So the conversation a visit runs in is written down when the visit starts and
crossed out when it returns, however it returns. One still written down when
the stage is entered again was cut off by a stopped worker, and is carried on.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
FILE = ".harness/stage-threads.json"


def _path(root: str | Path) -> Path:
    return Path(root) / FILE


def _read(root: str | Path) -> dict[str, str]:
    try:
        data = json.loads(_path(root).read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(root: str | Path, data: dict[str, str]) -> None:
    try:
        path = _path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    except OSError:
        logger.debug("Could not record the stage's conversation", exc_info=True)


def _key(outer_thread_id: str, stage_name: str) -> str:
    return f"{outer_thread_id}|{stage_name}"


def remember(root: str | Path | None, outer_thread_id: str, stage_name: str, inner_thread_id: str) -> None:
    if not root:
        return
    with _LOCK:
        data = _read(root)
        data[_key(outer_thread_id, stage_name)] = inner_thread_id
        _write(root, data)


def forget(root: str | Path | None, outer_thread_id: str, stage_name: str) -> None:
    if not root:
        return
    with _LOCK:
        data = _read(root)
        if data.pop(_key(outer_thread_id, stage_name), None) is not None:
            _write(root, data)


def cut_off(root: str | Path | None, outer_thread_id: str, stage_name: str, agent: Any) -> tuple[str, bool] | None:
    """(the conversation a stopped worker cut off, whether it had already finished), or None.

    Only a conversation with saved steps counts: one cut off before its first
    step has nothing to carry on, and the stage starts as it always did.
    """
    if not root:
        return None
    inner = _read(root).get(_key(outer_thread_id, stage_name))
    if not inner:
        return None
    try:
        snapshot = agent.get_state({"configurable": {"thread_id": inner}})
    except Exception:  # noqa: BLE001 - no saved conversation to carry on
        return None
    values = getattr(snapshot, "values", None) or {}
    if len(values.get("messages") or []) < 2:
        return None
    # Only a conversation with a step still to take. One that had finished is
    # an answer already given - and a note left behind by a path that never
    # crossed it out would hand a later visit the old answer.
    if not getattr(snapshot, "next", None):
        return None
    return inner, False
