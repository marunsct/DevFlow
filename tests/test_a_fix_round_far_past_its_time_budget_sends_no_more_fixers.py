"""A sprint far past its time budget sends no more fixers: the attempt goes to its end-of-attempt decision.

Measured on one run: the sprint time budget (`SPRINT_TIME_BUDGET`) was read only when an attempt ended, last in its
order, and an attempt with defects left kept sending fixers, so one sprint ran 891 active minutes against its 126.
Read inside the attempt too - at each test round and before each fixer - once the sprint has run twice its budget,
the fix round stops; nearer than that it goes on, so a sprint close to green is not cut. Off, nothing changes.
The stop applies once the attempt has had its first fix round (its first round is
`test_a_sprint_s_time_budget_measures_its_own_work.py`'s), so these sprints have one behind them.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import the_fix_stage

from app.graph import sprint_time_budget

#: One sprint delivering one criterion: a budget of 42 active minutes, so twice over is past 84.
PLAN = SimpleNamespace(sprints=[SimpleNamespace(criteria=["AC-1"], in_scope=[])])
FAR_PAST = 100
PAST_BUT_NOT_TWICE = 60


@pytest.fixture
def a_sprint_that_has_run(monkeypatch, tmp_path):
    """Write this run's transcript as a sprint that has worked for `minutes` active minutes up to now."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "r")
    (tmp_path / "data" / "transcripts").mkdir(parents=True)

    def written(minutes: int) -> None:
        now = datetime.now(timezone.utc)
        lines = [json.dumps({"at": (now - timedelta(minutes=minutes - step)).isoformat(), "run_id": "r",
                             "stage": "technical_lead" if step == 0 else "defect_fix_1_0", "kind": "model_request"})
                 for step in range(0, minutes, 10)]
        (tmp_path / "data" / "transcripts" / "r.jsonl").write_text("\n".join(lines) + "\n")

    return written


def _recorded(tmp_path) -> list[dict]:
    path = tmp_path / "data" / "transcripts" / "r.jsonl"
    return [entry for entry in map(json.loads, path.read_text().splitlines()) if entry.get("kind") == "time_budget"]


@pytest.mark.parametrize("minutes, limit, stops", [(253, 126, True), (252, 126, False), (130, 126, False)])
def test_a_fix_round_stops_only_once_the_sprint_has_run_twice_its_budget(minutes, limit, stops):
    assert sprint_time_budget.Budget(minutes=minutes, limit=limit, size=8).ends_the_fix_round() is stops


#: A fixer this attempt sent in its first fix round; the fix stages below are in round 2.
EARLIER_FIXER = {"stage": "defect_fix_1_0", "files": ["app/count.js"], "did": "", "outcome": "left open"}


@pytest.mark.parametrize("side_by_side", [False, True])
def test_far_past_its_budget_the_round_sends_no_fixer_and_the_attempt_ends(
        monkeypatch, tmp_path, a_sprint_that_has_run, side_by_side):
    monkeypatch.setenv("SPRINT_TIME_BUDGET", "on")
    a_sprint_that_has_run(FAR_PAST)
    state = the_fix_stage.a_state(tmp_path, the_fix_stage.a_defect(attempts=[EARLIER_FIXER]),
                                  the_fix_stage.a_defect("The total is wrong", affected_files=["app/total.js"]),
                                  sprint_plan=PLAN)

    update, seen = the_fix_stage.run(tmp_path, state, side_by_side=side_by_side)

    assert "agent loop" not in seen.events and not update.get("fix_batch")
    assert update["stage"] == "escalation"
    assert sprint_time_budget.SAID in json.dumps(update, default=str)
    [entry] = _recorded(tmp_path)
    assert entry["message"].startswith(sprint_time_budget.SAID)
    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
        assert not re.search(rf"\b{re.escape(word)}\b", entry["message"], re.IGNORECASE), word


@pytest.mark.parametrize("switch, minutes", [("on", PAST_BUT_NOT_TWICE), ("off", FAR_PAST)])
def test_nearer_its_budget_or_with_the_budget_off_the_fixer_is_sent(
        monkeypatch, tmp_path, a_sprint_that_has_run, switch, minutes):
    monkeypatch.setenv("SPRINT_TIME_BUDGET", switch)
    a_sprint_that_has_run(minutes)

    _, seen = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, the_fix_stage.a_defect(), sprint_plan=PLAN))

    assert "agent loop" in seen.events
    assert _recorded(tmp_path) == []


@pytest.mark.parametrize("minutes, stage", [(FAR_PAST, "escalation"), (PAST_BUT_NOT_TWICE, "defect_remediation")])
def test_a_test_round_far_past_its_budget_starts_no_fix_round(
        monkeypatch, tmp_path, a_sprint_that_has_run, minutes, stage):
    from workflow_nodes import a_test_round, reported

    from app.sprint import RemediationCycle

    monkeypatch.setenv("SPRINT_TIME_BUDGET", "on")
    a_sprint_that_has_run(minutes)
    after_a_fix_round = RemediationCycle(sprint_goal="g", defects=[the_fix_stage.a_defect(attempts=[EARLIER_FIXER])])

    update, _ = a_test_round(tmp_path, [reported("Saving an entry returns 500")],
                             state={"sprint_plan": PLAN, "remediation": after_a_fix_round})

    assert update["stage"] == stage


def test_a_thorough_sprint_s_review_stages_are_not_on_its_clock(monkeypatch, tmp_path):
    """Measured on one medium run: the budget's pace came from runs with no review stages, and a sprint's code,
    security, advice and milestone reviews (about 75 active minutes) counted against its 66-minute budget."""
    monkeypatch.setenv("SPRINT_TIME_BUDGET", "on")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "r")
    (tmp_path / "data" / "transcripts").mkdir(parents=True)
    now = datetime.now(timezone.utc)
    stages = ["technical_lead"] + ["specialist_backend_0"] * 3 + ["code_review_0_0"] * 6 + ["security_review"] * 6 \
        + ["advice_review_backend"] * 3 + ["defect_fix_1_0"] * 2
    lines = [json.dumps({"at": (now - timedelta(minutes=10 * (len(stages) - n))).isoformat(), "run_id": "r",
                         "stage": stage, "kind": "model_request"}) for n, stage in enumerate(stages)]
    (tmp_path / "data" / "transcripts" / "r.jsonl").write_text("\n".join(lines) + "\n")
    state = the_fix_stage.a_state(tmp_path, the_fix_stage.a_defect(), sprint_plan=PLAN)

    budget = sprint_time_budget.measure(state, run_id="r", now=now)

    # 21 entries 10 minutes apart: 210 minutes in all, 150 of them ending on a review stage's entry.
    assert budget is not None and budget.minutes == 60.0
