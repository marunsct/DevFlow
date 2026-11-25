"""A criterion whose every test passed before anything of the product was built is not shown as met (LF.1446).

The lock already says when tests pass on the scaffold ("8 of 21 test(s) pass although nothing of the product is built
yet"), but only in its rationale. Measured on a medium run: from the lock on, every decision read those criteria as
met - the re-plan request listed three of them "currently PASSED", the time budget and the escalation said "still
failing: AC-1, AC-8, AC-13" - while one of them ("service starts with migrations applied") passed with a migration
function that ran no migration, the very fault three fixers were trying to reach. Read without those eight tests, the
sprint's progress over 9 h 53 min was 0 -> 1 of 13.

At the first writing of the suite, before anything is built, the names of the tests that already pass are kept. A
criterion all of whose tests are among them is shown as passing only on tests that passed before anything was built,
not as PASSED, and those tests are left out of the pass counts the foundation rule reads. Never raises.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: The key in the suite's state file.
KEY = "passed_before_anything_was_built"

#: How a criterion that passes only on such tests is shown, in place of PASSED.
SAID = "passes, but only on tests that passed before anything was built"


def record(root: str | Path, result: Any, nothing_built: bool) -> None:
    """Keep the names of the tests that pass while nothing of the product is built. Never raises."""
    if not nothing_built or not getattr(result, "ran", False):
        return
    try:
        from app.acceptance import suite

        tests = getattr(getattr(result, "report", None), "tests", None) or []
        names = sorted({str(test.name) for test in tests if getattr(test, "outcome", "") == "passed"})
        suite._save_state(root, {**suite._state(root), KEY: names})
    except Exception:  # noqa: BLE001 - every passing test counts as before
        logger.debug("Could not keep the tests that pass before anything is built", exc_info=True)


def names(root: str | Path) -> set[str]:
    """The tests that passed before anything was built, as kept at the suite's first writing."""
    try:
        from app.acceptance import suite

        return {str(name) for name in suite._state(root).get(KEY) or []}
    except Exception:  # noqa: BLE001
        return set()


def unproven(root: str | Path, saved: dict[str, Any] | None = None) -> set[str]:
    """The criteria the saved result (the last one when None) shows passing only on tests that passed before anything
    was built."""
    try:
        from app.acceptance import suite

        before = names(root)
        if not before:
            return set()
        saved = suite.last_result(root) if saved is None else saved
        entries = {**(saved.get("criteria") or {}), **(saved.get("change_requests") or {})}
        found = set()
        for cid, entry in entries.items():
            tests = [test for test in (entry or {}).get("tests") or [] if isinstance(test, dict)]
            if tests and all(str(test.get("name")) in before for test in tests):
                found.add(str(cid))
        return found
    except Exception:  # noqa: BLE001
        return set()


def shown(status: Any, cid: str, unproven_ids: set[str]) -> str:
    """How a criterion's status is shown: PASSED becomes `SAID` for one in `unproven_ids`."""
    word = str(status or "")
    if word.lower() == "passed" and cid in unproven_ids:
        return SAID
    return word.upper()


__all__ = ["KEY", "SAID", "names", "record", "shown", "unproven"]
