"""A sprint's time budget measures the sprint's own work: an attempt gets its first fix round, the adopted specialist
items placed in the sprint count toward its size, and a model server failing is not the sprint's time.

Measured on one medium run: a first sprint of 6 criteria with 29 adopted specialist items placed in it (SP.2) read 219
active minutes against its 102 at its first test round - 22 of them a proxy answering every model call with a time-out
- so its fix round sent not one fixer for its five defects, one a real blocker, and the sprint was planned again with
no fix tried.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import the_fix_stage

from app.graph import sprint_time_budget
from app.sprint import RemediationCycle

#: One sprint delivering one criterion: a budget of 42 active minutes, so twice over is past 84.
PLAN = SimpleNamespace(sprints=[SimpleNamespace(criteria=["AC-1"], in_scope=[])])
FAR_PAST = 100
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def _fixer(stage: str) -> dict:
    return {"stage": stage, "files": ["app/count.js"], "did": "", "outcome": "left open"}


@pytest.fixture
def transcript(monkeypatch, tmp_path):
    """Write this run's transcript from (minutes before now, stage, kind) entries."""
    monkeypatch.setenv("SPRINT_TIME_BUDGET", "on")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "r")
    (tmp_path / "data" / "transcripts").mkdir(parents=True)

    def written(entries, *, now: datetime) -> None:
        lines = [json.dumps({"at": (now - timedelta(minutes=ago)).isoformat(), "run_id": "r", "stage": stage,
                             "kind": kind}) for ago, stage, kind in entries]
        (tmp_path / "data" / "transcripts" / "r.jsonl").write_text("\n".join(lines) + "\n")

    return written


def _worked_for(minutes: int):
    """A sprint that has worked for `minutes` active minutes up to now, a model call every ten."""
    return [(minutes - step, "technical_lead" if step == 0 else "specialist_backend_0", "model_response")
            for step in range(0, minutes, 10)]


def _time_budget_records(tmp_path) -> list[dict]:
    path = tmp_path / "data" / "transcripts" / "r.jsonl"
    return [entry for entry in map(json.loads, path.read_text().splitlines()) if entry.get("kind") == "time_budget"]


# --- An attempt gets its first fix round (LF.1396) ---

@pytest.mark.parametrize("side_by_side", [False, True])
def test_far_past_its_budget_an_attempt_s_first_fix_round_still_sends_its_fixer(tmp_path, transcript, side_by_side):
    transcript(_worked_for(FAR_PAST), now=datetime.now(timezone.utc))
    state = the_fix_stage.a_state(tmp_path, the_fix_stage.a_defect(), sprint_plan=PLAN)

    _, seen = the_fix_stage.run(tmp_path, state, side_by_side=side_by_side)

    assert "agent loop" in seen.events
    assert _time_budget_records(tmp_path) == []


def test_the_first_fix_round_sends_every_fixer_of_its_round_not_only_the_first(tmp_path, transcript):
    """One defect of round 2 already worked in round 2: the next one's fixer still goes, the round is the attempt's
    first."""
    transcript(_worked_for(FAR_PAST), now=datetime.now(timezone.utc))
    worked = the_fix_stage.a_defect(attempts=[_fixer("defect_fix_2_0")], status="fixed")
    state = the_fix_stage.a_state(tmp_path, worked, the_fix_stage.a_defect("The total is wrong",
                                  affected_files=["app/total.js"]), sprint_plan=PLAN, fixes_tried=["defect_fix_2_0"])

    _, seen = the_fix_stage.run(tmp_path, state)

    assert "agent loop" in seen.events


def test_far_past_its_budget_an_attempt_s_first_test_round_starts_its_fix_round(tmp_path, transcript):
    from workflow_nodes import a_test_round, reported

    transcript(_worked_for(FAR_PAST), now=datetime.now(timezone.utc))

    update, _ = a_test_round(tmp_path, [reported("Saving an entry returns 500")], state={"sprint_plan": PLAN})

    assert update["stage"] == "defect_remediation"


