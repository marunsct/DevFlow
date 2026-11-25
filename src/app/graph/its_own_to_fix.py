"""After a stage answers, it is asked to fix only the errors in files it may write (PA.8).

Measured on a small run: a testing stage changed the package manifest and answered; the check after the answer ran
the compiler, which reported an error in the product's entry file, and the stage was told "fix these errors now".
That file is a builder's: every write to it was refused (12 refusals, 5 after its first answer) and the stage answered
4 times in one visit. The same question the file tools answer for a write - whose file it is - now splits what the
check found:

- an error in a file the stage may write is put to it once, as before;
- an error in a file it may not write is added to its answer's `blockers` by the harness, and the stage ends with its
  answer. A testing work order's is also recorded as its blocker for the builder that owns the file
  (`app.tools.testing_blockers`), which sends it there before the tests run.

Nothing here names a language, a framework or a kind of product.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

#: How a diagnostic line names its file: "- In `path` line 12: ...".
_THE_FILE = re.compile(r"^\s*-\s*In\s+`([^`]+)`(?:\s+line\s+(\S+?):)?\s*(.*)$", re.S)

#: The ledger event (`loop.sh effects`).
KEPT_EVENT = "post-answer error in another's file kept as a blocker"

#: The testing work order's stage names.
_TESTING_WORK_ORDER = "specialist_testing_"


def _the_file(line: str) -> str:
    match = _THE_FILE.match(str(line or ""))
    return match.group(1).strip() if match else ""


def split(root: str, stage: str, run_id: str | None, diagnostics: list[str]) -> tuple[list[str], list[str]]:
    """(the lines in files `stage` may write, the lines in files it may not); a line naming no file is its own."""
    from app.tools.repository import why_the_stage_may_not_write

    own: list[str] = []
    others: list[str] = []
    for line in diagnostics:
        path = _the_file(line)
        if path and why_the_stage_may_not_write(root, stage, path, run_id):
            others.append(line)
        else:
            own.append(line)
    return own, others


def _by_file(lines: list[str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for line in lines:
        match = _THE_FILE.match(str(line or ""))
        if not match:
            continue
        where = f"line {match.group(2)}: " if match.group(2) else ""
        found.setdefault(match.group(1).strip(), []).append(f"{where}{' '.join(match.group(3).split())}")
    return found


def blocker_lines(root: str, stage: str, lines: list[str]) -> list[str]:
    """The blockers for errors in files `stage` may not write, one a file; a testing work order's recorded for the
    builder that owns the file. Never raises."""
    blockers: list[str] = []
    for path, said in _by_file(lines).items():
        errors = "; ".join(said)
        try:
            if stage.startswith(_TESTING_WORK_ORDER):
                from app.tools import testing_blockers

                needed = testing_blockers.cut_short(f"what the checks after its answer found there fixed: {errors}")
                testing_blockers.record(root, stage, path, needed)
                blockers.append(testing_blockers.as_blocker(path, needed))
            else:
                blockers.append(f"`{path}` is not this stage's to change, and the checks after its answer found "
                                f"there: {errors}")
            from app.observability import defect_ledger

            defect_ledger.note(KEPT_EVENT, stage, detail=f"`{path}`: {errors}"[:300])
        except Exception:  # noqa: BLE001 - the answer stands without it
            logger.debug("Could not keep an error in %s as %s's blocker", path, stage, exc_info=True)
    return blockers


def with_blockers(answer: Any, blockers: list[str]) -> Any:
    """`answer` with `blockers` added to its own; as it was when it has no `blockers` or nothing is new."""
    if not blockers or answer is None or not hasattr(answer, "model_copy"):
        return answer
    if "blockers" not in (getattr(type(answer), "model_fields", None) or {}):
        return answer
    have = list(getattr(answer, "blockers", None) or [])
    added = [line for line in blockers if line not in have]
    if not added:
        return answer
    try:
        return answer.model_copy(update={"blockers": [*have, *added]})
    except Exception:  # noqa: BLE001 - its own answer stands
        return answer


def effects_lines(records: list[dict]) -> list[str]:
    """PA.8: errors the checks after an answer found in a file the stage may not write, kept as its blockers."""
    kept = sum(1 for r in records if isinstance(r, dict) and r.get("event") == KEPT_EVENT)
    if not kept:
        return ["     -  PA.8 an error in a file the stage may not write kept as its blocker: not reached"]
    return [f"  {kept:>4}  PA.8 an error in a file the stage may not write kept as its blocker, not put to it"]


__all__ = ["KEPT_EVENT", "blocker_lines", "effects_lines", "split", "with_blockers"]
