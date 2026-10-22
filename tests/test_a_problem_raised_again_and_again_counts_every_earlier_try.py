"""A problem's failed tries and spent calls count every earlier generation, and a fix left open is a try.

Measured in a scripted run: three same-wording defects, the first two fixed with
20 calls each, counted 20 and one try; a defect left open twice after measured
failures counted no try at all, so the candidates, the judgement model and the
last attempt's note never fired.
"""
from __future__ import annotations

import os
from unittest import mock

from app.graph import defect_budget
from app.sprint import Defect, RemediationCycle, failed_fix_tries, recurrence_chain


def _defect(status, calls=0, outcome="fixed"):
    return Defect(description="The items route answers 500 on create", severity="major", reproduction_steps="r",
                  expected_behavior="e", actual_behavior="a", owner="backend", status=status,
                  attempts=[{"stage": "defect_fix_1_0", "outcome": outcome, "calls": calls}] if calls else [])


def test_every_generation_of_a_recurring_problem_is_counted():
    cycle = RemediationCycle(sprint_goal="g", defects=[_defect("fixed", 20), _defect("fixed", 20), _defect("open")])
    assert len(recurrence_chain(cycle.defects[2], cycle.defects[:2])) == 2
    assert failed_fix_tries(cycle, 2) == 2
    with mock.patch.dict(os.environ, {"DEFECT_CALL_CAP": "on"}):
        assert defect_budget.spent(cycle, 2) == 40


def test_a_fix_measured_and_left_open_is_a_failed_try():
    left_open = _defect("open", 10, "left open: its tests still fail")
    left_open = left_open.model_copy(update={"attempts": [*left_open.attempts, {"stage": "defect_fix_2_0", "outcome": "left open"}]})
    assert failed_fix_tries(RemediationCycle(sprint_goal="g", defects=[left_open]), 0) == 2
