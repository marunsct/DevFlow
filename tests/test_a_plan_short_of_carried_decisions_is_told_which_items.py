"""A plan with fewer carried-forward decisions than items is told the items, numbered, not only the two counts.

Measured on three runs: told "8 item(s) were carried forward ... records 4", the lead returned the same short list
three times and the plan went out with the problem noted.
"""
from __future__ import annotations

import re

from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.analysis.work_orders import readiness_problems

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_items_are_listed_by_number(monkeypatch):
    monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "on")
    plan = MilestonePlanOutput(
        selected_sprint_goal="g",
        delegated_tasks=[SpecialistTask(specialist_role="testing", task_description="Write the unit tests", acceptance_criteria=["they run"])],
        carried_forward_decisions=["1. taken by the backend work order"],
    )
    items = ["A 500 on a long password (sprint 1 review)", "A 204 with a body type (sprint 1 review)"]

    problem = next(p for p in readiness_problems(plan, "/nonexistent", carried_forward=items)
                   if "carried forward from earlier sprints" in p)

    assert "  1. A 500 on a long password" in problem and "  2. A 204 with a body type" in problem
    assert "starting with its number" in problem
    assert not BANNED.search(problem.split("The items:")[0])
