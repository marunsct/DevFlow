"""A defect whose own tests pass when it comes up for dispatch is closed there.

The queue a test round writes is stale by dispatch time: later fixes in the
round may have made a defect pass, and the harness only re-ran a defect's
tests *after* its fixer ran. Measured on one day of runs: sixteen defects
were closed "already fixed" from stored measurements at dispatch, and nine
fixer stages were named and stood down. Dispatch now re-measures the
defect's own tests - seconds of probe against a fixer stage of minutes - and
a green probe closes it with no model call at all (Initiative L.3).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app import ci
from app.acceptance import suite
from app.sprint import Defect, RemediationCycle

SPEC = "acceptance/flow.spec.js"


def _state(root: Path, **extra: Any) -> dict[str, Any]:
    return {"repository": SimpleNamespace(root_path=str(root)), "test_round": 2, **extra}


def _defect(description: str = "AC-4 Delete: removes every record", **extra: Any) -> Defect:
    return Defect(
        description=description, severity="blocking", reproduction_steps="r",
        expected_behavior="e", actual_behavior="a", owner="backend", **extra,
    )


def _cycle(*defects: Defect) -> RemediationCycle:
    return RemediationCycle(sprint_goal="Sprint 2", defects=list(defects))


def _round_found(root: Path, **statuses: str) -> None:
    path = root / suite.RESULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "ran": True,
        "command": "npm run test:acceptance",
        "criteria": {cid: {"id": cid, "status": status} for cid, status in statuses.items()},
    }))


def _measured(root: Path, label: str, **outcomes: str) -> None:
    ci.save(root, ci.Snapshot(
        label=label,
        acceptance={
            f"{SPEC} › [{name.replace('_', '-')}] does what it says": outcome
            for name, outcome in outcomes.items()
        },
        acceptance_ran=True,
    ))


def test_a_defect_whose_own_tests_pass_in_a_dispatch_re_measure_is_closed(tmp_path, monkeypatch) -> None:
    from app.graph import workflow

    monkeypatch.setattr(workflow, "_the_defect_s_tests_pass", lambda root, defect: True)
    cycle = _cycle(_defect(failing_criteria=["AC-4"]))

    update = workflow._closed_if_an_earlier_fix_resolved_it(_state(tmp_path), cycle, 0)

    assert update is not None
    assert update["stage"] == "defect_remediation" and update["defect_cursor"] == 1
    closed = update["remediation"].defects[0]
    assert closed.status == "fixed"
    assert "re-measure" in closed.resolution and "re-measure" in closed.regression_test


def test_a_defect_still_failing_at_dispatch_goes_to_a_fixer(tmp_path, monkeypatch) -> None:
    from app.graph import workflow

    monkeypatch.setattr(workflow, "_the_defect_s_tests_pass", lambda root, defect: False)

    assert workflow._closed_if_an_earlier_fix_resolved_it(
        _state(tmp_path), _cycle(_defect(failing_criteria=["AC-4"])), 0
    ) is None


def test_a_re_measure_that_cannot_answer_changes_nothing(tmp_path, monkeypatch) -> None:
    from app.graph import workflow

    monkeypatch.setattr(workflow, "_the_defect_s_tests_pass", lambda root, defect: None)

    assert workflow._closed_if_an_earlier_fix_resolved_it(
        _state(tmp_path), _cycle(_defect(failing_criteria=["AC-4"])), 0
    ) is None


def test_a_defect_a_stored_measurement_resolves_is_not_re_measured(tmp_path, monkeypatch) -> None:
    """The cheap stored answer comes first; the probe is for what no
    measurement can settle."""
    from app.graph import workflow

    calls: list[str] = []

    def probe(root, defect):
        calls.append(defect.description)
        return True

    monkeypatch.setattr(workflow, "_the_defect_s_tests_pass", probe)
    _round_found(tmp_path, **{"AC-4": "passed"})
    _measured(tmp_path, "after defect_fix_2_0", AC_4="passed")

    update = workflow._closed_if_an_earlier_fix_resolved_it(
        _state(tmp_path), _cycle(_defect(failing_criteria=["AC-4"])), 0
    )

    assert update is not None and calls == []
    assert "earlier fix" in update["remediation"].defects[0].resolution
