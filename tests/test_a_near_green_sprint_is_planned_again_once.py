"""A near-green sprint is planned again once, not twice (LR.53, `NEAR_GREEN_REPLANNED_ONCE`, Efficiency group).

Measured over 175 re-plans in 109 runs: after a near-green locked suite the first re-plan beat the best attempt in 41
of 57 cases, the second and third in 4 of 27, at about 34 active minutes each, and 21 of the 22 runs that had them
scored every hidden test.
"""
from __future__ import annotations

import json

import pytest

from app import switches
from app.acceptance import suite
from app.graph import end_of_attempt, near_green_once
from app.observability import provenance, switch_firing


def _measured(root, passed, failed):
    path = root / suite.RESULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"passed": passed, "failed": failed}))


@pytest.mark.parametrize("passed,failed,near", [(17, 1, True), (8, 2, True), (27, 3, True), (6, 3, False),
                                                 (10, 0, False), (0, 0, False)])
def test_what_near_green_is(passed, failed, near):
    assert near_green_once.near_green(passed, failed) is near


def test_on_a_second_end_of_a_near_green_sprint_it_stops_instead_of_planning_again(tmp_path, monkeypatch):
    monkeypatch.setenv("NEAR_GREEN_REPLANNED_ONCE", "on")
    _measured(tmp_path, 17, 1)
    first = end_of_attempt.decide(str(tmp_path), [], replans=0, best_history=[])
    second = end_of_attempt.decide(str(tmp_path), [], replans=1, best_history=[])
    assert first.outcome == end_of_attempt.REPLAN
    assert second.outcome == end_of_attempt.STOP and near_green_once.SAID in second.why


def test_far_from_green_or_off_it_plans_again_as_before(tmp_path, monkeypatch):
    monkeypatch.setenv("NEAR_GREEN_REPLANNED_ONCE", "on")
    _measured(tmp_path, 5, 5)
    assert end_of_attempt.decide(str(tmp_path), [], replans=1, best_history=[]).outcome == end_of_attempt.REPLAN
    monkeypatch.setenv("NEAR_GREEN_REPLANNED_ONCE", "off")
    _measured(tmp_path, 17, 1)
    assert end_of_attempt.decide(str(tmp_path), [], replans=1, best_history=[]).outcome == end_of_attempt.REPLAN


def test_it_is_a_registered_efficiency_switch_whose_firing_the_audit_reads():
    assert "NEAR_GREEN_REPLANNED_ONCE" in switches.GROUPS["Efficiency"]
    assert "NEAR_GREEN_REPLANNED_ONCE" in provenance.SWITCHES
    assert switch_firing.SIGNALS["NEAR_GREEN_REPLANNED_ONCE"] == near_green_once.SAID
