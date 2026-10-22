"""A defect a round raises again refreshes the open one; a second fixer is not queued for it.

Measured on one run: "The unit tests fail." was raised by round 0 and again by
round 1 with a longer output; both stayed open, and round 2 sent two fix stages
of forty calls each, one after the other, at the one failure.
"""
from __future__ import annotations

import inspect

from app.graph import workflow
from app.sprint import Defect, RemediationCycle


def _defect(description, *, source="test round", found_in_round=0, status="open"):
    return Defect(description=description, severity="major", reproduction_steps="run the unit tests",
                  expected_behavior="they pass", actual_behavior=f"output of round {found_in_round}",
                  owner="testing", source=source, found_in_round=found_in_round, status=status)


def _cycle(*defects):
    return RemediationCycle(sprint_goal="Sprint 1", defects=list(defects))


def test_the_same_check_s_defect_refreshes_the_open_one():
    open_one = _defect("The unit tests fail. The runner's output ends: no such table: users (round 0)")
    again = _defect("The unit tests fail. The runner's output ends: no such table: users (round 1, longer)",
                    found_in_round=1)
    other = _defect("[AC-8] Users can sign in - the acceptance suite says this does not work yet.",
                    source="acceptance suite", found_in_round=1)

    cycle, repeated = workflow._refreshed_by_the_round(_cycle(open_one), [again, other], 1)

    assert repeated == [again]
    (refreshed,) = cycle.defects
    assert refreshed.description.endswith("(round 1, longer)") and refreshed.found_in_round == 1
    assert refreshed.actual_behavior == "output of round 1"


def test_a_closed_defect_or_another_check_s_is_raised_as_new():
    fixed = _defect("The unit tests fail. The runner's output ends: x", status="fixed")
    again = _defect("The unit tests fail. The runner's output ends: y", found_in_round=1)
    review = _defect("The unit tests fail. The runner's output ends: y", source="code review", found_in_round=1)

    cycle, repeated = workflow._refreshed_by_the_round(_cycle(fixed), [again, review], 1)

    assert repeated == [] and cycle.defects == [fixed]


def test_the_round_still_counts_what_it_raised_again():
    """Merged, the round must still read as failing and still charge the budget,
    or a failure that persists would never exhaust it."""
    source = inspect.getsource(workflow)

    assert "passed=not measured" in source
    assert "charge_the_budget=_a_round_that_found_a_product_defect(measured)" in source
