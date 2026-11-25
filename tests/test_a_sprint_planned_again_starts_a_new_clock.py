"""A sprint the escalation plans again for its foundation starts its time budget at the re-plan (LF.1448).

Measured on a medium run (deep review 2026-11-25, decisions finding 9): the fix round was stopped at 219 active minutes
against 102, the escalation then chose "plan sprint 1 again" for its foundation, and the new attempt began on the same
clock, already past twice its limit; at its next test round it was ended by it and the run stopped, with four defects
that round had just raised never sent to a fixer. The minutes between a stop and its resume were on the clock too. The
transcript heads (time, stage, kind) are the run's own, from the suite's lock to the re-planned attempt's first test
round.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.graph import sprint_time_budget

HEADS = Path(__file__).parent / "captured" / "transcript-heads-a-sprint-planned-again.jsonl"
#: When the escalation planned the sprint again, and when the new attempt's first test round raised its defects.
REPLANNED_AT = "2026-11-25T11:15:37.992063+00:00"
FIRST_ROUND = datetime.fromisoformat("2026-11-25T12:37:16.521032+00:00")
SPRINT = SimpleNamespace(criteria=["AC-1", "AC-8", "AC-12", "AC-13", "AC-14", "AC-15"], in_scope=[], advice=[])


@pytest.fixture
def run(monkeypatch, tmp_path):
    monkeypatch.setenv("SPRINT_TIME_BUDGET", "on")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data" / "transcripts").mkdir(parents=True)
    shutil.copy(HEADS, tmp_path / "data" / "transcripts" / "r.jsonl")
    return tmp_path


def _state(root: Path, **more) -> dict:
    return {"sprint_plan": SimpleNamespace(sprints=[SPRINT, SimpleNamespace(criteria=["AC-2"], in_scope=[])]),
            "current_sprint_index": 0, "repository": SimpleNamespace(root_path=str(root)), **more}


def test_the_re_planned_attempt_is_measured_from_its_re_plan(run):
    state = _state(run, foundation_replanned_sprints=[0], foundation_replanned_at=REPLANNED_AT)

    budget = sprint_time_budget.measure(state, run_id="r", now=FIRST_ROUND)

    assert budget is not None
    assert not budget.ends_the_fix_round()
    assert budget.minutes < budget.limit


def test_the_minutes_between_a_stop_and_its_resume_are_off_the_clock(run):
    since = datetime.fromisoformat(REPLANNED_AT)

    assert sprint_time_budget.resumed_minutes(HEADS, since) == pytest.approx(6.95, abs=0.1)
