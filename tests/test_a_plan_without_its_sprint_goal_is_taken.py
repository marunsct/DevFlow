"""A lead's plan that leaves out its sprint goal is taken, with the sprint's own goal.

Measured on one run: a lead's every answer left `selected_sprint_goal` out and
was refused, eight times in 12 minutes, each the whole plan again - a value
the harness already holds.
"""

from __future__ import annotations

import inspect

from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.graph import workflow


def test_a_plan_with_no_sprint_goal_is_a_valid_answer():
    plan = MilestonePlanOutput.model_validate({
        "milestone_scope": ["Fix the delete race"],
        "delegated_tasks": [SpecialistTask(
            specialist_role="backend", title="t", task_description="Fix the delete race",
            acceptance_criteria=["AC-1"], files=["notes-api/src/app.ts"],
        ).model_dump()],
    })

    assert plan.selected_sprint_goal == ""


def test_the_lead_s_plan_is_given_the_sprint_s_goal_when_it_has_none():
    source = inspect.getsource(workflow)
    node = source[source.index("    def technical_lead_node("):]
    node = node[:node.index("\n    def ", 10)]
    filled = node.index('model_copy(update={"selected_sprint_goal": current_goal})')
    assert node.index('if _hand_back(update, "milestone_plan"):') < filled < node.index("readiness_problems(")
