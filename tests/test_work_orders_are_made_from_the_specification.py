"""Fast delivery's work orders are made from the specification by the harness.

One run's lead was sent back three times for test files its plan gave nobody,
returned the same plan each time and started over: 23 minutes for a plan the
specification already spelled out.
"""

from __future__ import annotations

import inspect

from app.agents.principal_architect import TechnicalSpecificationOutput
from app.analysis.work_orders import readiness_problems
from app.graph import workflow
from app.graph.planned_work import work_orders_from_the_specification

SPEC = TechnicalSpecificationOutput(
    product_scope="Notes.",
    file_plan=[
        "notes-api/src/store.ts - keeps notes",
        "notes-api/src/app.ts - routes",
        "notes-api/tests/store.test.ts - unit tests for the store",
        "notes-api/README.md - how to run it",
    ],
    function_contracts=["notes-api/src/store.ts createStore(dir: string): Store", "app.ts createApp(store): Hono"],
    implementation_order=["1. store.ts", "2. app.ts"],
    error_catalogue=["store.ts: a corrupt notes.json -> refuse to start"],
    test_cases=["store.test.ts: given an empty dir, when created, then it lists []"],
)


def test_files_go_to_who_writes_them_with_the_specification_s_own_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "on")

    plan = work_orders_from_the_specification(SPEC, "Notes", ["AC-1: create a note"], ["npm test"])

    roles = {task.specialist_role: task for task in plan.delegated_tasks}
    assert roles["backend"].files == ["notes-api/src/store.ts", "notes-api/src/app.ts"]
    assert roles["testing"].files == ["notes-api/tests/store.test.ts"]
    assert roles["documentation"].files == ["notes-api/README.md"]
    assert roles["backend"].interfaces == SPEC.function_contracts
    assert roles["backend"].edge_cases == SPEC.error_catalogue
    assert roles["testing"].test_cases == SPEC.test_cases
    assert readiness_problems(plan, str(tmp_path), sprint_scope="Build store.ts and app.ts") == []


def test_a_specification_that_plans_no_files_is_the_lead_s():
    assert work_orders_from_the_specification(TechnicalSpecificationOutput(product_scope="x"), "g", [], []) is None


def test_the_lead_is_asked_only_when_the_harness_has_no_plan():
    source = inspect.getsource(workflow)
    node = source[source.index("    def technical_lead_node("):]
    assert node.index("_the_specification_s_work_orders(state, current_goal)") < node.index('stage_name="technical_lead"')
    helper = source[source.index("    def _the_specification_s_work_orders("):source.index("    def technical_lead_node(")]
    assert "_fast_delivery()" in helper


def test_the_files_the_harness_keeps_are_no_work_order_s(tmp_path, monkeypatch):
    """One run's plan was sent back three times for package.json, package-lock.json and tsconfig.json."""
    from app.stacks import contract

    monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "on")
    monkeypatch.setattr(contract, "kept_paths", lambda root: frozenset({"notes-api/package.json", "notes-api/tsconfig.json"}))
    spec = SPEC.model_copy(update={"file_plan": [
        "notes-api/package.json - scripts", "notes-api/tsconfig.json - compiler", *SPEC.file_plan,
    ]})

    plan = work_orders_from_the_specification(spec, "Notes", ["AC-1"], ["npm test"], str(tmp_path))

    listed = [f for task in plan.delegated_tasks for f in task.files]
    assert "notes-api/package.json" not in listed and "notes-api/tsconfig.json" not in listed
    assert readiness_problems(plan, str(tmp_path), sprint_scope="Build store.ts and app.ts") == []


def test_a_product_already_built_is_changed_by_the_lead_not_written_again(tmp_path):
    """Each planned file is drafted whole: a plan made once the product exists would lose every fix."""
    for entry in SPEC.file_plan[:3]:
        path = tmp_path / entry.split(" ", 1)[0]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("export {}\n")

    assert work_orders_from_the_specification(SPEC, "Notes", ["AC-1"], ["npm test"], str(tmp_path)) is None
    (tmp_path / "notes-api/src/app.ts").unlink()
    (tmp_path / "notes-api/tests/store.test.ts").unlink()
    assert work_orders_from_the_specification(SPEC, "Notes", ["AC-1"], ["npm test"], str(tmp_path)) is not None


def test_the_harness_made_plan_narrates_itself_so_the_sprint_it_opened_is_counted():
    """Fast delivery's own path made no model call, so no event ever carried `stage="technical_lead"` for
    it; the UI's sprint counter (built by counting technical_lead events) silently skipped the sprint
    this opened, and the sprint that followed wore its number - shown live, sprint 1 never had a header,
    and the header that first appeared, over sprint 2's planning, read "Sprint 1"."""
    source = inspect.getsource(workflow)
    node = source[source.index("    def technical_lead_node("):]
    start = node.index("if planned is not None:")
    branch = node[start:node.index("        else:", start)]
    assert "AgentActivityStream(" in branch and '"technical_lead"' in branch and "publish_outcome(" in branch
