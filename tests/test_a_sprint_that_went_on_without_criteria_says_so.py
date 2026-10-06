"""A sprint the run went on from without some criteria says which, beside its status.

One run's sprint 4 could not be finished; its two failing criteria were deferred
by an automatic decision and the run went on. Its record read "Status:
Completed", with nothing to say the sprint had not delivered them.
"""

from __future__ import annotations

from app.agents.sprint_summary import render_sprint_summary
from app.graph.workflow import _deferred_in_this_attempt


def _decision(point: str, affects: list[str], at: str) -> dict:
    return {"id": "DR-1", "point": point, "affects": affects, "decided_at": at}


def test_this_attempt_s_deferrals_are_found() -> None:
    state = {"decisions": [
        _decision("escalation", ["AC-1"], "2026-10-06T01:00:00+00:00"),   # an earlier sprint's
        _decision("sprint", [], "2026-10-06T03:00:00+00:00"),
        _decision("escalation", ["AC-5", "AC-8"], "2026-10-06T04:34:41+00:00"),
    ]}

    assert _deferred_in_this_attempt(state, "2026-10-06T02:00:00+00:00") == ["AC-5", "AC-8"]


def test_a_sprint_that_deferred_nothing_has_none() -> None:
    assert _deferred_in_this_attempt({"decisions": []}, None) == []


def test_the_status_line_names_them() -> None:
    page = render_sprint_summary(
        sprint_number=4, total_sprints=5, goal="Filter the list", planned=[],
        attempts=[{"number": 1, "status": "Completed", "deferred": ["AC-5", "AC-8"]}],
    )

    status = next(line for line in page.splitlines() if line.startswith("**Status:**"))
    assert "Completed" in status and "without AC-5, AC-8" in status and "did not deliver" in status


def test_a_sprint_that_delivered_everything_reads_as_before() -> None:
    page = render_sprint_summary(
        sprint_number=1, total_sprints=5, goal="Add items", planned=[],
        attempts=[{"number": 1, "status": "Completed"}],
    )

    assert "**Status:** Completed\n" in page
