"""A regression defect whose test passes again is closed, not handed to fixer after fixer.

Measured on one run. A sprint's restyle undid an earlier contrast fix; the
regression check, the test round, code review and the page check each raised
it, and the first fixer restored it. The regression defect - "Regression:
`unit: ... contrast >= 4.5:1` passed before this batch of work orders and fails
now" - names one test and no criterion, so the checks that close a defect once a
measurement shows it resolved never reached it. It went to two fixers in turn;
each changed nothing and answered "None. All sprint-2 tests pass." and "None -
the reported defect does not reproduce", which read as blockers. It stayed open,
and the sprint's attempt was spent on it.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app import ci
from app.agents.specialists import SpecialistOutput
from app.sprint import Defect, RemediationCycle

TEST = "test › [WCAG AA] #empty-state foreground/background contrast ≥ 4.5:1"
REGRESSION = f"Regression: `unit: {TEST}` passed before this batch of work orders and fails now."


def _state(root: Path, **extra: Any) -> dict[str, Any]:
    return {"repository": SimpleNamespace(root_path=str(root)), "test_round": 1, **extra}


def _measured(root: Path, label: str, outcome: str, ran: bool = True) -> None:
    ci.save(root, ci.Snapshot(label=label, unit={TEST: outcome}, unit_ran=ran))


def _defect(description: str = REGRESSION) -> Defect:
    return Defect(
        description=description, severity="major", reproduction_steps="r",
        expected_behavior="e", actual_behavior="a", owner="ui_ux",
    )


def _cycle(*defects: Defect) -> RemediationCycle:
    return RemediationCycle(sprint_goal="Sprint 3", defects=list(defects))


class TestWhenItPassesAgain:
    def test_it_is_named(self, tmp_path):
        from app.graph.workflow import _a_regressed_test_passing_since

        _measured(tmp_path, "after defect_fix_1_0", "passed")

        assert _a_regressed_test_passing_since(_state(tmp_path), _defect()) == f"unit: {TEST}"

    @pytest.mark.parametrize("label", ["after the work orders", "after defect_fix_0_3", "accepted"])
    def test_a_measurement_from_before_the_round_s_fixes_proves_nothing(self, tmp_path, label):
        from app.graph.workflow import _a_regressed_test_passing_since

        _measured(tmp_path, label, "passed")

        assert _a_regressed_test_passing_since(_state(tmp_path), _defect()) == ""

    def test_still_failing_is_not_passing(self, tmp_path):
        from app.graph.workflow import _a_regressed_test_passing_since

        _measured(tmp_path, "after defect_fix_1_0", "failed")

        assert _a_regressed_test_passing_since(_state(tmp_path), _defect()) == ""

    def test_a_suite_that_did_not_run_proves_nothing(self, tmp_path):
        from app.graph.workflow import _a_regressed_test_passing_since

        _measured(tmp_path, "after defect_fix_1_0", "passed", ran=False)

        assert _a_regressed_test_passing_since(_state(tmp_path), _defect()) == ""

    def test_a_defect_that_is_no_regression_is_never_read_as_one(self, tmp_path):
        from app.graph.workflow import _a_regressed_test_passing_since

        _measured(tmp_path, "after defect_fix_1_0", "passed")

        assert _a_regressed_test_passing_since(_state(tmp_path), _defect("The contrast is too low")) == ""


class TestItIsClosed:
    def test_before_a_fixer_is_sent(self, tmp_path):
        from app.graph.workflow import _closed_if_an_earlier_fix_resolved_it

        _measured(tmp_path, "after defect_fix_1_0", "passed")

        update = _closed_if_an_earlier_fix_resolved_it(_state(tmp_path), _cycle(_defect("x"), _defect()), 1)

        assert update is not None
        assert update["defect_cursor"] == 2
        closed = update["remediation"].defects[1]
        assert closed.status == "fixed"
        assert TEST in closed.regression_test
        assert "passes again" in closed.resolution

    def test_still_failing_goes_to_a_fixer(self, tmp_path):
        from app.graph.workflow import _closed_if_an_earlier_fix_resolved_it

        _measured(tmp_path, "after defect_fix_1_0", "failed")

        assert _closed_if_an_earlier_fix_resolved_it(_state(tmp_path), _cycle(_defect()), 0) is None

    def test_by_the_next_round(self, tmp_path):
        from app.graph.workflow import _closed_by_this_round_s_measurement

        _measured(tmp_path, "after defect_fix_1_2", "passed")

        closed = _closed_by_this_round_s_measurement(_state(tmp_path), _cycle(_defect()), 1)

        assert closed.defects[0].status == "fixed"

    def test_not_by_the_next_round_while_it_fails(self, tmp_path):
        from app.graph.workflow import _closed_by_this_round_s_measurement

        _measured(tmp_path, "after defect_fix_1_2", "failed")

        assert _closed_by_this_round_s_measurement(_state(tmp_path), _cycle(_defect()), 1).defects[0].status == "open"


@pytest.mark.parametrize("answer", [
    "None. All sprint-2 tests pass. The AC-16 failure is expected and scoped to a later sprint.",
    "None — the reported defect does not reproduce on the current codebase. All unit tests pass.",
    "None - nothing stands in the way",
    "N/A: the fix was already in place",
])
def test_the_fixers_answers_are_no_blockers(answer: str) -> None:
    assert SpecialistOutput(decisions=["changed nothing"], blockers=[answer]).blockers == []
