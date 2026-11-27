"""The product builds before the testing work order starts (PA.3).

Measured over three small runs: the unit-test writer was sent to a product that did not build. It had 25 writes
refused (product files, each a builder's) beside 32 writing calls, and its answers carried 40 blockers and 41 defects
that restated compiler errors with the fix written out - work the builder of the file had to do anyway, a stage later.

So when the dispatcher reaches a testing work order and every other work order of the plan has handed over (drafted
or built by the agent loop), the harness builds the product first, with the checks it already runs after a stage
writes: the compiler where the language has one (`compiler_check`), the pack's type check, and the language service
over the files the work orders list (`workflow._diagnostics_in_files_touched`). An error in a product file goes to
the builder whose work order lists the file - or, when none does, the stage that created it - with the build's output
(bounded), and the testing work order waits. At most `MOST_SEND_BACKS` times a plan attempt; then, or when no builder
owns the failing files, the testing work order starts with the failure recorded in the ledger (`loop.sh effects`).

Errors in test files are the testing work order's own and do not hold it. Nothing here names a language, a framework
or a kind of product.
"""

from __future__ import annotations

import logging
import re
from types import SimpleNamespace
from typing import Any

logger = logging.getLogger(__name__)

#: How often the builders are sent back for the build before the testing work order starts anyway.
MOST_SEND_BACKS = 2
#: How many of the build's error lines go to one builder, and how much of each.
MOST_LINES = 12
MOST_LINE_CHARS = 400

#: `builders_sent_back` entries: each send-back (numbered), and "the testing work order started anyway".
SENT_MARK = "the build before testing"
WENT_ON_MARK = "the build before testing: went on"

#: The ledger events.
SENT_EVENT = "sent back to its builder: the product does not build"
WENT_ON_EVENT = "testing work order started on a product that does not build"

HEADING = "The product does not build"
OPENING = ("Every builder of this plan has handed over, and before its unit tests are written the harness built the "
           "product. The build reports these errors in your files:")
CLOSING = ("Correct each one in your own files so that the product builds, then check it as your work order says. "
           "Where an error comes from another file, say which one and why in your report and leave that file as it is.")

_TESTING_WORK_ORDER = "specialist_testing_"
_THE_FILE = re.compile(r"^\s*-\s*In\s+`([^`]+)`")


def _stage(task: Any, index: int) -> str:
    from app.graph.workflow import _specialist_stage_name

    return _specialist_stage_name(task, index)


def is_a_testing_work_order(stage: str) -> bool:
    return str(stage or "").startswith(_TESTING_WORK_ORDER)


def _sent_so_far(state: Any) -> int:
    return sum(1 for mark in (state.get("builders_sent_back") or [])
               if str(mark).startswith(SENT_MARK) and mark != WENT_ON_MARK)


def _the_build_s_errors(state: Any, root: str, builders: dict[str, Any]) -> list[str]:
    """The build's error lines in product files the builders' work orders list; [] when it builds or cannot say."""
    from app.analysis.file_kinds import classify_file
    from app.graph.unfinished_build import product_sources
    from app.graph.workflow import MOST_DIAGNOSTICS_FOR_A_PASS, _diagnostics_in_files_touched
    from app.tools.testing_blockers import _lists

    files = [path for path in product_sources(root) if any(_lists(task, path) for task in builders.values())]
    if not files:
        return []
    found = _diagnostics_in_files_touched(
        state, {"messages": []}, SimpleNamespace(changed_files=files), "build_check", most=MOST_DIAGNOSTICS_FOR_A_PASS)
    try:
        from app.graph.builder_facts import compiler_lines

        found += [line for line in compiler_lines(root, files) if line not in found]
    except Exception:  # noqa: BLE001 - the checks above stand
        logger.debug("Could not run the pack's type check before the testing work order", exc_info=True)
    kept = []
    for line in found:
        match = _THE_FILE.match(line)
        if match and classify_file(match.group(1)) == "application":
            kept.append(line)
    return kept


def _bounded(line: str) -> str:
    flat = " ".join(str(line).split())
    return flat if len(flat) <= MOST_LINE_CHARS else flat[: MOST_LINE_CHARS - 3].rstrip() + "..."


def _shown(lines: list[str]) -> list[str]:
    """Each error line bounded, and the known cause it carries kept whole beneath it, once in the note.

    A cause follows its error on the same line, and the two ran past the bound together: the cut fell in the cause, the
    part the builder acts on (on a Rust run, axum's E0195 error line is some 210 characters and its cause 600).
    """
    from app.stacks.known_errors import KNOWN_CAUSE

    out, said = [], set()
    for line in lines:
        error, *causes = str(line).split(KNOWN_CAUSE)
        out.append(_bounded(error))
        for cause in (" ".join(cause.split()) for cause in causes):
            if cause and cause not in said:
                said.add(cause)
                out.append(f"  {KNOWN_CAUSE} {cause}")
    return out


