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
import re
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from app.observability.degraded import degraded
from app.switches import is_on

logger = logging.getLogger(__name__)

#: `VERIFY_AFTER_WRITE` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Checks run per stage, at most.
MOST_CHECKS = 6
#: The tools whose success changes the product's files.
WRITES = frozenset({"write_artifact", "edit_artifact", "write_file", "edit_file", "replace_lines"})
#: Measured on a gate run: a fixer whose defect's tests passed at its twentieth
#: call went on for eighteen more, fixing failures other fixers were given,
#: and broke the file it had fixed. Passing is the moment to answer.
PASSED = (
    "The harness ran this defect's own tests after the write: they pass now. Your defect is fixed: "
    "give your answer now. Other failing tests are other defects, each with its own fixer; leave them."
)
FAILING = "The harness ran this defect's own tests after the write: they still fail."

#: How a write that did not happen answers: `{"error": ...}`, or a refusal.
_A_WRITE_THAT_DID_NOT_HAPPEN = re.compile(
    r'\s*(?:\{\s*"error"|Error\b|Refusing\b|\{[^{}]*"status":\s*"(?:unchanged|already_applied)")')

_lock = threading.Lock()
_watched: dict[tuple[str, str], list[Any]] = {}


def enabled() -> bool:
    return is_on("VERIFY_AFTER_WRITE", ON_BY_DEFAULT)


@contextmanager
def watching(
    run_id: str | None, stage: str, check: Callable[[], bool | None], *,
    says: tuple[str, ...] | None = None, most: int | None = None, checkpoints_in: str | Path | None = None,
    then: Callable[[], str] | None = None,
) -> Iterator[None]:
    """While inside, a write in `stage` of `run_id` runs `check`. Nothing when off.

    `says` is the line appended when the check passes and when it does not, for a check that is not the defect's
    tests (a deliberate change the new tests must notice), and a third, when given, for a check that could not say;
    `most` is the checks the stage gets, for one that costs more.
    `checkpoints_in`, a fix made alone's workspace: a write the check passes is kept there as the fix's best so far
    (`best_checkpoint`).
    `then`, after a check that does not pass: what the tests do now - their first failure and the server's error
    (`first_failure.after_a_write`, FX.7) - added below the line that says they still fail.
    """
    key = (str(run_id or ""), stage)
    if enabled():
        with _lock:
            _watched[key] = [check, 0, says or (PASSED, FAILING), MOST_CHECKS if most is None else most, checkpoints_in,
                             then]
    try:
        yield
    finally:
        with _lock:
            _watched.pop(key, None)


def _the_check(
    run_id: str | None, stage: str,
) -> tuple[Callable[[], bool | None], tuple[str, ...], str | Path | None, Callable[[], str] | None] | None:
    with _lock:
        entry = _watched.get((str(run_id or ""), stage))
        if entry is None or entry[1] >= entry[3]:
            return None
        entry[1] += 1
        return entry[0], entry[2], entry[4], entry[5]


def after_a_write(tool: str, result: Any, run_id: str | None, stage: str) -> Any:
    """`result` with the defect's test outcome appended, when it is a watched stage's successful write."""
    if tool not in WRITES or getattr(result, "status", None) == "error" or not isinstance(getattr(result, "content", None), str):
        return result
    # A refused or failed write answers as a successful tool message with its
    # error in the content; nothing changed, so nothing is worth measuring.
    if _A_WRITE_THAT_DID_NOT_HAPPEN.match(result.content):
        return result
    found = _the_check(run_id, stage)
    if found is None:
        return result
    check, says, checkpoints_in, then = found
    try:
        outcome = check()
    except Exception as failure:  # noqa: BLE001 - the write stands as it was
        degraded("verify_after_write", failure)
        return result
    if outcome is None and len(says) < 3:
        return result
    if outcome and checkpoints_in is not None:
        from app.graph import best_checkpoint

        best_checkpoint.record(checkpoints_in, run_id, stage)
    said = says[2] if outcome is None else says[0] if outcome else says[1]
    if not outcome and then is not None:
        try:
            now = then()
        except Exception as failure:  # noqa: BLE001 - the line alone, as before
            degraded("verify_after_write.then", failure)
            now = ""
        if now:
            said += "\n" + now
    result.content = result.content.rstrip() + "\n" + said
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
