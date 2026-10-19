"""The run page reads a run's sprints as figures, not by parsing their documents (plan BG.6).

The sprint panel drew its timeline by reading each `docs/sprint_N_summary.md`
and parsing the rendered markdown back into numbers, so any change to the
document's wording broke the panel's figures silently. The route serves the
attempts the documents are rendered from, and the fix loop says how many of its
defects are still open.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.agents.sprint_summary import render_sprint_summary, sprint_views
from app.server.runs import _remediation_info

PLAN = SimpleNamespace(sprints=[
    SimpleNamespace(goal="Accounts", in_scope=["Register", "Sign in"]),
    SimpleNamespace(goal="Items", in_scope=["Add an item"]),
])

FAILED = {
    "sprint_index": 0, "number": 1, "status": "Failed", "reason": "the suite stayed red",
    "cases": {"tests": 20, "passed": 15, "failed": 5}, "rounds": 3, "features": ["Register"],
    "defects": [{"status": "open", "description": "Sign-in accepts an empty password", "owner": "backend"}],
}
PASSED = {
    "sprint_index": 0, "number": 2, "status": "Completed", "reason": "",
    "cases": {"tests": 30, "passed": 30, "failed": 0}, "rounds": 2, "features": ["Register", "Sign in"],
    "defects": [
        {"status": "fixed", "description": "Sign-in accepts an empty password", "owner": "backend"},
        {"status": "open", "description": "The error is not announced", "owner": "frontend"},
    ],
}


def test_each_attempted_sprint_with_its_latest_attempt_and_history():
    (view,) = sprint_views(PLAN, [FAILED, PASSED])

    assert (view["number"], view["planned_total"], view["goal"], view["status"]) == (1, 2, "Accounts", "Completed")
    assert view["attempts"] == 2 and view["failure_reason"] == ""
    assert view["planned"] == ["Register", "Sign in"]
    assert (view["test_cases"], view["cases_passed"], view["cases_failed"], view["test_rounds"]) == (30, 30, 0, 2)
    assert (view["total_bugs"], view["fixed_bugs"], view["open_bugs"]) == (2, 1, 1)
    assert len(view["attempt_history"]) == 2 and view["attempt_history"][0].startswith("**Attempt 1** (first attempt) - Failed")


def test_a_sprint_without_counts_says_none_rather_than_zero():
    (view,) = sprint_views(PLAN, [{**FAILED, "cases": None}])
    assert view["test_cases"] is None and view["failure_reason"] == "the suite stayed red"


def test_the_document_still_carries_the_same_history():
    document = render_sprint_summary(sprint_number=1, total_sprints=2, goal="Accounts", planned=["Register"], attempts=[FAILED, PASSED])
    for line in sprint_views(PLAN, [FAILED, PASSED])[0]["attempt_history"]:
        assert line in document


def test_the_fix_loop_counts_its_open_defects():
    cycle = SimpleNamespace(
        attempt=2, max_attempts=3, escalated=False, test_runs=[1, 2, 3],
        defects=[SimpleNamespace(status="open"), SimpleNamespace(status="fixed"), SimpleNamespace(status="open")],
    )
    info = _remediation_info(cycle)
    assert (info.defect_count, info.open_defects, info.test_runs) == (3, 2, 3)
    assert _remediation_info(None) is None


def test_the_route_serves_a_new_run_s_sprints_as_none_yet(client, tmp_path: Path):
    brief = tmp_path / "brief.md"
    brief.write_text("A product")
    with open(brief, "rb") as handle:
        run_id = client.post("/api/runs", files=[("files", ("brief.md", handle, "text/plain"))]).json()["run_id"]

    response = client.get(f"/api/runs/{run_id}/sprints")

    assert response.status_code == 200 and response.json() == {"sprints": []}
