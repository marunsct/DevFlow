"""A milestone plan made for a different sprint than the one being planned is sent back.

Measured over 889 stored plans: twice a lead asked to plan sprint 1 returned
sprint 2's goal word for word. The rule names exactly those two, and none of
the other 887, which restate their own sprint's goal in other words as often
as not.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.analysis.work_orders import another_sprints_plan, readiness_problems

GOALS = [
    "Users can add items with a title and optional description, see them in a list, "
    "and empty titles are rejected with an inline error message.",
    "Users can mark items complete/incomplete via a 'Done' control and remove items "
    "with a 'Delete' control on each row.",
    "Users can click 'Edit' on an item to change its title inline, save the new title, "
    "or press Escape to cancel without saving.",
    "Users can filter displayed items by status (All, Active, Completed) and all data "
    "persists correctly across page reloads.",
    "The application is fully functional at both mobile (375px) and desktop (1280px) "
    "viewport widths with no horizontal scrolling.",
]


def _plan(goal: str) -> SimpleNamespace:
    return SimpleNamespace(selected_sprint_goal=goal, delegated_tasks=[])


def test_another_sprint_s_goal_is_named() -> None:
    why = another_sprints_plan(_plan(GOALS[3]), GOALS, 1)

    assert "sprint 4" in why and "sprint 2" in why


@pytest.mark.parametrize("goal", [
    GOALS[1],
    # Restated, as a lead does.
    "Mark items complete or incomplete with the Done control, and delete items with "
    "the Delete control on each row",
    # Shorter than the plan's own words, and close to no other sprint.
    "Done and Delete controls on each row",
])
def test_the_sprint_being_planned_however_it_is_put_passes(goal) -> None:
    assert another_sprints_plan(_plan(goal), GOALS, 1) == ""


@pytest.mark.parametrize("sprint_goals, index", [((), 0), (GOALS, 9), (GOALS, -1)])
def test_without_a_sprint_plan_to_compare_nothing_is_said(sprint_goals, index) -> None:
    assert another_sprints_plan(_plan(GOALS[3]), sprint_goals, index) == ""


def test_it_reaches_the_lead_as_the_plan_s_one_problem(monkeypatch) -> None:
    monkeypatch.setattr("app.analysis.work_orders.readiness_enforced", lambda: True)
    plan = _plan(GOALS[3])
    plan.delegated_tasks = [SimpleNamespace(role="backend", files=[], test_cases=[])]

    problems = readiness_problems(plan, None, sprint_goals=GOALS, sprint_index=1)

    assert len(problems) == 1 and "sprint 4" in problems[0]
