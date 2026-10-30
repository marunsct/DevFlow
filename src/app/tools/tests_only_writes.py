"""While the acceptance suite is green, the first fix of a failing unit test writes test files only (behind `TESTS_ONLY_WRITES`).

Measured on two runs: fixes for "the unit tests fail" rewrote the product's files
as well as the unit tests, broke the locked acceptance suite or other unit tests,
and were reverted whole; four wrong unit tests then shipped failing beside a green
suite. The acceptance suite is the definition of done and it already passed, so the
first thing a failing unit test is owed is a look at the test.

With the switch on, a fix stage that (1) is for a defect about the project's own
failing unit tests, (2) starts while the locked suite's last run passed in full, and
(3) is the defect's first attempt, is refused any write to application code: the
file tools answer as they do to a test round. A second attempt - after the first left
the defect open or was reverted - writes whatever it needs, so a product that is
really wrong is still fixed. The harness records which mode each attempt ran in.

The mode is registered by `app.graph.defect_fix_modes` when the stage begins and read
here by the file tools, keyed by the run and the stage, as the checks after a write are.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from app.switches import is_on

#: `TESTS_ONLY_WRITES` set to on or off overrides this.
ON_BY_DEFAULT = False
_lock = threading.Lock()
_holding: set[tuple[str, str]] = set()


def enabled() -> bool:
    return is_on("TESTS_ONLY_WRITES", ON_BY_DEFAULT)


def hold(run_id: str | None, stage: str) -> None:
    """From now on a write in `stage` of `run_id` is refused unless it is to a test, a configuration or a document."""
    with _lock:
        _holding.add((str(run_id or ""), stage))


def release(run_id: str | None, stage: str) -> None:
    with _lock:
        _holding.discard((str(run_id or ""), stage))


def holds(run_id: str | None, stage: str) -> bool:
    with _lock:
        return (str(run_id or ""), stage) in _holding


def may_write(run_id: str | None, stage: str, root: str | Path, path: str) -> bool:
    """Whether `path` (relative to `root`, or absolute) is writable in `stage` of `run_id` under the mode."""
    if not holds(run_id, stage):
        return True
    return _is_not_application(root, path)


def _is_not_application(root: str | Path, path: str) -> bool:
    """Whether a file is a test, test configuration, a document, a package manifest or a throwaway."""
    from app.analysis.file_kinds import classify_file, is_scratch
    from app.tools.repository import PACKAGE_MANIFESTS

    shown = str(path or "").replace("\\", "/")
    try:
        shown = Path(shown).resolve().relative_to(Path(root).resolve()).as_posix() if Path(shown).is_absolute() else shown
    except (OSError, ValueError):
        pass
    return (Path(shown).name in PACKAGE_MANIFESTS or classify_file(shown) != "application" or is_scratch(shown))


def refusal(root: Path, target: Path) -> str | None:
    """The refusal for the running fix stage writing application code in tests-only mode, or None."""
    if not _holding:
        return None
    try:
        from app.observability.transcript import _run_id_from_config, _stage_from_config

        stage = str(_stage_from_config("") or "")
        run_id = _run_id_from_config()
        if not holds(run_id, stage):
            return None
        shown = target.relative_to(root).as_posix()
    except Exception:  # noqa: BLE001 - a guard that cannot decide lets the call through
        return None
    if _is_not_application(root, shown):
        return None
    return (
        f"'{shown}' is product code, and this first attempt at the failing unit tests writes tests only: the locked "
        "acceptance suite already passes, so the product is what it is meant to be and the unit test is the first "
        "thing to put right. Correct the test, its fixtures or its setup. If the test is right and the product is "
        "wrong, say exactly which file and what change in `blockers` and finish: the next attempt may change the "
        "product. Nothing was written."
    )


def briefing(run_id: str | None, stage: str) -> str:
    """The section of the fixer's request that says what this attempt may write; "" when the stage is not held."""
    if not holds(run_id, stage):
        return ""
    return (
        "\n--- What this attempt may write ---\n"
        "The locked acceptance suite passes, and what fails is the project's own unit tests. This first attempt "
        "writes test files only (tests, fixtures, test setup); a write to application code is refused. Find out "
        "whether the test asserts the wrong thing, builds the wrong state or calls the product the wrong way, and "
        "correct it. If the test is right and the product is wrong, name the file and the change in `blockers` and "
        "finish; the next attempt may change the product.\n"
    )


def explain_mode(held: bool, *, unit_failure_beside_a_green_suite: bool) -> str:
    """The ledger's words for the mode an attempt ran in; "" when the switch had no say."""
    if held:
        return "tests only: the locked acceptance suite is green and this is the first attempt at a failing unit test"
    if unit_failure_beside_a_green_suite:
        return "product code allowed: an earlier attempt at this failing unit test did not close it"
    return ""


__all__: list[Any] = [
    "ON_BY_DEFAULT", "briefing", "enabled", "explain_mode", "hold", "holds", "may_write", "refusal", "release",
]
