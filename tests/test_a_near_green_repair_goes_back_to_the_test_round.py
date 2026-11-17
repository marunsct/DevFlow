"""A suite repaired at a re-plan's entry that leaves the sprint near green is measured again in a test round, not
planned again (LR.53, `NEAR_GREEN_REPAIR_TO_ROUND`, Efficiency group).

Of 45 near-green re-plans that beat the best attempt, 19 got there from the dispute's repair alone, then re-planned for
about 25 more minutes. And a suite sent back to the round from there needs a plan to measure against: the re-plan's
entry clears it, and a round with none sends the run on to the lead's re-plan anyway.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.graph import acceptance_nodes, near_green_repair, workflow
from workflow_nodes import an_acceptance_review

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


ADDS = [f"[AC-1] adds note {n}" for n in range(16)]
SUITE = "".join(f"test('{name}', async () => {{}});\n" for name in [*ADDS, "[AC-2] deletes", "[AC-3] persists"])


def _locked_after_a_repair(tmp_path, monkeypatch):
    """The lock of a suite repaired at a re-plan's entry, whose run passes 17 of 18 tests, with the plan cleared."""
    monkeypatch.setenv("NEAR_GREEN_REPAIR_TO_ROUND", "on")
    sprint_plan = SimpleNamespace(sprints=[SimpleNamespace(goal="first", criteria=[]),
                                           SimpleNamespace(goal="the second goal", criteria=[])])
    return an_acceptance_review(tmp_path, SUITE, passed=[*ADDS, "[AC-3] persists"], failed=["[AC-2] deletes"], state={
        "acceptance_return_to": "sprint_replan", "milestone_plan": None, "sprint_plan": sprint_plan,
        "current_sprint_index": 1})


def test_the_lock_goes_to_a_test_round_and_records_why(tmp_path, monkeypatch):
    update = _locked_after_a_repair(tmp_path, monkeypatch)

    assert update["stage"] == "test_and_triage"
    assert update["decisions"][-1]["decision"] == "measure it again in a test round"
    assert "near green" in update["decisions"][-1]["rationale"]


def test_the_round_it_goes_back_to_has_a_plan_to_measure_against(tmp_path, monkeypatch):
    update = _locked_after_a_repair(tmp_path, monkeypatch)

    # The re-plan's entry cleared the plan; a round with none sends the run back to the lead.
    assert workflow._missing_upstream(update, "milestone_plan") is None
    assert update["milestone_plan"].selected_sprint_goal == "the second goal"
    assert not update["milestone_plan"].delegated_tasks


def test_a_plan_the_round_already_has_is_the_one_it_measures():
    kept = SimpleNamespace(selected_sprint_goal="kept")
    assert acceptance_nodes.the_plan_a_round_measures({"milestone_plan": kept}) is kept


def test_its_words_use_none_of_the_banned_ones():
    assert not BANNED.search(near_green_repair.SAID)
    assert not BANNED.search(acceptance_nodes.NO_NEW_PLAN)
