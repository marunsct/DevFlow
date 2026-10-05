"""A sprint sent back by its milestone review is summarised with every plan it ran.

One run's sprint 1 built the whole page, was sent back over one XSS finding,
and its summary listed only the XSS fix under "Features Implemented", with
"Total Bugs Found: 0" and "Attempts: 1 (no re-run)" - for a sprint whose fix
rounds had found and fixed four defects and whose plan had been revised once.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.sprint_summary import render_sprint_summary
from app.graph import workflow


def _plan(*titles: str):
    return SimpleNamespace(delegated_tasks=[SimpleNamespace(title=t, task_description=t) for t in titles],
                           selected_sprint_goal="goal")


def _cycle(*descriptions: str):
    return SimpleNamespace(defects=[SimpleNamespace(status="fixed", description=d, owner="ui_ux") for d in descriptions])


def test_the_earlier_plan_s_work_and_defects_are_in_the_summary(tmp_path, monkeypatch) -> None:
    written = {}
    monkeypatch.setattr(workflow, "_record_document", lambda state, path, text: written.update({path: text}))
    monkeypatch.setattr(workflow, "_the_accepted_counts", lambda root: None)
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "current_sprint_index": 0,
        "sprint_plan": SimpleNamespace(sprints=[SimpleNamespace(goal="Add tasks", in_scope=["Build the page"])]),
        "sprint_earlier_plans": [workflow._what_a_plan_did(_plan("Build the page", "Store the tasks"),
                                                           _cycle("No UI rendered", "Title not saved"))],
        "milestone_plan": _plan("Escape quotes in titles"),
        "remediation": _cycle(),
        "test_round": 3,
    }

    update = workflow._record_sprint_summary(state, "Completed")

    document = written["docs/sprint_1_summary.md"]
    assert "Build the page" in document and "Escape quotes in titles" in document
    assert "**Total Bugs Found:** 2" in document
    assert "revised 1 time after the milestone review" in document
    assert update["sprint_earlier_plans"] == []


def test_a_sprint_never_revised_reads_as_before() -> None:
    document = render_sprint_summary(
        sprint_number=1, total_sprints=1, goal="g", planned=["p"],
        attempts=[{"number": 1, "status": "Completed", "rounds": 1, "features": ["f"], "defects": []}],
    )
    assert "**Attempts:** 1 (no re-run)" in document


def test_a_revision_keeps_the_plan_it_replaces() -> None:
    import inspect

    source = inspect.getsource(workflow)
    keep = source.index('update["sprint_earlier_plans"] = [')
    assert keep < source.index('update["remediation"] = start_remediation(milestone.selected_sprint_goal')
    assert "if revising and previous_milestone is not None:" in source[keep - 200:keep]