def the_note(lines: list[str]) -> str:
    """What a builder sent back for the build reads, added to its work order's request."""
    shown = "\n".join(_shown(lines[:MOST_LINES]))
    return f"\n\n--- {HEADING} ---\n{OPENING}\n{shown}\n{CLOSING}"


def _noted(event: str, stage: str, state: Any, detail: str) -> None:
    from app.observability import defect_ledger

    defect_ledger.note(event, stage, sprint=state.get("current_sprint_index", 0), detail=detail[:600])


def before_the_testing_work_order(state: Any, testing_stage: str) -> dict[str, Any] | None:
    """What to do before `testing_stage` starts: None to start it; an update with `unfinished_orders` that sends the
    builders of the failing files back first; or an update that only marks that it starts on a failing build.

    Never raises: a build that cannot be checked starts the testing work order as before.
    """
    try:
        marks = list(state.get("builders_sent_back") or [])
        if WENT_ON_MARK in marks or not is_a_testing_work_order(testing_stage):
            return None
        if state.get("pending_inner_thread_id") or state.get("pending_decision"):
            return None  # a stage resuming after a pause: the check ran before it started
        root = str(getattr(state.get("repository"), "root_path", "") or "")
        tasks = list(getattr(state.get("milestone_plan"), "delegated_tasks", None) or [])
        if not root or not tasks:
            return None
        from app.graph.unfinished_build import pending

        builders = {_stage(task, index): task for index, task in enumerate(tasks)
                    if not is_a_testing_work_order(_stage(task, index))}
        done = set(state.get("specialist_outputs") or {}) - pending(state)
        if not builders or any(stage not in done for stage in builders):
            return None
        errors = _the_build_s_errors(state, root, builders)
        if not errors:
            return None
        from app.tools.testing_blockers import owner_of

        by_owner: dict[str, list[str]] = {}
        for line in errors:
            match = _THE_FILE.match(line)
            owner = owner_of(match.group(1), builders, refused_to=testing_stage, root=root) if match else None
            if owner is not None:
                by_owner.setdefault(owner, []).append(line)
        sent = _sent_so_far(state)
        if sent >= MOST_SEND_BACKS or not by_owner:
            why = "sent back the most times allowed" if by_owner else "no builder of this plan owns the failing files"
            logger.warning("The product does not build (%s); %s starts anyway: %s", why, testing_stage,
                           "; ".join(errors))
            _noted(WENT_ON_EVENT, testing_stage, state, f"{why}: " + "; ".join(errors))
            return {"builders_sent_back": [*marks, WENT_ON_MARK]}
        for owner, lines in by_owner.items():
            logger.warning("The product does not build; back to %s before %s: %s", owner, testing_stage,
                           "; ".join(lines))
            _noted(SENT_EVENT, owner, state, "; ".join(lines))
        return {"unfinished_orders": {owner: the_note(lines) for owner, lines in by_owner.items()},
                "builders_sent_back": [*marks, f"{SENT_MARK} {sent + 1}"]}
    except Exception:  # noqa: BLE001 - the testing work order starts as before
        logger.warning("Could not build the product before the testing work order", exc_info=True)
        return None


def held_back(state: Any, pending: list[tuple[int, Any]]) -> list[tuple[int, Any]]:
    """The parallel fan-out's `pending` with the testing work orders left out while a builder sent back for the build
    is still building; `pending` as it was otherwise."""
    notes = state.get("unfinished_orders") or {}
    if not any(note and f"--- {HEADING} ---" in note for note in notes.values()):
        return pending
    return [(index, task) for index, task in pending if not is_a_testing_work_order(_stage(task, index))] or pending


def effects_lines(records: list[dict]) -> list[str]:
    """PA.3: builders sent back because the product did not build, and testing work orders started on a failing build."""
    sent = sum(1 for r in records if isinstance(r, dict) and r.get("event") == SENT_EVENT)
    went_on = sum(1 for r in records if isinstance(r, dict) and r.get("event") == WENT_ON_EVENT)
    if not (sent or went_on):
        return ["     -  PA.3 the product builds before the testing work order: not reached"]
    return [f"  {sent:>4}  PA.3 a builder sent back before the testing work order: the product did not build",
            f"  {went_on:>4}  PA.3 a testing work order started on a product that does not build"]


__all__ = ["HEADING", "MOST_SEND_BACKS", "SENT_EVENT", "WENT_ON_EVENT", "before_the_testing_work_order",
           "effects_lines", "held_back", "is_a_testing_work_order", "the_note"]
