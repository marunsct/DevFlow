"""A batch after which the product does not start has one defect, not one per lost test.

Measured live: a re-planned batch left the product unable to start for the
acceptance suite. The test round raised that once, and the regression check
also raised each acceptance test that had passed before as "gone now - no test
of that name ran ... removed or renamed". Those went first in the queue, ahead
of the start failure, and a fixer was sent to find a renamed test in a locked
suite while the cause waited at the end.
"""

from __future__ import annotations

from types import SimpleNamespace

from app import ci
from app.graph.engineering import regression_defects

DID_NOT_START = (
    "The product did not start for the acceptance suite: no test could reach it. Its output:\n"
    "Error: Process from config.webServer was not able to start. Exit code: 1"
)


def _state() -> dict:
    task = SimpleNamespace(specialist_role="ui_ux", title="Wire the page", task_description="")
    return {"milestone_plan": SimpleNamespace(delegated_tasks=[task])}


def _after(problem: str = DID_NOT_START) -> ci.Snapshot:
    return ci.Snapshot(label="after the work orders", unit={"logic.test.js › adds": "passed"}, unit_ran=True,
                       acceptance={}, acceptance_ran=True, problem=problem)


LOST = [
    "acceptance: auth.spec.js › [AC-1] register returns 201",
    "acceptance: tasks.spec.js › [AC-2] creates a note",
]


def test_acceptance_tests_lost_to_a_product_that_did_not_start_are_not_regressions() -> None:
    assert regression_defects(_state(), LOST, _after()) == []


def test_a_unit_test_lost_with_it_is_still_raised() -> None:
    [defect] = regression_defects(_state(), [*LOST, "unit: logic.test.js › removes"], _after())
    assert "logic.test.js › removes" in defect.description


def test_lost_acceptance_tests_of_a_product_that_started_are_still_raised() -> None:
    after = ci.Snapshot(label="after the work orders", acceptance={"auth.spec.js › [AC-3] other": "passed"},
                        acceptance_ran=True)
    assert len(regression_defects(_state(), LOST, after)) == 2
