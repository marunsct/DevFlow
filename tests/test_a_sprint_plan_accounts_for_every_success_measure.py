"""A sprint plan must assign every success measure the product intake states.

The Scrum Master planned from the specification alone and was never shown the
intake's success measures - the one place a requirement is sure to be stated
plainly. Measured across the 33 stored runs whose intake required editing a
task: the sprint plan never mentioned editing in 12 of them. The specification
had dropped it outright in only 3; in the others it mentioned editing once or
twice, far down, and the plan followed the emphasis.

On run-ed19fdbb the intake's success measures read "Users can add, edit, and
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
    _specialist,
    agents,
    responds_with,
)

#: run-ed19fdbb's success measures, verbatim.
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
        """run-ed19fdbb's own plan: no coverage at all."""
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
    agents.script("scrum_master", [responds_with(p) for p in plans])
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    agents.script("specialist_backend", [responds_with(_specialist())])
    agents.script("specialist_testing", [responds_with(_specialist())])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])


def _one_sprint(coverage: list[str]) -> SprintPlanOutput:
    return SprintPlanOutput(
        sprints=[SprintDefinition(goal="Sprint 1: todo", user_value="Users manage tasks")],
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
        _script(agents, _one_sprint([]), _one_sprint([]))

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-twice")

        assert len(agents.requests["scrum_master"]) == 2
        assert state["stage"] == "complete", state.get("error")
        assert not state.get("sprint_plan_gaps")

    def test_the_accepted_plan_is_the_one_recorded(self, agents: ScriptedAgents, tmp_path: Any) -> None:
        _script(agents, _one_sprint(COMPLETE[1:]), _one_sprint(COMPLETE))

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-recorded")

        assert state["sprint_plan"].success_measure_coverage == COMPLETE
