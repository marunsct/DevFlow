"""A suite repaired at a re-plan's entry that leaves the sprint near green is measured again in a test round, not
planned again (LR.53, `NEAR_GREEN_REPAIR_TO_ROUND`, Efficiency group).

Of 45 near-green re-plans that beat the best attempt, 19 got there from the dispute's repair alone, then re-planned for
about 25 more minutes. And a suite sent back to the round from there needs a plan to measure against: the re-plan's
entry clears it, and a round with none sends the run on to the lead's re-plan anyway.
"""
from __future__ import annotations

import inspect
import re
from types import SimpleNamespace

from app.graph import acceptance_nodes, near_green_repair, workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _result(passed, failed, ran=True):
    tests = [SimpleNamespace(outcome="passed")] * passed + [SimpleNamespace(outcome="failed")] * failed
    return SimpleNamespace(ran=ran, report=SimpleNamespace(tests=tests, passed=passed, failed=failed))


def test_on_a_near_green_repair_is_measured_again(tmp_path, monkeypatch):
    monkeypatch.setenv("NEAR_GREEN_REPAIR_TO_ROUND", "on")
    assert acceptance_nodes.why_measured_again(tmp_path, _result(17, 1)) == acceptance_nodes.NEAR_GREEN
    assert acceptance_nodes.why_measured_again(tmp_path, _result(27, 3)) == acceptance_nodes.NEAR_GREEN


def test_far_from_green_not_run_or_off_it_is_planned_again(tmp_path, monkeypatch):
    monkeypatch.setenv("NEAR_GREEN_REPAIR_TO_ROUND", "on")
    assert acceptance_nodes.why_measured_again(tmp_path, _result(6, 3)) == ""
    assert acceptance_nodes.why_measured_again(tmp_path, _result(17, 1, ran=False)) == ""
    monkeypatch.setenv("NEAR_GREEN_REPAIR_TO_ROUND", "off")
    assert acceptance_nodes.why_measured_again(tmp_path, _result(17, 1)) == ""


def test_the_lock_records_the_decision_in_the_switch_s_words():
    source = inspect.getsource(acceptance_nodes.acceptance_review)
    at = source.index("measured_again == NEAR_GREEN")
    branch = source[at:at + 1400]
    assert "near_green_repair.SAID" in branch and 'stage = "test_and_triage"' in branch


def test_the_round_it_goes_back_to_has_a_plan_to_measure_against():
    sprint_plan = SimpleNamespace(sprints=[SimpleNamespace(goal="first"), SimpleNamespace(goal="the second goal")])
    state = {"milestone_plan": None, "sprint_plan": sprint_plan, "current_sprint_index": 1}
    # As the re-plan's entry leaves it, the round sends the run back to the lead.
    assert workflow._missing_upstream(state, "milestone_plan") is not None
    plan = acceptance_nodes.the_plan_a_round_measures(state)
    assert plan.selected_sprint_goal == "the second goal" and not plan.delegated_tasks
    assert workflow._missing_upstream({**state, "milestone_plan": plan}, "milestone_plan") is None
    kept = SimpleNamespace(selected_sprint_goal="kept")
    assert acceptance_nodes.the_plan_a_round_measures({**state, "milestone_plan": kept}) is kept
    source = inspect.getsource(acceptance_nodes.acceptance_review)
    assert '"milestone_plan": the_plan_a_round_measures(state)' in source


def test_its_words_use_none_of_the_banned_ones():
    assert not BANNED.search(near_green_repair.SAID)
    assert not BANNED.search(acceptance_nodes.NO_NEW_PLAN)
