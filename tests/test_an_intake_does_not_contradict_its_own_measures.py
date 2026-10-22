"""An intake whose success measures name a capability its workflows omit is repaired.

The intake's success measures said "Users can successfully add, edit, and
delete tasks through the UI" while its core workflows listed add, toggle, delete
and filter. The architect saw the contradiction and resolved it the wrong way,
in an ADR: "'Edit' in the success measures refers to toggling completion status.
No inline text editing ... is implemented." The reviewer approved it, and the
planner deferred editing from both sprints. The brief had said "Users can add,
edit, delete tasks".

So the contradiction is removed where it is made, before anything is rendered
from the intake. Nothing here reads a programming language.
"""

from __future__ import annotations

from typing import Any

from app.agents.product_manager import ProductManagerOutput, with_the_workflows_its_measures_require
from app.graph.workflow import start_workflow
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    ScriptedAgents,
    _approved_review,
    _document,
    _graph,
    _repository,
    _spec,
    _stack_selector,
    _tools,
    agents,
    responds_with,
)

#: The contradictory intake, as it was written.
WORKFLOWS = [
    "Add new tasks with title and description",
    "Toggle tasks between complete/incomplete states",
    "Delete tasks that are no longer needed",
    "Filter task view by status (all, active, completed)",
]
MEASURES = [
    "Users can successfully add, edit, and delete tasks through the UI",
    "Tasks persist correctly between page refreshes using local storage",
    "Filter functionality accurately shows all, active-only, or completed-only tasks",
    "Application stays within the 500-line code limit",
]


def _intake(**over: Any) -> ProductManagerOutput:
    fields: dict[str, Any] = {
        "product_name": "Todo",
        "core_workflows": WORKFLOWS,
        "success_measures": MEASURES,
    }
    fields.update(over)
    return ProductManagerOutput(**fields)


class TestTheRepair:
    def test_the_dropped_capability_becomes_a_workflow(self) -> None:
        repaired = with_the_workflows_its_measures_require(_intake())

        added = repaired.core_workflows[len(WORKFLOWS):]
        assert len(added) == 1
        assert added[0].startswith(MEASURES[0])
        assert "edit" in added[0]

    def test_the_model_s_workflows_are_kept_and_come_first(self) -> None:
        repaired = with_the_workflows_its_measures_require(_intake())

        assert repaired.core_workflows[: len(WORKFLOWS)] == WORKFLOWS

    def test_measures_the_workflows_already_cover_add_nothing(self) -> None:
        """Filtering active and completed covers "active-only, or completed-only"."""
        repaired = with_the_workflows_its_measures_require(_intake())

        assert not any(MEASURES[2] in w for w in repaired.core_workflows)

    def test_a_consistent_intake_is_returned_unchanged(self) -> None:
        intake = _intake(core_workflows=[*WORKFLOWS, "Edit a task's title and description"])

        assert with_the_workflows_its_measures_require(intake) is intake

    def test_no_measures_changes_nothing(self) -> None:
        intake = _intake(success_measures=[])

        assert with_the_workflows_its_measures_require(intake) is intake

    def test_it_is_idempotent(self) -> None:
        once = with_the_workflows_its_measures_require(_intake())

        assert with_the_workflows_its_measures_require(once).core_workflows == once.core_workflows


class TestItReachesTheArchitect:
    def test_the_architect_is_asked_to_specify_the_repaired_workflows(
        self, agents: ScriptedAgents, tmp_path: Any
    ) -> None:
        agents.script("product_manager", [responds_with(_intake())])
        agents.script("tools_models", [responds_with(_tools())])
        agents.script("stack_selector", [responds_with(_stack_selector())])
        agents.script(
            "principal_architect",
            [responds_with(_spec(scope="Add, edit and delete tasks; local storage; active and completed filters"))],
        )
        agents.script("architecture_review", [responds_with(_approved_review())])

        # Only the architect's request matters here; the run is not scripted
        # past it, so it stops at the next stage.
        try:
            start_workflow(_graph(), _document(), _repository(tmp_path), "run-intake-repair")
        except AssertionError as exc:
            assert "scrum_master" in str(exc)

        request = agents.last_request_text("principal_architect")
        assert "no workflow above covered edit" in request
