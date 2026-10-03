"""A sprint plan must assign every success measure the product intake states.

The Scrum Master planned from the specification alone and was never shown the
intake's success measures - the one place a requirement is sure to be stated
plainly. Measured across the 33 stored runs whose intake required editing a
task: the sprint plan never mentioned editing in 12 of them. The specification
had dropped it outright in only 3; in the others it mentioned editing once or
twice, far down, and the plan followed the emphasis.

On one run the intake's success measures read "Users can add, edit, and
delete tasks through the UI", its core workflows listed create, toggle, delete,
filter and persist, and the specification never mentioned editing a task at
all. The milestone review caught it - "No `edit` functionality exists in app.js
or any other source file" - after the whole first milestone had been built,
tested and security-reviewed, and at the cost of one of the three revisions the
run is allowed. Revision exhaustion is how the three low-brief runs before it
ended.

Nothing here reads a programming language: it compares numbered requirements
against numbered sprints.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agents.product_manager import ProductManagerOutput
from app.agents.scrum_master import (
    SprintDefinition,
    SprintPlanOutput,
    build_sprint_planning_request,
    capabilities_the_plan_never_names,
    unaccounted_success_measures,
)
from app.graph.workflow import start_workflow
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    ScriptedAgents,
    _approved_review,
    _document,
    _graph,
    _milestone,
    _milestone_review,
    _repository,
    _script_through_architecture,
    _security_review,
    _spec,
    _specialist,
    agents,
    responds_with,
)

#: One run's success measures, verbatim.
MEASURES = [
    "Users can add, edit, and delete tasks through the UI",
    "Tasks persist between page refreshes (verified via local storage or JSON file)",
    "Filter controls correctly show all / active / completed subsets",
    "UI is responsive on both mobile and desktop viewports",
    "Total codebase stays within 500 lines",
]


def _plan(coverage: list[str], sprints: int = 2) -> SprintPlanOutput:
    return SprintPlanOutput(
        sprints=[SprintDefinition(goal=f"Sprint {k}", user_value="v") for k in range(1, sprints + 1)],
        success_measure_coverage=coverage,
    )


class TestTheAccounting:
    def test_a_plan_that_never_considered_them_misses_all(self) -> None:
        """One run's own plan: no coverage at all."""
        assert unaccounted_success_measures(_plan([]), MEASURES) == [1, 2, 3, 4, 5]

    def test_a_complete_plan_misses_none(self) -> None:
        coverage = ["1: Sprint 1", "2: Sprint 1", "3: Sprint 2", "4: Sprint 2", "5: every sprint"]

        assert unaccounted_success_measures(_plan(coverage), MEASURES) == []

    def test_the_one_it_left_out_is_named(self) -> None:
        coverage = ["2: Sprint 1", "3: Sprint 2", "4: Sprint 2", "5: all sprints"]

        assert unaccounted_success_measures(_plan(coverage), MEASURES) == [1]

    def test_a_sprint_that_does_not_exist_is_not_an_assignment(self) -> None:
        coverage = ["1: Sprint 7", "2: Sprint 1", "3: Sprint 2", "4: Sprint 2", "5: every sprint"]

        assert unaccounted_success_measures(_plan(coverage, sprints=2), MEASURES) == [1]

    def test_a_line_with_no_sprint_in_it_is_not_an_assignment(self) -> None:
        """'1: later' is exactly the dropped requirement, written down."""
        coverage = ["1: later", "2: Sprint 1", "3: Sprint 2", "4: Sprint 2", "5: every sprint"]

        assert unaccounted_success_measures(_plan(coverage), MEASURES) == [1]

    @pytest.mark.parametrize("line", ["1: Sprint 1", "1. sprint 1", "1) Sprint #1 - editing", "1 - Sprints 1 and 2"])
    def test_the_ways_a_model_writes_the_line(self, line: str) -> None:
        assert 1 not in unaccounted_success_measures(_plan([line]), MEASURES)

    def test_no_measures_asks_for_nothing(self) -> None:
        """Every existing fixture and any intake without measures is unaffected."""
        assert unaccounted_success_measures(_plan([]), []) == []


#: One run's Sprint 1, which its coverage line said delivered measure 1.
A_SPRINT_THAT_CLAIMS_EDIT = SprintDefinition(
    goal=(
        "Users can add tasks with title and description, toggle completion state, "
        "delete tasks, and have all changes persist across page refreshes."
    ),
    user_value="Users keep a task list",
    in_scope=[
        "app.js: all four exported pure functions (addTask, toggleTask, deleteTask, filterTasks)",
        "style.css: mobile-first responsive layout; desktop refinements",
        "localStorage adapter",
    ],
)


