"""A fixer's write is followed by the defect's own tests, and the result is in the write's reply (plan AY step 3, behind `VERIFY_AFTER_WRITE`).

A fix stage in the agent loop wrote, then ran the whole suite itself to see
whether the write worked, or did not run it and answered: measured on one
run, a fixer took 42 calls on one defect, most of them reading and running to
find out what the harness could have told it. With the switch on, each
successful write in a fix stage the harness is watching runs that defect's
own tests (`_the_defect_s_tests_pass`) and appends one line - they pass, or
they still fail - to what the write tool returns. No model call; at most
`MOST_CHECKS` per stage, so the tests never become the stage's cost.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `VERIFY_AFTER_WRITE` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Checks run per stage, at most.
MOST_CHECKS = 6
#: The tools whose success changes the product's files.
WRITES = frozenset({"write_artifact", "edit_artifact", "write_file", "edit_file"})
PASSED = "The harness ran this defect's own tests after the write: they pass now."
FAILING = "The harness ran this defect's own tests after the write: they still fail."

_lock = threading.Lock()
_watched: dict[tuple[str, str], list[Any]] = {}


def enabled() -> bool:
    return is_on("VERIFY_AFTER_WRITE", ON_BY_DEFAULT)


@contextmanager
def watching(run_id: str | None, stage: str, check: Callable[[], bool | None]) -> Iterator[None]:
    """While inside, a write in `stage` of `run_id` runs `check`. Nothing when off."""
    key = (str(run_id or ""), stage)
    if enabled():
        with _lock:
            _watched[key] = [check, 0]
    try:
        yield
    finally:
        with _lock:
            _watched.pop(key, None)


def _the_check(run_id: str | None, stage: str) -> Callable[[], bool | None] | None:
    with _lock:
        entry = _watched.get((str(run_id or ""), stage))
        if entry is None or entry[1] >= MOST_CHECKS:
            return None
        entry[1] += 1
        return entry[0]


def after_a_write(tool: str, result: Any, run_id: str | None, stage: str) -> Any:
    """`result` with the defect's test outcome appended, when it is a watched stage's successful write."""
    if tool not in WRITES or getattr(result, "status", None) == "error" or not isinstance(getattr(result, "content", None), str):
        return result
    check = _the_check(run_id, stage)
    if check is None:
        return result
    try:
        outcome = check()
    except Exception:  # noqa: BLE001 - the write stands as it was
        logger.debug("Could not run the defect's tests after a write", exc_info=True)
        return result
    if outcome is None:
        return result
    result.content = result.content.rstrip() + "\n" + (PASSED if outcome else FAILING)
    return result


def build_middleware() -> Any:
    """The middleware that runs the check after a write; a pass-through when nothing is watched."""
    from langchain.agents.middleware import AgentMiddleware

    from app.observability.transcript import _run_id_from_config, _stage_from_config

    class VerifyAfterWriteMiddleware(AgentMiddleware):
        name = "VerifyAfterWriteMiddleware"

        def wrap_tool_call(self, request: Any, handler: Any) -> Any:
            result = handler(request)
            if not _watched:
                return result
            call = getattr(request, "tool_call", None) or {}
            return after_a_write(str(call.get("name") or ""), result, _run_id_from_config(), _stage_from_config(""))

    return VerifyAfterWriteMiddleware()


__all__ = ["FAILING", "MOST_CHECKS", "ON_BY_DEFAULT", "PASSED", "WRITES", "after_a_write", "build_middleware",
           "enabled", "watching"]
