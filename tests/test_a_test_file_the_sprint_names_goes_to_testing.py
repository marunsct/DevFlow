"""A test file the sprint names and no work order lists is given to the testing work order.

Measured on one run: the sprint's scope named the specification's three planned
test files, the lead's plan gave them to nobody, and it was sent back three
times for it - returning the same plan each time - and then started over.
"""

from __future__ import annotations

import inspect

from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.analysis.work_orders import readiness_problems, with_named_tests_given_to_testing
from app.graph import workflow

SCOPE = ("Build the notes service: app.ts and store.ts, proven by boot-failure.test.ts, "
         "concurrency.test.ts and contract.test.ts.")


def _order(role: str, *files: str) -> SpecialistTask:
    return SpecialistTask(
        specialist_role=role, title=f"{role} work", task_description=f"Do the {role} work.",
        acceptance_criteria=["works"], files=list(files), interfaces=["f(x) -> y"], steps=["one"],
        edge_cases=["none"], test_cases=["Given x, when f, then y"], verification=["npm test"],
    )


def test_the_testing_work_order_is_given_them_at_the_planned_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "on")
    plan = MilestonePlanOutput(selected_sprint_goal="notes", delegated_tasks=[
        _order("backend", "notes-api/src/app.ts", "notes-api/src/store.ts"),
        _order("testing", "notes-api/tests/unit/store.test.ts"),
    ])
    planned = ["notes-api/tests/unit/concurrency.test.ts", "notes-api/src/app.ts"]

    given_plan, given = with_named_tests_given_to_testing(plan, str(tmp_path), SCOPE, planned)

    assert given == [
        "notes-api/tests/unit/boot-failure.test.ts",
        "notes-api/tests/unit/concurrency.test.ts",
        "notes-api/tests/unit/contract.test.ts",
    ]
    assert given_plan.delegated_tasks[1].files[1:] == given
    assert given_plan.delegated_tasks[0].files == plan.delegated_tasks[0].files
    assert not any("no work order lists" in p for p in readiness_problems(given_plan, str(tmp_path), sprint_scope=SCOPE))
    assert any("no work order lists" in p for p in readiness_problems(plan, str(tmp_path), sprint_scope=SCOPE))


def test_without_a_testing_work_order_the_lead_is_still_asked(tmp_path):
    plan = MilestonePlanOutput(selected_sprint_goal="notes", delegated_tasks=[_order("backend", "notes-api/src/app.ts")])

    assert with_named_tests_given_to_testing(plan, str(tmp_path), SCOPE) == (plan, [])


def test_the_workflow_gives_them_before_it_checks_the_plan():
    source = inspect.getsource(workflow)
    node = source[source.index("with_named_tests_given_to_testing("):]
    assert node.index("with_named_tests_given_to_testing(") < node.index("problems = readiness_problems(")
