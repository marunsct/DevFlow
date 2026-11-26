"""A regression, or a definition removed that another file uses, stays with the sprint that broke it (LF.1530).

Measured on a medium run: a test round's seven defects - regressions of the sprint's own sign-in criteria and
definitions its fixers removed - were read as later sprints' work by the files and actions they name, logged "about
work a later sprint builds; left for that sprint, not fixed in this one", and the sprint was accepted with them open.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph import workflow
from app.analysis import integration_checks

REGRESSION = ("Regression: `acceptance: auth.spec.js › auth.spec.js › [AC-1] registered user can log in` passed "
              "before this batch of work orders and fails now.")
REMOVED = ("`Base` was removed from `task-management-dashboard/task_management_dashboard/models.py` by "
           "specialist_database_0, and `task-management-dashboard/task_management_dashboard/database.py` still uses it.")
LATER = "The analytics page is missing: no chart of tasks done per week."


def _split(monkeypatch, *descriptions):
    monkeypatch.setattr(workflow, "_what_later_sprints_build", lambda state: {"files": ["models.py"]})
    monkeypatch.setattr(workflow, "_what_this_sprint_builds", lambda state: {})
    monkeypatch.setattr(integration_checks, "later_sprint_files_in", lambda description, now, later: True)
    monkeypatch.setattr(integration_checks, "later_sprint_work_in", lambda description, now, later: False)
    import app.graph.acceptance_nodes as acceptance_nodes

    monkeypatch.setattr(acceptance_nodes, "criteria_only_later", lambda state, text: False)
    return workflow._defects_a_later_sprint_builds([SimpleNamespace(description=d) for d in descriptions], {})


def test_a_regression_and_a_removed_definition_stay_with_this_sprint(monkeypatch):
    kept, moved = _split(monkeypatch, REGRESSION, REMOVED)

    assert [d.description for d in kept] == [REGRESSION, REMOVED]
    assert moved == []


def test_other_work_a_later_sprint_owns_still_moves(monkeypatch):
    kept, moved = _split(monkeypatch, LATER)

    assert kept == [] and [d.description for d in moved] == [LATER]
