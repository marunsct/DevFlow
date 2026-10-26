"""A sprint planned again twice with no gain over the best product goes to the escalation (behind `STALL_RULE`).

Measured on three runs: a browser app and two services sat at the same number of criteria passing for 30 to 60 minutes
while the sprint was drafted, fixed and planned again; the best product was kept and no later attempt beat it.
"""
from __future__ import annotations

import inspect
import json

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


def _replan_source() -> str:
    source = inspect.getsource(workflow)
    start = source.index("def _replan_or_escalate(")
    return source[start:source.index("def defect_remediation_node(", start)]


def test_the_replan_asks_and_keeps_the_history():
    body = _replan_source()
    assert "stalled_sprint.stalled(" in body
    assert body.index("stalled_sprint.stalled(") < body.index("if revision_count > MAX_MILESTONE_REVISIONS:")
    assert "sprint_best_history=best_history" in body
    assert "sprint_best_history" in workflow.WorkflowGraphState.__annotations__


def test_the_history_starts_again_with_the_next_sprint():
    source = inspect.getsource(workflow)
    advance = source[source.index('"revision_comments": [],'):][:260]
    assert '"sprint_best_history": []' in advance
