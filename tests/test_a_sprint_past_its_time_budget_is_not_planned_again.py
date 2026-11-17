"""A sprint has an active-minutes budget from its measured size; past it, the attempt stops (LR.42, `SPRINT_TIME_BUDGET`).

Measured over the KPI ledger: runs slower than 20 active minutes a criterion scored 0.58 of their hidden tests on
average, against 0.93-0.99 for every band under it. The budget is 30 minutes plus 12 a criterion (the ledger's 90th
percentile pace); an attempt that ends past it and would be planned again stops with the criteria still failing.
"""
from __future__ import annotations

import inspect
import json
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.acceptance import suite
from app.graph import end_of_attempt, sprint_time_budget, workflow

T0 = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)


def _measured(root, statuses):
    path = root / suite.RESULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    criteria = {cid: {"id": cid, "status": status} for cid, status in statuses.items()}
    failed = sum(status == "failed" for status in statuses.values())
    path.write_text(json.dumps({"passed": len(statuses) - failed, "failed": failed, "criteria": criteria}))


def test_the_budget_grows_with_the_sprint_s_size():
    assert sprint_time_budget.limit_for(1) == 42
    assert sprint_time_budget.limit_for(6) == 102
    assert sprint_time_budget.limit_for(0) == sprint_time_budget.limit_for(1)


def test_past_its_budget_an_attempt_that_would_be_planned_again_stops_with_what_still_fails(tmp_path):
    _measured(tmp_path, {"AC-1": "passed", "AC-2": "failed", "AC-10": "failed", "AC-3": "failed"})
    past = sprint_time_budget.Budget(minutes=130, limit=102, size=6, due=("AC-1", "AC-2", "AC-10"))
    decision = end_of_attempt.decide(str(tmp_path), [], replans=0, best_history=[], budget=past)
    assert decision.outcome == end_of_attempt.STOP
    assert sprint_time_budget.SAID in decision.why
    assert "still failing: AC-2, AC-10" in decision.why  # only the sprint's own, in id order


def test_inside_its_budget_or_unmeasured_it_is_planned_again_as_before(tmp_path):
    _measured(tmp_path, {"AC-1": "passed", "AC-2": "failed"})
    inside = sprint_time_budget.Budget(minutes=60, limit=102, size=6)
    assert end_of_attempt.decide(str(tmp_path), [], replans=0, best_history=[], budget=inside).outcome == "replan"
    assert end_of_attempt.decide(str(tmp_path), [], replans=0, best_history=[]).outcome == "replan"


def test_active_minutes_leave_out_a_pause():
    moments = [T0, T0 + timedelta(minutes=10), T0 + timedelta(hours=5), T0 + timedelta(hours=5, minutes=20)]
    assert sprint_time_budget.active_minutes(moments, T0 + timedelta(hours=5, minutes=25)) == 35


def _line(at, stage):
    return json.dumps({"at": at.isoformat(), "run_id": "r", "stage": stage, "kind": "model_request", "x": "y" * 50})


def test_measured_from_the_sprint_s_first_plan_after_the_last_sprint_ended(tmp_path, monkeypatch):
    monkeypatch.setenv("SPRINT_TIME_BUDGET", "on")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "transcripts").mkdir()
    lines = [
        _line(T0, "principal_architect"),
        _line(T0 + timedelta(minutes=30), "technical_lead"),       # the first sprint
        _line(T0 + timedelta(minutes=90), "sprint_advance"),
        _line(T0 + timedelta(minutes=95), "acceptance_check"),      # before the second sprint's plan
        _line(T0 + timedelta(minutes=100), "technical_lead"),      # the second sprint starts here
        _line(T0 + timedelta(minutes=125), "defect_fix"),
    ]
    (tmp_path / "transcripts" / "run-x.jsonl").write_text("\n".join(lines) + "\nnot json\n")
    plan = SimpleNamespace(sprints=[SimpleNamespace(criteria=["AC-1"], in_scope=[]),
                                    SimpleNamespace(criteria=["AC-2", "AC-3"], in_scope=["a", "b", "c"])])
    state = {"sprint_plan": plan, "current_sprint_index": 1, "repository": SimpleNamespace(root_path=str(tmp_path)),
             "sprint_attempts": [{"sprint_index": 0, "ended_at": (T0 + timedelta(minutes=92)).isoformat()}]}
    budget = sprint_time_budget.measure(state, run_id="run-x", now=T0 + timedelta(minutes=150))
    assert budget is not None
    assert budget.minutes == 50 and budget.size == 3 and budget.limit == sprint_time_budget.limit_for(3)
    monkeypatch.setenv("SPRINT_TIME_BUDGET", "off")
    assert sprint_time_budget.measure(state, run_id="run-x") is None


def test_the_workflow_passes_the_measured_budget_and_it_is_off_in_code():
    source = inspect.getsource(workflow)
    assert "budget=sprint_time_budget.measure(state))" in source
    assert sprint_time_budget.ON_BY_DEFAULT is False


def test_the_words_it_writes_name_no_product_word(tmp_path):
    _measured(tmp_path, {"AC-1": "failed"})
    text = sprint_time_budget.Budget(minutes=130, limit=102, size=6).why(tmp_path)
    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
        assert not re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE), word
