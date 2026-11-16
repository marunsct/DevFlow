"""The one defect for one wrong answer behind many tests closes the per-criterion defects it explains (LR.53).

Measured on one run: the round raised the one defect, but the eleven per-criterion defects of the round before stayed
open beside it, so the fixers still worked through twelve and the grouping saved nothing.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph import workflow
from app.sprint import Defect, RemediationCycle


def _defect(description, status="open"):
    return Defect(description=description, severity="major", reproduction_steps="r", expected_behavior="e",
                  actual_behavior="a", owner="backend", status=status)


def test_the_per_criterion_defects_are_superseded_and_others_stay():
    cycle = RemediationCycle(sprint_goal="g", defects=[
        _defect("[AC-3] Create an item - the acceptance suite says this does not work yet."),
        _defect("Regression: `unit: test_a` passed before"),
        _defect("[AC-4] List - the suite says", status="fixed"),
    ])
    one = SimpleNamespace(description="16 acceptance tests across 14 criteria are all answered 422 where they expect another answer")
    after = workflow.superseded_by_one_cause(cycle, [one])
    assert [d.status for d in after.defects] == ["superseded", "open", "fixed"]


def test_without_the_one_defect_nothing_changes():
    cycle = RemediationCycle(sprint_goal="g", defects=[_defect("[AC-3] Create - fails")])
    assert workflow.superseded_by_one_cause(cycle, [SimpleNamespace(description="[AC-5] other")]) is cycle