class TestWhatTheSprintsDeliver:
    """Assignment was not enough: the item a measure lists must be delivered."""

    def test_the_measured_case(self) -> None:
        plan = SprintPlanOutput(sprints=[A_SPRINT_THAT_CLAIMS_EDIT], success_measure_coverage=COMPLETE)

        assert unaccounted_success_measures(plan, MEASURES) == []
        assert capabilities_the_plan_never_names(plan, MEASURES) == {1: ["edit"]}

    def test_a_deferral_does_not_deliver_it(self) -> None:
        sprint = A_SPRINT_THAT_CLAIMS_EDIT.model_copy(update={"out_of_scope": ["Editing tasks (later)"]})

        assert capabilities_the_plan_never_names(SprintPlanOutput(sprints=[sprint]), MEASURES) == {1: ["edit"]}

    def test_an_open_question_does_not_deliver_it(self) -> None:
        plan = SprintPlanOutput(sprints=[A_SPRINT_THAT_CLAIMS_EDIT], open_questions=["Should tasks be editable?"])

        assert 1 in capabilities_the_plan_never_names(plan, MEASURES)

    def test_a_camel_case_function_names_it(self) -> None:
        sprint = A_SPRINT_THAT_CLAIMS_EDIT.model_copy(
            update={"in_scope": [*A_SPRINT_THAT_CLAIMS_EDIT.in_scope, "editTask(id, fields) pure function"]}
        )

        assert 1 not in capabilities_the_plan_never_names(SprintPlanOutput(sprints=[sprint]), MEASURES)

    def test_a_word_that_merely_contains_it_does_not(self) -> None:
        """'credit' is not 'edit'."""
        sprint = A_SPRINT_THAT_CLAIMS_EDIT.model_copy(
            update={"in_scope": [*A_SPRINT_THAT_CLAIMS_EDIT.in_scope, "Show a credit line in the footer"]}
        )

        assert capabilities_the_plan_never_names(SprintPlanOutput(sprints=[sprint]), MEASURES) == {1: ["edit"]}

    def test_an_or_list_needs_only_one(self) -> None:
        """'localStorage or JSON file' is satisfied by localStorage alone."""
        plan = SprintPlanOutput(sprints=[A_SPRINT_THAT_CLAIMS_EDIT])

        assert 2 not in capabilities_the_plan_never_names(plan, MEASURES)

    def test_an_and_list_needs_every_item(self) -> None:
        sprint = SprintDefinition(goal="g", user_value="v", in_scope=["Works on mobile"])
        measures = ["UI is responsive on both mobile and desktop viewports"]

        assert capabilities_the_plan_never_names(SprintPlanOutput(sprints=[sprint]), measures) == {1: ["desktop"]}

    def test_words_outside_a_list_are_never_required(self) -> None:
        """'correctly', 'controls', 'show' - handing back for those is phrasing, not scope."""
        sprint = SprintDefinition(goal="g", user_value="v", in_scope=["Filter dropdown for active and completed"])
        measures = ["Filter controls correctly show only active or completed tasks"]

        assert capabilities_the_plan_never_names(SprintPlanOutput(sprints=[sprint]), measures) == {}

    def test_a_measure_without_a_list_is_not_checked(self) -> None:
        plan = SprintPlanOutput(sprints=[SprintDefinition(goal="g", user_value="v")])

        assert capabilities_the_plan_never_names(plan, ["Total codebase stays within 500 lines"]) == {}

    def test_the_whole_plan_delivering_everything_passes(self) -> None:
        assert capabilities_the_plan_never_names(_one_sprint(COMPLETE), MEASURES) == {}


class TestTheRequest:
    def test_the_planner_is_shown_the_measures(self) -> None:
        body = build_sprint_planning_request("spec", "/w", success_measures=MEASURES)["messages"][0]["content"]

        assert "1. Users can add, edit, and delete tasks through the UI" in body
        assert "success_measure_coverage" in body

    def test_a_re_plan_names_what_the_last_one_missed(self) -> None:
        body = build_sprint_planning_request("spec", "/w", success_measures=MEASURES, gaps=[1])["messages"][0][
            "content"
        ]

        assert "LEFT THESE UNASSIGNED" in body
        assert "1. Users can add, edit, and delete tasks through the UI" in body.split("LEFT THESE UNASSIGNED")[1]

    def test_without_measures_the_request_is_as_it_was(self) -> None:
        body = build_sprint_planning_request("spec", "/w")["messages"][0]["content"]

        assert "Success measures" not in body
        assert "CRITICAL INSTRUCTION" in body


def _script(agents: ScriptedAgents, *plans: SprintPlanOutput) -> None:
    _script_through_architecture(agents, _approved_review())
    agents.script(
        "product_manager",
        [responds_with(ProductManagerOutput(product_name="Todo", success_measures=MEASURES))],
    )
    # A specification that names every listed capability, so the architecture
    # review's own coverage check passes and these tests reach the planner.
    agents.script(
        "principal_architect",
        [responds_with(_spec(scope="Add, edit and delete tasks; local storage; mobile and desktop layouts"))],
    )
    agents.script("scrum_master", [responds_with(p) for p in plans])
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    agents.script("specialist_backend", [responds_with(_specialist())])
    agents.script("specialist_testing", [responds_with(_specialist())])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])


