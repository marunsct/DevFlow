"""A defect an earlier fix in its round resolved is closed, not handed to a fixer.

Measured on one run: a test round reported two defects with one cause - the
page read its saved list once and every handler worked on that stale copy. The
first fix made every criterion the second named pass, and CI measured it. The
second was handed to a fixer anyway; told to fix what already worked, it spent
its budget building a later sprint's criteria instead.

Resolved means: every criterion the defect named that was failing when it was
reported passes in a measurement taken since, by one of this round's fixes. A
criterion already passing when the round reported cannot close a defect - it
was never what the defect was about - and a fix CI reverted is never saved, so
what it made pass does not count.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app import ci
from app.acceptance import suite
from app.graph import acceptance_nodes
from app.sprint import Defect, RemediationCycle

SPEC = "acceptance/flow.spec.js"


def _state(root: Path, **extra: Any) -> dict[str, Any]:
    return {"repository": SimpleNamespace(root_path=str(root)), "test_round": 2, **extra}


def _round_found(root: Path, **statuses: str) -> None:
    """The harness's own run of the suite for the round, as it saves it."""
    path = root / suite.RESULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "ran": True,
        "command": "npm run test:acceptance",
        "criteria": {cid: {"id": cid, "status": status} for cid, status in statuses.items()},
    }))


def _measured(root: Path, label: str, **outcomes: str) -> None:
    """CI's latest measurement: one test per criterion, `AC_4="passed"` for AC-4."""
    ci.save(root, ci.Snapshot(
        label=label,
        acceptance={
            f"{SPEC} › [{name.replace('_', '-')}] does what it says": outcome
            for name, outcome in outcomes.items()
        },
        acceptance_ran=True,
    ))


def _defect(description: str = "AC-4 Delete: removes every record", **extra: Any) -> Defect:
    return Defect(
        description=description, severity="blocking", reproduction_steps="r",
        expected_behavior="e", actual_behavior="a", owner="backend", **extra,
    )


def test_a_defect_records_the_criteria_failing_when_it_was_reported(tmp_path) -> None:
    _round_found(tmp_path, **{"AC-3": "passed", "AC-4": "failed", "AC-5": "untested"})

    named = acceptance_nodes.criteria_failing_now(
        _state(tmp_path), "AC-3 and AC-4 break when AC-5 is used"
    )

    assert named == ["AC-4", "AC-5"]


def test_older_defects_have_none_recorded() -> None:
    assert _defect().failing_criteria == []


def test_they_count_as_resolved_once_a_fix_in_the_round_makes_them_pass(tmp_path) -> None:
    _measured(tmp_path, "after defect_fix_2_0", AC_4="passed", AC_5="failed")

    assert acceptance_nodes.passing_since_reported(_state(tmp_path), ["AC-4"]) == ["AC-4"]


def test_a_measurement_before_a_later_fix_is_since_the_report_too(tmp_path) -> None:
    """The next fix measures the tree before it starts; that is still later."""
    _measured(tmp_path, "before defect_fix_2_1", AC_4="passed")

    assert acceptance_nodes.passing_since_reported(_state(tmp_path), ["AC-4"]) == ["AC-4"]


@pytest.mark.parametrize("label", [
    "after the work orders",      # the measurement the round itself reported on
    "after defect_fix_1_0",       # an earlier round's fix
    "accepted",
])
def test_a_measurement_from_before_the_round_s_fixes_proves_nothing(tmp_path, label) -> None:
    _measured(tmp_path, label, AC_4="passed")

    assert acceptance_nodes.passing_since_reported(_state(tmp_path), ["AC-4"]) == []


def test_one_criterion_still_failing_keeps_it_open(tmp_path) -> None:
    _measured(tmp_path, "after defect_fix_2_0", AC_4="passed", AC_6="failed")

    assert acceptance_nodes.passing_since_reported(_state(tmp_path), ["AC-4", "AC-6"]) == []


def test_a_criterion_with_no_test_measured_keeps_it_open(tmp_path) -> None:
    _measured(tmp_path, "after defect_fix_2_0", AC_4="passed")

    assert acceptance_nodes.passing_since_reported(_state(tmp_path), ["AC-9"]) == []


def test_a_defect_naming_no_failing_criterion_is_never_closed_here(tmp_path) -> None:
    _measured(tmp_path, "after defect_fix_2_0", AC_4="passed")

    assert acceptance_nodes.passing_since_reported(_state(tmp_path), []) == []


class TestTheDispatch:
    @staticmethod
    def _cycle(*defects: Defect) -> RemediationCycle:
        return RemediationCycle(sprint_goal="Sprint 2", defects=list(defects))

    def test_it_is_closed_without_a_fixer_and_the_record_says_why(self, tmp_path) -> None:
        from app.graph.workflow import _closed_if_an_earlier_fix_resolved_it

        _round_found(tmp_path, **{"AC-4": "passed"})
        _measured(tmp_path, "after defect_fix_2_0", AC_4="passed")
        cycle = self._cycle(_defect("the first"), _defect(failing_criteria=["AC-4"]))

        update = _closed_if_an_earlier_fix_resolved_it(_state(tmp_path), cycle, 1)

        assert update is not None
        assert update["stage"] == "defect_remediation" and update["defect_cursor"] == 2
        closed = update["remediation"].defects[1]
        assert closed.status == "fixed"
        assert "AC-4" in closed.regression_test and "AC-4" in closed.resolution
        assert closed.verified_by == "npm run test:acceptance"

    def test_a_defect_still_failing_goes_to_a_fixer(self, tmp_path) -> None:
        from app.graph.workflow import _closed_if_an_earlier_fix_resolved_it

        _measured(tmp_path, "after defect_fix_2_0", AC_4="failed")
        cycle = self._cycle(_defect(failing_criteria=["AC-4"]))

        assert _closed_if_an_earlier_fix_resolved_it(_state(tmp_path), cycle, 0) is None

    def test_a_stage_already_under_way_is_left_to_finish(self, tmp_path) -> None:
        from app.graph.workflow import _closed_if_an_earlier_fix_resolved_it

        _measured(tmp_path, "after defect_fix_2_0", AC_4="passed")
        cycle = self._cycle(_defect(failing_criteria=["AC-4"]))
        state = _state(tmp_path, pending_inner_thread_id="inner")

        assert _closed_if_an_earlier_fix_resolved_it(state, cycle, 0) is None
