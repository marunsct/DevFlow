"""A lead's plan that leaves out its sprint goal is taken, with the sprint's own goal.

Measured on one run: a lead's every answer left `selected_sprint_goal` out and
was refused, eight times in 12 minutes, each the whole plan again - a value
the harness already holds.
"""

from __future__ import annotations

import pytest

from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask


def test_a_plan_with_no_sprint_goal_is_a_valid_answer():
    plan = MilestonePlanOutput.model_validate({
        "milestone_scope": ["Fix the delete race"],
        "delegated_tasks": [SpecialistTask(
            specialist_role="backend", title="t", task_description="Fix the delete race",
            acceptance_criteria=["AC-1"], files=["notes-api/src/app.ts"],
        ).model_dump()],
    })

    assert plan.selected_sprint_goal == ""


@pytest.mark.parametrize("its_own, dispatched", [("", "Notes can be saved"), ("Save notes first", "Save notes first")])
def test_the_lead_s_plan_is_given_the_sprint_s_goal_when_it_has_none(tmp_path, monkeypatch, its_own, dispatched):
    """Given before the definition of ready reads the plan, so the plan is not sent back for it."""
    from workflow_node_stubs import one_sprint, run_node, two_work_orders

    checked = []
    seen = run_node(
        monkeypatch, tmp_path, "technical_lead", sprint_plan=one_sprint("Notes can be saved"),
        answer=two_work_orders().model_copy(update={"selected_sprint_goal": its_own}),
        overrides={"app.analysis.work_orders.readiness_problems":
                   lambda plan, *a, **k: checked.append(plan.selected_sprint_goal) or []},
    )

    assert checked == [dispatched]
    assert seen.update["milestone_plan"].selected_sprint_goal == dispatched