@pytest.mark.parametrize("stage, test_round, recorded, already", [
    ("test_round_1", 1, [], False),                            # nothing sent yet: the round goes
    ("test_round_1", 1, ["defect_fix_1_0"], True),             # after the first fix round: the stop applies
    ("defect_fix_2", 2, ["defect_fix_2_0"], False),            # inside the first fix round
    ("defect_fix_2", 2, ["defect_fix_1_0", "defect_fix_2_1"], True),  # the second fix round
])
def test_the_stop_applies_from_the_round_after_the_attempt_s_first_fix_round(stage, test_round, recorded, already):
    """The 891-minute attempt stays bounded: after one fix round, every later test round and fixer is stopped."""
    cycle = RemediationCycle(sprint_goal="g", defects=[the_fix_stage.a_defect(attempts=[_fixer(s) for s in recorded])])

    found = sprint_time_budget.a_fix_round_already_sent({"remediation": cycle, "test_round": test_round}, stage=stage)

    assert found is already


# --- Adopted specialist items count toward the sprint's size (LF.1397) ---

def test_the_adopted_specialist_items_placed_in_a_sprint_add_to_its_budget(tmp_path, transcript):
    transcript(_worked_for(150), now=NOW)
    sprint = SimpleNamespace(criteria=["AC-1", "AC-8", "AC-12", "AC-13", "AC-14", "AC-15"],
                             in_scope=["Backend: auth endpoints", "Database: migrations (DB-9)"],
                             advice=["UX-1", "UX-2", "DB-1", "BE-2", "SR-1", "TS-1"])
    state = {"sprint_plan": SimpleNamespace(sprints=[sprint]), "current_sprint_index": 0,
             "repository": SimpleNamespace(root_path=str(tmp_path))}

    budget = sprint_time_budget.measure(state, run_id="r", now=NOW)

    # 30 + 12 x 6 criteria + 4 x 7 items (six placed, one named by its scope).
    assert budget is not None and budget.limit == 130
    assert "7 adopted specialist items" in budget.why(tmp_path)


def test_the_words_with_its_items_name_no_product_word(tmp_path):
    text = sprint_time_budget.Budget(minutes=300, limit=218, size=6, items=29).why(tmp_path)
    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
        assert not re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE), word


# --- A model server failing is not the sprint's time (LF.1398) ---

def _a_sprint_whose_server_failed():
    """80 minutes from the plan with an 18-minute streak of failed calls in it: five calls, each failing after 2
    minutes and asked again 2 minutes later, before a call that answers."""
    entries = [(80, "technical_lead", "model_request"), (70, "technical_lead", "model_response"),
               (60, "specialist_backend_0", "model_request"), (50, "specialist_backend_0", "model_response"),
               (50, "specialist_testing_3", "model_request")]
    for call in range(5):
        start = 50 - 4 * call
        entries += [(start - 2, "specialist_testing_3", "model_error"),
                    (start - 3, "specialist_testing_3", "request_budget"),
                    (start - 4, "specialist_testing_3", "model_request")]
    return entries + [(20, "specialist_testing_3", "model_response"), (0, "test_round_0", "model_response")]


def test_minutes_inside_a_streak_of_failed_model_calls_are_not_the_sprint_s(tmp_path, transcript):
    transcript(_a_sprint_whose_server_failed(), now=NOW)

    budget = sprint_time_budget.measure(the_fix_stage.a_state(tmp_path, the_fix_stage.a_defect(), sprint_plan=PLAN),
                                        run_id="r", now=NOW)

    # 80 minutes from the plan, less the streak: from the call that failed first (at 50) to the last failure (at 32).
    assert budget is not None and budget.minutes == 62


def test_a_failed_call_on_a_review_stage_is_taken_off_once(tmp_path, transcript):
    transcript([(40, "technical_lead", "model_response"), (30, "code_review_0_0", "model_request"),
                (20, "code_review_0_0", "model_error"), (10, "code_review_0_0", "model_response"),
                (8, "test_round_0", "model_request"), (4, "test_round_0", "model_error"),
                (0, "test_round_0", "model_response")], now=NOW)

    budget = sprint_time_budget.measure(the_fix_stage.a_state(tmp_path, the_fix_stage.a_defect(), sprint_plan=PLAN),
                                        run_id="r", now=NOW)

    # 40 minutes: the review stage's 30 off the clock once, whether or not a call of it failed; the test round's
    # failed call's 4 off too.
    assert budget is not None and budget.minutes == 6
