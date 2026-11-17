"""Fast delivery's work orders are made from the specification by the harness.

One run's lead was sent back three times for test files its plan gave nobody,
returned the same plan each time and started over: 23 minutes for a plan the
specification already spelled out.
"""

from __future__ import annotations

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


def _the_lead_node_runs(tmp_path, monkeypatch, *, fast: bool):
    """The technical lead node's update, what its stage was asked and what it narrated, in either delivery mode."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from langgraph.checkpoint.memory import MemorySaver

    from app import delivery
    from app.agents.scrum_master import SprintDefinition, SprintPlanOutput
    from app.agents.technical_lead import MilestonePlanOutput

    monkeypatch.setattr(delivery, "fast", lambda environment=None: fast)
    narrated: list[tuple[str, str, str]] = []

    class _Stream:
        def __init__(self, run_id, stage):
            self.run_id, self.stage = run_id, stage

        def publish_outcome(self, summary):
            narrated.append((self.run_id, self.stage, summary))

    sprint = SprintDefinition(goal="Notes", user_value="notes", in_scope=["Build store.ts and app.ts"],
                              out_of_scope=[], acceptance_criteria=["works"], dependencies=[])
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "sprint_plan": SprintPlanOutput(sprints=[sprint], success_measure_coverage=[]),
        "technical_specification": SPEC,
        "current_sprint_index": 0,
    }
    lead_s = MilestonePlanOutput(selected_sprint_goal="Notes", delegated_tasks=[])
    with patch("app.graph.workflow.create_technical_lead_agent", return_value=MagicMock()), \
         patch("app.graph.acceptance_nodes.sprint_already_done", return_value=""), \
         patch("app.server.agent_stream.AgentActivityStream", _Stream), \
         patch("app.graph.workflow._run_gated_agent", return_value={"milestone_plan": lead_s}) as asked:
        graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(tmp_path))
        update = graph.nodes["technical_lead"].bound.invoke(
            state, {"configurable": {"thread_id": "t", "app_run_id": "run-lead"}})
    return update, asked.called, narrated


def test_the_lead_is_asked_only_when_the_harness_has_no_plan(tmp_path, monkeypatch):
    """Fast delivery plans from the specification with no planning call; thorough delivery asks the lead (once
    checked on the source)."""
    update, lead_asked, _ = _the_lead_node_runs(tmp_path, monkeypatch, fast=True)

    assert not lead_asked
    assert {f for task in update["milestone_plan"].delegated_tasks for f in task.files} >= {
        "notes-api/src/store.ts", "notes-api/src/app.ts"}

    _, lead_asked, _ = _the_lead_node_runs(tmp_path, monkeypatch, fast=False)

    assert lead_asked


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


def test_the_harness_made_plan_narrates_itself_so_the_sprint_it_opened_is_counted(tmp_path, monkeypatch):
    """Fast delivery's own path made no model call, so no event ever carried `stage="technical_lead"` for
    it; the UI's sprint counter (built by counting technical_lead events) silently skipped the sprint
    this opened, and the sprint that followed wore its number - shown live, sprint 1 never had a header,
    and the header that first appeared, over sprint 2's planning, read "Sprint 1"."""
    _, _, narrated = _the_lead_node_runs(tmp_path, monkeypatch, fast=True)

    assert [(run_id, stage) for run_id, stage, _ in narrated] == [("run-lead", "technical_lead")]
    assert "work order(s) made from the specification" in narrated[0][2]
