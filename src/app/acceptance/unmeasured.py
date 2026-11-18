"""A measurement the harness could not take is not a product failure.

Deep review 2026-11-18 (A1): a measurement record held test outcomes and a free-text problem, and nothing for "the
harness could not measure". Measured: the sandbox's own memory refusal ("Not enough memory is free in this container")
failed all 18 acceptance criteria of one round, a fix was reverted as "broke 32 tests" and the sprint was planned again;
a registry the build needed could not be resolved ("Could not resolve host: index.crates.io"), was raised as a product
defect, and cost 17 model calls.

A runner's outcome carries `UNMEASURED` (the reason) where its source knows the cause: the sandbox's refusal to start a
command for want of memory. Where the source cannot carry a type - a build or an install whose network could not
resolve a registry, read from what it printed - a small recogniser stands in, and only for a run that reached no test:
a test that ran and failed on its own network call is the product's.

An unmeasured measurement raises no defect, reverts nothing, charges no round and replaces no baseline; it is tried once
more after a short wait, and when still unmeasured it is recorded (log, transcript) for the operator.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

from app.stacks import contract

logger = logging.getLogger(__name__)

#: The key of a runner's outcome that says the command was not measured, and why.
UNMEASURED = "unmeasured"

#: How a note of a measurement not taken begins: an install the network or the container stopped.
NOT_INSTALLED = "The project's dependencies could not be installed for a reason outside the product"

#: Where the last measurement the harness could not take is kept, until one is taken.
RECORD_FILE = f"{contract.HARNESS_DIR}/unmeasured.json"

#: Seconds before the one retry: long enough for a neighbour's command to end and free its memory.
RETRY_AFTER_SECONDS = 30.0

#: The harness's own memory refusal (`tools.resources.enough_headroom`), for an outcome that lost its type.
_THE_HARNESS_REFUSED = "Not enough memory is free in this container"

#: A network that could not resolve a host's name: curl, git and cargo's wording, glibc's, and Node's.
_NAME_RESOLUTION = re.compile(
    r"Could not resolve host\b[^\n]*|Temporary failure in name resolution[^\n]*|\bEAI_AGAIN\b[^\n]*"
)

T = TypeVar("T")


def why(outcome: Any, *, reached_tests: bool = False) -> str:
    """Why `outcome` (a runner's answer) measured nothing about the product; "" when it measured it."""
    if not isinstance(outcome, dict):
        return ""
    typed = str(outcome.get(UNMEASURED) or "").strip()
    if typed:
        return typed
    if reached_tests:
        return ""
    said = "\n".join(str(outcome.get(key) or "") for key in ("error", "stdout", "stderr"))
    if _THE_HARNESS_REFUSED in said:
        return next(line for line in said.splitlines() if _THE_HARNESS_REFUSED in line).strip()[:300]
    resolved = _NAME_RESOLUTION.search(said)
    if resolved:
        return "the network could not resolve a host the build needs: " + resolved.group(0).strip()[:200]
    return ""


def in_the_repairs(repairs: Any) -> str:
    """The note of an install not taken among a measurement's repairs; ""."""
    return next((str(note) for note in repairs or () if str(note).startswith(NOT_INSTALLED)), "")


def once_more(measure: Callable[[], T], reason: Callable[[T], str], wait: float | None = None) -> T:
    """`measure()`, and when it could not measure, once more after a short wait. Never sleeps when it measured."""
    first = measure()
    said = reason(first)
    if not said:
        return first
    logger.warning("The harness could not measure the product (%s); trying once more", said[:200])
    time.sleep(RETRY_AFTER_SECONDS if wait is None else wait)
    return measure()


def record(root: str | Path, stage: str, said: str) -> None:
    """Keep that a measurement could not be taken, in the workspace and the run's transcript. Never raises."""
    logger.error("The harness could not measure the product at %s, twice: %s. Nothing is judged on it; "
                 "the operator may pause the run.", stage, said[:300])
    try:
        path = Path(root) / RECORD_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"stage": stage, "why": said[:1000],
                                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}) + "\n",
                        encoding="utf-8")
    except OSError:
        pass
    from app.observability import defect_ledger

    defect_ledger.note("not measured", stage, detail=said)


def taken(root: str | Path) -> None:
    """A measurement was taken: the record of one that was not is cleared. Never raises."""
    try:
        (Path(root) / RECORD_FILE).unlink(missing_ok=True)
    except OSError:
        pass


def last(root: str | Path) -> str:
    """Why the last measurement could not be taken, when no measurement has been taken since; ""."""
    try:
        return str(json.loads((Path(root) / RECORD_FILE).read_text(encoding="utf-8")).get("why") or "")
    except (OSError, ValueError, AttributeError):
        return ""
