"""A fix that makes a locked test pass and breaks only unit tests is kept, and each is raised (behind `UNIT_TESTS_YIELD_TO_THE_LOCKED_SUITE`).

Measured on one run: a locked test asked for a JSON content type on a route, and a unit test written earlier asserted
that route's body was empty. Three fixes in a row made the locked test pass, broke the unit test and were reverted, so
the criterion could never be reached. The locked suite is the definition of done; the unit tests are the build's own.
`net_gain` weighs how many tests a fix gained, and left this one-for-one case to the revert.

The fix stays when every test it broke is a unit test, the unit runner still ran, the product builds and starts, and
at least one locked test went from failing to passing. A fix that broke a locked test, or made none pass, is judged as
before. What it broke is not hidden: each unit test becomes a defect naming the locked test it disagrees with, in the
next round's `review_defects`. Its description names only the unit test: a criterion's id there would have the
defect judged by that criterion's tests, which pass. A broken unit test can also be a real fault the locked suite does
not cover, so the defect says that too, and a fix that fails the locked test to suit the unit test is reverted.

Off until measured: a one-for-one keep reverses a measured threshold, on one run's evidence, and a locked test that
passes is no longer failing, so a wrong one is not brought to a dispute by this path.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `UNIT_TESTS_YIELD_TO_THE_LOCKED_SUITE` set to on or off overrides this.
ON_BY_DEFAULT = False

STORE = ".harness/unit_tests_that_disagree.json"
#: Defects raised from one kept fix, as for any regression, and locked tests each one names.
MOST_DEFECTS = 6
MOST_LOCKED_NAMED = 3

_UNIT = "unit: "
_LOCKED = "acceptance: "


def enabled() -> bool:
    return is_on("UNIT_TESTS_YIELD_TO_THE_LOCKED_SUITE", ON_BY_DEFAULT)


def locked_tests_gained(broken: list[str], before: Any, after: Any, *, product_runs: bool) -> list[str]:
    """The locked tests that went from failing to passing, when a fix that broke `broken` stays for them; else []."""
    if not enabled() or not broken or not product_runs or before is None:
        return []
    if not all(str(item).startswith(_UNIT) for item in broken):
        return []  # a locked test, the build or the install: judged as before
    if not after.unit_ran or not after.acceptance_ran or not before.acceptance_ran:
        return []  # a unit runner that stopped is not a disagreement
    return sorted(
        f"{_LOCKED}{name}" for name, outcome in after.acceptance.items()
        if outcome == "passed" and name in before.acceptance and before.acceptance[name] != "passed"
    )


def note(root: str | Path, broken: list[str], locked: list[str], gone: list[str]) -> None:
    """Keep what a kept fix broke for `raised`, which the node holding the state calls. Never raises."""
    path = Path(root) / STORE
    try:
        found = _read(path)
        for name in broken:
            found[name] = {"locked": locked[:MOST_LOCKED_NAMED], "gone": name in gone}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(found, indent=1) + "\n", encoding="utf-8")
    except OSError:
        logger.warning("Could not note the unit tests a kept fix broke; the next round finds them failing", exc_info=True)


def _read(path: Path) -> dict[str, Any]:
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError):
        return {}


def what_it_says(locked: list[str], gone: bool) -> str:
    """The defect's actual behaviour: which locked test it disagrees with, and what to do about it."""
    named = ", ".join(f"`{name}`" for name in locked)
    return (
        ("No test of that name ran" if gone else "It fails")
        + f" since a fix that made the locked acceptance test(s) {named} pass. The unit test disagrees with the locked "
        "test. The fix was kept: the locked suite is the definition of done and no fix may change it. Where the two ask "
        "for opposite things, change what the unit test asserts to what the product now does, keep the test's name, and "
        "say in your answer that it was out of date. If it asserts something the locked test does not ask for, the fix "
        "damaged the product: repair the product so both pass. A change that fails the locked test is reverted."
    )


def raised(state: Any) -> list[Any]:
    """The defects for what kept fixes broke since the last call, for the next round; each is raised once."""
    from app.agents.specialists import ReportedDefect
    from app.graph.engineering import _owner_of, raised_by

    path = Path(state["repository"].root_path) / STORE
    found = _read(path)
    if not found:
        return []
    path.unlink(missing_ok=True)
    return raised_by("regression", [
        ReportedDefect(
            description=f"Regression: `{name}` passed before a fix was kept, and fails now.",
            severity="major",
            reproduction_steps="Run the unit tests in the project directory.",
            expected_behavior="It passes, and so does the locked acceptance test it disagrees with.",
            actual_behavior=what_it_says(list(item.get("locked") or []), bool(item.get("gone"))),
            affected_files=[],
            owner=_owner_of(state, ""),
        )
        for name, item in list(found.items())[:MOST_DEFECTS]
    ])
