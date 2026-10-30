"""A test written to notice a deliberate change is kept only if it does (behind `MUTATION_TEST_RETENTION`).

A mutation finding asks the testing role for a unit test that fails with the change and
passes without it (`mutation_guided`). The harness measured the first half and left the
rest to chance: whatever the fixer wrote stayed in the product. A test that fails on
the unchanged product is a wrong test that ships failing; one that passes both ways
asserts nothing about the change and is noise the next reader has to understand.

With the switch on, after a finding's fix stage the harness keeps what was added only
if it earns its place, at file granularity - a test runner reports files, a fix writes
files, and a model's edit inside a file is not the harness's to take apart:

- a unit test that fails on the product as it is, and did not fail before the fix
  (measured by the fix's own snapshot against the snapshot before it), puts the fix's
  test files back as they were: the finding stays open, its try spent;
- a fix that notices nothing - the harness made the change and every unit test still
  passed - takes with it the test files it created; a file it only edited stays,
  since the earlier tests in it are not this fix's to remove.

Both rules put back test files only, never the product. The harness's note says what
was put back and why, in the ledger and in the next try's earlier attempts.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `MUTATION_TEST_RETENTION` set to on or off overrides this.
ON_BY_DEFAULT = False

_lock = threading.Lock()
#: (run, stage) -> {"base": the commit the fix started from, "failing": unit tests failing then}.
_before: dict[tuple[str, str], dict[str, Any]] = {}


def enabled() -> bool:
    return is_on("MUTATION_TEST_RETENTION", ON_BY_DEFAULT)


def _failing(unit: dict[str, str]) -> set[str]:
    return {name for name, outcome in unit.items() if outcome == "failed"}


def remember(run_id: str | None, stage: str, root: str | Path) -> None:
    """Note the commit the stage starts from and the unit tests that fail there. Never raises."""
    try:
        from app import ci

        snapshot = ci.load(root, "latest")
        entry = {"base": ci.head(root), "failing": _failing(snapshot.unit) if snapshot is not None and snapshot.unit_ran else None}
        with _lock:
            _before[(str(run_id or ""), stage)] = entry
    except Exception:  # noqa: BLE001 - without a note nothing is put back
        logger.debug("Could not note what a mutation finding's fix starts from", exc_info=True)


def _forget(run_id: str | None, stage: str) -> dict[str, Any] | None:
    with _lock:
        return _before.pop((str(run_id or ""), stage), None)


def _put_back(root: str | Path, base: str, paths: list[str], why: str, stage: str) -> list[str]:
    """Put `paths` back as they were at `base` and commit that; the paths put back."""
    from app import ci

    if not paths or not ci.restore_paths(root, base, paths):
        return []
    ci.commit(root, f"Retention, {stage}: {why[:60]}")
    return paths


def _created_by_the_fix(root: str | Path, base: str, relative: str) -> bool:
    from app import ci

    existed = ci._git(root, "cat-file", "-e", f"{base}:{relative}")  # noqa: SLF001 - the workspace's own git
    return existed is not None and existed.returncode != 0


def judged(
    root: str | Path, run_id: str | None, stage: str, settle: Callable[[], bool | None],
) -> tuple[bool | None, str]:
    """`(settled, note)` for a finding's fix: `settle()`'s answer, after the retention rule has put back what it must.

    `settle` is `mutation_guided.settled` for the finding. `note` is "" when nothing was put back or the switch is
    off, else what was and why. A fix whose tests fail on the unchanged product is not settled whatever `settle`
    would say: the change is not measured, the tests are gone.
    """
    if not enabled():
        return settle(), ""
    entry = _forget(run_id, stage)
    if not entry or not entry.get("base"):
        return settle(), ""
    asked: list[bool | None] = []

    def settle_once() -> bool | None:
        if not asked:
            asked.append(settle())
        return asked[0]

    try:
        from app import ci
        from app.analysis.file_kinds import classify_file

        base = entry["base"]
        tests = [path for path in ci.changed_since(root, base) if classify_file(path) == "test"]
        after = ci.load(root, "latest")
        failing_before = entry.get("failing")
        if tests and failing_before is not None and after is not None and after.unit_ran:
            new = sorted(_failing(after.unit) - failing_before)
            if new:
                gone = _put_back(root, base, tests, "its tests fail on the unchanged product", stage)
                if gone:
                    return False, (
                        f"the fix's tests failed on the product as it is ({', '.join(new[:3])}), so its test files "
                        f"were put back: {', '.join(gone[:4])}"
                    )
        answer = settle_once()
        if answer is False:
            created = [path for path in tests if _created_by_the_fix(root, base, path)]
            gone = _put_back(root, base, created, "its tests notice nothing", stage)
            if gone:
                return answer, f"the fix's tests noticed nothing, so the test files it created were put back: {', '.join(gone[:4])}"
        return answer, ""
    except Exception:  # noqa: BLE001 - the finding is settled as it was without the rule
        logger.debug("Could not apply the retention rule", exc_info=True)
        return settle_once(), ""


__all__: list[Any] = ["ON_BY_DEFAULT", "enabled", "judged", "remember"]
