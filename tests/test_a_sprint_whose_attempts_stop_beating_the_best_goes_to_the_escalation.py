"""A sprint planned again twice with no gain over the best product goes to the escalation (behind `STALL_RULE`).

Measured on three runs: a browser app and two services sat at the same number of criteria passing for 30 to 60 minutes
while the sprint was drafted, fixed and planned again; the best product was kept and no later attempt beat it.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.graph import stalled_sprint, workflow


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("STALL_RULE", "on")


@pytest.mark.parametrize("history, expected", [
    ([4, 11, 13, 15, 15, 15], True),
    ([4, 11, 13, 15, 15], False),      # one flat attempt is given another
    ([4, 11, 13], False),               # still rising
    ([15, 15, 15], True),
    ([0, 0, 0], False),                 # nothing was ever kept: no rule
    ([5, 5], False),
    ([], False),
])
def test_two_flat_attempts_in_a_row_stall_the_sprint(history, expected):
    assert stalled_sprint.stalled(history) is expected


def test_off_nothing_stalls(monkeypatch):
    monkeypatch.setenv("STALL_RULE", "off")
    assert stalled_sprint.stalled([15, 15, 15]) is False
    assert stalled_sprint.record("/nowhere", [1]) == [1]


def test_the_best_count_so_far_is_written_down_each_time(tmp_path):
    record = tmp_path / ".harness" / "best-attempt.json"
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"passed": 15, "commit": "abc"}))

    assert stalled_sprint.record(tmp_path, [4, 11]) == [4, 11, 15]
    assert stalled_sprint.record(tmp_path / "empty", [4]) == [4]


def test_the_replan_asks_and_keeps_the_history(tmp_path, monkeypatch):
    from workflow_node_stubs import end_an_attempt

    update, asked = end_an_attempt(monkeypatch, tmp_path, "REPLAN", sprint_best_history=[15], sprint_replan_count=1)

    assert asked[0]["best_history"] == [15] and asked[0]["replans"] == 1
    assert update["stage"] == "technical_lead" and update["sprint_replan_count"] == 2
    assert update["sprint_best_history"] == [15, 15]
    assert "sprint_best_history" in workflow.WorkflowGraphState.__annotations__


def test_a_stalled_attempt_escalates_before_the_revision_limit(tmp_path, monkeypatch):
    """The decision is read before the revision limit: a stop escalates on the first re-plan."""
    from workflow_node_stubs import end_an_attempt

    update, _ = end_an_attempt(monkeypatch, tmp_path, "STOP", sprint_best_history=[15, 15], sprint_replan_count=0)

    assert update["stage"] == "escalation"
    assert "the decision's reason" in str(update)


def test_the_history_starts_again_with_the_next_sprint(tmp_path, monkeypatch):
    from workflow_node_stubs import CONFIG, compiled, two_work_orders

    graph = compiled(monkeypatch, tmp_path)
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "milestone_plan": two_work_orders(),
             "sprint_best_history": [11, 15, 15], "current_sprint_index": 0}

    update = graph.nodes["sprint_advance"].bound.invoke(state, CONFIG)

    assert update["sprint_best_history"] == []
