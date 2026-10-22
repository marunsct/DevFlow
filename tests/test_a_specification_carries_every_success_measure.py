"""A specification that never names a capability the success measures require goes back once.

The Senior Architect Reviewer is given the specification and the brief's
constraints - not its requirements - so it cannot see a feature that is not
there. The architect is given the whole intake and still drops one whenever the
intake's core workflows leave out what its success measures keep.

That is both runs of `brief_low` on 2026-09-28. Two runs
each had the success measure "Users can add, edit, and delete tasks" beside core
workflows reading add, toggle, delete and filter; neither specification named
editing (21,474 and 27,575 characters, no mention); both were approved; and the
gap surfaced at the milestone review, a full build cycle later.

The comparison is the one `app.agents.success_measures` makes for the sprint
plan: every item of an "and" list in a measure must be named in the document.
Nothing here reads a programming language.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.agents.product_manager import ProductManagerOutput
from app.agents.success_measures import capabilities_never_named, enumerations, named_in
from app.graph.workflow import (
    MAX_ARCHITECTURE_REVISIONS,
    _a_success_measure_the_specification_drops,
    start_workflow,
)
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    ScriptedAgents,
    _approved_review,
    _document,
    _graph,
    _milestone,
    _milestone_review,
    _repository,
    _security_review,
    _specialist,
    _spec,
    _stack_selector,
    _tools,
    agents,
    responds_with,
)
from app.agents.scrum_master import SprintDefinition, SprintPlanOutput

MEASURE = "Users can add, edit, and delete tasks without errors"


def _state(**extra: Any) -> dict:
    return {"product_intake": SimpleNamespace(success_measures=[MEASURE]), **extra}


class TestTheComparison:
    def test_the_measured_specification(self) -> None:
        text = "addTask(tasks, title) appends a task. deleteTask(tasks, id) removes it. toggleTask flips it."

        assert capabilities_never_named(text, [MEASURE]) == {1: ["edit"]}

    def test_a_specification_that_names_it(self) -> None:
        text = "addTask, editTask and deleteTask are pure functions."

        assert capabilities_never_named(text, [MEASURE]) == {}

    def test_the_lists_it_finds(self) -> None:
        assert enumerations(MEASURE) == [(True, ["add", "edit", "delete"])]
        assert enumerations("stored in localStorage or a JSON file") == [(False, ["localStorage", "JSON"])]

    def test_a_hyphenated_item_is_named_by_its_leading_word(self) -> None:
        """A live false positive: a plan filtering "active" and "completed" was
        handed back for not saying "active-only" and "completed-only"."""
        measure = "Filter functionality accurately shows all, active-only, or completed-only tasks"

        assert capabilities_never_named("Filter by active or completed status", [measure]) == {}

    def test_a_short_leading_word_does_not_stand_in(self) -> None:
        """'real' is not 'real-time'; erring this way only means not flagging."""
        measure = "Updates arrive in real-time and offline"

        assert capabilities_never_named("real data, offline mode", [measure]) == {1: ["real-time"]}

    def test_word_starts_only(self) -> None:
        assert named_in("edit", "updateTask via startEdit()")
        assert not named_in("edit", "credit card")


class TestTheFinding:
    def test_a_spec_without_it_gets_a_major_finding_naming_it(self) -> None:
        finding = _a_success_measure_the_specification_drops(_state(), "addTask and deleteTask")

        assert finding is not None
        assert finding.severity == "major"
        assert "'edit'" in finding.description
        assert MEASURE in finding.description

    def test_a_spec_with_it_gets_nothing(self) -> None:
        assert _a_success_measure_the_specification_drops(_state(), "addTask, editTask, deleteTask") is None

    def test_only_once_per_run(self) -> None:
        state = _state(specification_coverage_checked=True)

        assert _a_success_measure_the_specification_drops(state, "addTask and deleteTask") is None

    def test_never_on_the_revision_that_would_end_the_run(self) -> None:
        """The sprint-plan check and the milestone review are still behind it."""
        state = _state(architecture_revision_count=MAX_ARCHITECTURE_REVISIONS - 1)

        assert _a_success_measure_the_specification_drops(state, "addTask and deleteTask") is None

    def test_no_measures_no_finding(self) -> None:
        state = {"product_intake": SimpleNamespace(success_measures=[])}

        assert _a_success_measure_the_specification_drops(state, "anything") is None


def _script(agents: ScriptedAgents, *specs: Any) -> None:
    agents.script(
        "product_manager",
        [responds_with(ProductManagerOutput(product_name="Todo", success_measures=[MEASURE]))],
    )
    agents.script("tools_models", [responds_with(_tools())])
    agents.script("stack_selector", [responds_with(_stack_selector())])
    agents.script("principal_architect", [responds_with(s) for s in specs])
    agents.script("architecture_review", [responds_with(_approved_review()) for _ in specs])
    agents.script(
        "scrum_master",
        [
            responds_with(
                SprintPlanOutput(
                    sprints=[
                        SprintDefinition(
                            goal="Sprint 1: tasks",
                            user_value="Users manage tasks",
                            in_scope=["Add, edit and delete tasks"],
                        )
                    ],
                    success_measure_coverage=["1: Sprint 1"],
                )
            )
        ],
    )
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    agents.script("specialist_backend", [responds_with(_specialist())])
    agents.script("specialist_testing", [responds_with(_specialist())])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])


class TestTheWorkflow:
    def test_an_approved_spec_that_drops_it_goes_back_to_the_architect(
        self, agents: ScriptedAgents, tmp_path: Any
    ) -> None:
        _script(agents, _spec(scope="Users add and delete tasks"), _spec(scope="Users add, edit and delete tasks"))

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-spec-drops")

        assert len(agents.requests["principal_architect"]) == 2
        revision = agents.last_request_text("principal_architect")
        assert "never mentions a capability" in revision
        assert "'edit'" in revision
        assert state["stage"] == "complete", state.get("error")

    def test_a_spec_that_names_it_goes_straight_through(self, agents: ScriptedAgents, tmp_path: Any) -> None:
        _script(agents, _spec(scope="Users add, edit and delete tasks"))

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-spec-ok")

        assert len(agents.requests["principal_architect"]) == 1
        assert state["stage"] == "complete", state.get("error")

    def test_an_architect_that_drops_it_twice_is_not_looped_on(
        self, agents: ScriptedAgents, tmp_path: Any
    ) -> None:
        _script(agents, _spec(scope="Users add and delete tasks"), _spec(scope="Users add and delete tasks"))

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-spec-twice")

        assert len(agents.requests["principal_architect"]) == 2
        assert state["stage"] == "complete", state.get("error")