#: A sprint that really delivers every measure above.
DELIVERS_ALL = [
    "Add, edit and delete tasks from the list",
    "Persist tasks to local storage across refreshes",
    "Filter by all, active or completed",
    "Responsive layout on mobile and desktop",
]


def _one_sprint(coverage: list[str], scope: list[str] | None = None) -> SprintPlanOutput:
    return SprintPlanOutput(
        sprints=[
            SprintDefinition(
                goal="Sprint 1: todo",
                user_value="Users manage tasks",
                in_scope=DELIVERS_ALL if scope is None else scope,
            )
        ],
        success_measure_coverage=coverage,
    )


COMPLETE = ["1: Sprint 1", "2: Sprint 1", "3: Sprint 1", "4: Sprint 1", "5: every sprint"]


class TestTheWorkflow:
    def test_a_plan_that_drops_a_measure_is_asked_for_again_once(
        self, agents: ScriptedAgents, tmp_path: Any
    ) -> None:
        _script(agents, _one_sprint(COMPLETE[1:]), _one_sprint(COMPLETE))

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-replan")

        assert len(agents.requests["scrum_master"]) == 2
        second = agents.last_request_text("scrum_master")
        assert "LEFT THESE UNASSIGNED" in second
        assert "Users can add, edit, and delete tasks" in second.split("LEFT THESE UNASSIGNED")[1]
        assert state["stage"] == "complete", state.get("error")

    def test_a_complete_plan_is_not_asked_for_again(self, agents: ScriptedAgents, tmp_path: Any) -> None:
        _script(agents, _one_sprint(COMPLETE))

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-complete")

        assert len(agents.requests["scrum_master"]) == 1
        assert state["stage"] == "complete", state.get("error")

    def test_a_second_omission_is_not_looped_on(self, agents: ScriptedAgents, tmp_path: Any) -> None:
        """The milestone review is still behind it; planning forever is not."""
        _script(agents, _one_sprint(COMPLETE[1:]), _one_sprint(COMPLETE[1:]))

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-twice")

        assert len(agents.requests["scrum_master"]) == 2
        assert state["stage"] == "complete", state.get("error")
        assert not state.get("sprint_plan_gaps")

    def test_a_plan_that_twice_assigns_nothing_is_not_built_from(
        self, agents: ScriptedAgents, tmp_path: Any
    ) -> None:
        """One measure left out is the milestone review's to judge. A plan that
        assigns none has no review that will look at the whole brief with a
        sprint still to come: one run continued on such a plan, built its one
        foundation sprint, and completed with a product that could only add a
        task."""
        _script(agents, _one_sprint([]), _one_sprint([]))

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-nothing")

        assert len(agents.requests["scrum_master"]) == 2
        assert state["stage"] == "failed"
        assert "assigns none of the" in state["error"]

    def test_a_plan_that_assigns_nothing_is_completed_when_there_are_criteria(
        self, agents: ScriptedAgents, tmp_path: Any, monkeypatch: Any
    ) -> None:
        """With acceptance criteria the harness gives every one to a sprint
        itself, and a sprint is done only when its criteria pass - so the
        product that stop protected against can no longer complete, and
        stopping threw away a plan the harness was about to complete."""
        from app.acceptance import suite
        from app.acceptance.criteria import Criterion

        criteria = [Criterion(id="AC-1", text="Users can add, edit, and delete tasks", source="brief")]
        monkeypatch.setattr(suite, "criteria", lambda root: list(criteria))
        monkeypatch.setattr(suite, "deferred", lambda root: {})
        _script(agents, _one_sprint([]), _one_sprint([]))

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-nothing-but-criteria")

        assert len(agents.requests["scrum_master"]) == 2
        assert "assigns none of the" not in str(state.get("error") or "")
        assert state["sprint_plan"].sprints[0].criteria == ["AC-1"]

    def test_a_plan_that_claims_a_measure_it_only_half_delivers_is_asked_again(
        self, agents: ScriptedAgents, tmp_path: Any
    ) -> None:
        """One run: every measure assigned, and editing nowhere in the plan."""
        half = [s.replace("Add, edit and delete", "Add and delete") for s in DELIVERS_ALL]
        _script(agents, _one_sprint(COMPLETE, scope=half), _one_sprint(COMPLETE))

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-half")

        assert len(agents.requests["scrum_master"]) == 2
        second = agents.last_request_text("scrum_master").split("LEFT THESE UNASSIGNED")[1]
        assert "no sprint delivers: edit" in second
        assert state["stage"] == "complete", state.get("error")

    def test_the_accepted_plan_is_the_one_recorded(self, agents: ScriptedAgents, tmp_path: Any) -> None:
        _script(agents, _one_sprint(COMPLETE[1:]), _one_sprint(COMPLETE))

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-recorded")

        assert state["sprint_plan"].success_measure_coverage == COMPLETE
