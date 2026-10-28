"""A sprint whose acceptance suite is fully green is not planned again for the unit tests alone (behind `SETTLE_WHEN_ACCEPTANCE_IS_GREEN`).

Measured on a small-model run: all 18 acceptance criteria passed from the eighteenth minute, the one open defect was
a unit test the model had written (tests sharing a temporary folder), and the sprint was planned again, drafted again
and measured again, each pass ending the same way. The acceptance suite is the run's definition of done; a unit
test that fails beside a fully green suite is a known issue the release records (`release_with_failing_unit_tests`),
not a reason to redraft a product that works.

The rule applies from the first exhaustion on (owner 2026-10-27: the one re-plan it used to wait for redrafted a
product whose 12 acceptance tests all passed, and the escalation then accepted it as it was), only when the suite ran,
every acceptance test passed and every defect still open is a failing unit test. It sends the sprint where the re-plan
limit does: to the escalation, which decides to accept it with the open problems recorded.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file turns it on.
ON_BY_DEFAULT = False

#: A re-plan has already been tried this many times.
AFTER_REPLANS = 0

#: How a defect from a failing unit-test run begins (`workflow.UNIT_TESTS_FAIL`).
UNIT_TESTS_FAIL = "The unit tests fail."

#: Defects a check read from the files rather than from a test that failed. Measured on one run: every acceptance test
#: and every unit test passed, and the sprint was planned again for a cross-file finding about scratch files a dead
#: attempt left in the unit-test folder. Beside a green suite it is a known issue the release records.
READ_FROM_THE_FILES = ("cross-file check",)


def enabled() -> bool:
    return is_on("SETTLE_WHEN_ACCEPTANCE_IS_GREEN", ON_BY_DEFAULT)


def _a_unit_test_failure(defect: Any, acceptance_command: str) -> bool:
    """Whether an open defect is a failing unit test: the harness's own wording, or a test round's defect in its words.

    A test round's model words the defect itself ("the error handler answers with a body where the test expects
    none"), so the opening words alone missed it: measured on a small-model run, 18 of 18 criteria passed for three
    rounds and the sprint was planned again twice for two such defects. Such a defect carries the test command the
    round left failing (`caught_by`); beside a green suite that is not the suite, and it names no criterion.
    """
    if str(getattr(defect, "description", "") or "").startswith(UNIT_TESTS_FAIL):
        return True
    caught_by = str(getattr(defect, "caught_by", "") or "").strip()
    return bool(caught_by) and caught_by != acceptance_command and not list(getattr(defect, "failing_criteria", None) or [])


def applies(root: str | Path, defects: Any, replans: int) -> bool:
    """Whether the sprint should go to the escalation now: the acceptance suite is green and only unit tests, or findings read from the files, are open."""
    if not enabled() or replans < AFTER_REPLANS:
        return False
    try:
        from app.acceptance import suite

        result = suite.last_result(root) or {}
        if not result.get("ran") or int(result.get("passed") or 0) <= 0 or int(result.get("failed") or 0) > 0:
            return False
        if str(result.get("problem") or ""):
            return False
        still_open = [d for d in defects or () if getattr(d, "status", "") == "open"]
        command = suite._command(root)
        acceptance = " ".join(command[0]) if command else ""
        return bool(still_open) and all(
            _a_unit_test_failure(d, acceptance) or str(getattr(d, "source", "") or "") in READ_FROM_THE_FILES
            for d in still_open
        )
    except Exception:  # noqa: BLE001 - a rule that cannot tell leaves the sprint as it was
        logger.debug("Could not tell whether the acceptance suite is green", exc_info=True)
        return False


__all__ = ["AFTER_REPLANS", "ON_BY_DEFAULT", "READ_FROM_THE_FILES", "applies", "enabled"]
