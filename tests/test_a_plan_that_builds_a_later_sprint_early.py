"""A sprint plan put a later sprint's work in an earlier sprint's scope.

One run's plan assigned editing, deleting and filtering to sprint 2's criteria
and listed them in sprint 2's scope - and in sprint 1's too, as "inline edit
flow with Edit/Save buttons per task, Delete button per task, filter button
handlers". The lead wrote sprint 1's work orders from that scope and the
builders built every sprint's features in the first, though each was now told
which locked tests were a later sprint's. The planner is asked once to move the
work, and the lead is told what later sprints deliver.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

from app.agents.scrum_master import (
    SprintDefinition,
    SprintPlanOutput,
    build_sprint_planning_request,
    scope_a_later_sprint_delivers,
)
from app.analysis.integration_checks import work_a_later_sprint_delivers
from app.graph.workflow import start_workflow
from test_a_sprint_plan_accounts_for_every_success_measure import DELIVERS_ALL, _script
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    ScriptedAgents,
    _document,
    _graph,
    _milestone,
    _milestone_review,
    _repository,
    _security_review,
    _specialist,
    agents,
    responds_with,
)

#: The run's sprint 1 scope item, as the plan wrote it.
THE_RUNS_ITEM = (
    "Implement DOM wiring in init(): form submit handler that creates tasks, checkbox "
    "click handler that toggles completion, render() that populates the task list from "
    "localStorage, inline edit flow with Edit/Save buttons per task, Delete button per "
    "task, filter button handlers, localStorage persistence on every mutation"
)

SPRINT_ONE = "Users can add items and mark them complete\nAdd new items with a title\nMark items as complete or incomplete"
SPRINT_TWO = "Users can edit, delete and filter items\nEdit an item's title\nDelete items\nFilter items by status"

TEXTS = {
    "AC-1": "Add new items with a title",
    "AC-2": "Mark items as complete or incomplete",
    "AC-3": "Edit an item's title",
    "AC-4": "Delete items",
    "AC-5": "Filter items by status",
}


def _plan(first_scope: list[str]) -> Any:
    return SimpleNamespace(sprints=[
        SimpleNamespace(goal="Users can add items and mark them complete", criteria=["AC-1", "AC-2"], in_scope=first_scope),
        SimpleNamespace(goal="Users can edit, delete and filter items", criteria=["AC-3", "AC-4", "AC-5"],
                        in_scope=["Inline editing", "A delete control on each item", "Filter controls"]),
    ])


class TestTheActionsAnItemBuildsAhead:
    def test_the_runs_item(self):
        assert work_a_later_sprint_delivers(THE_RUNS_ITEM, SPRINT_ONE, SPRINT_TWO) == ["edit", "delete", "filter"]

    def test_an_action_this_sprint_names_is_its_own(self):
        """`complete` and `add`/`create` are sprint 1's, whatever word the item uses."""
        found = work_a_later_sprint_delivers(THE_RUNS_ITEM, SPRINT_ONE, SPRINT_TWO + "\nMark all complete")

        assert "complete" not in found
        assert "create" not in found

    def test_an_item_of_this_sprints_work_builds_nothing_ahead(self):
        assert work_a_later_sprint_delivers("The form that adds an item", SPRINT_ONE, SPRINT_TWO) == []

    def test_nothing_is_ahead_of_the_last_sprint(self):
        assert work_a_later_sprint_delivers(THE_RUNS_ITEM, SPRINT_TWO, "") == []

    def test_a_word_that_only_contains_an_action_is_not_one(self):
        assert work_a_later_sprint_delivers("Credit the source in the footer", SPRINT_ONE, SPRINT_TWO) == []


class TestThePlanCheck:
    def test_the_runs_plan_is_reported(self):
        notes = scope_a_later_sprint_delivers(_plan([THE_RUNS_ITEM]), TEXTS)

        assert len(notes) == 1
        assert notes[0].startswith("Sprint 1's scope builds edit, delete, filter")
        assert "(AC-3, AC-4, AC-5)" in notes[0]

    def test_a_plan_whose_scopes_match_its_criteria_passes(self):
        assert scope_a_later_sprint_delivers(_plan(["The form that adds an item", "A control that marks it complete"]), TEXTS) == []

    def test_the_last_sprints_scope_is_never_reported(self):
        plan = _plan(["The form that adds an item"])

        assert all("Sprint 2" not in note for note in scope_a_later_sprint_delivers(plan, TEXTS))


class TestThePlanningRequest:
    def test_a_re_plan_names_what_was_built_ahead(self, tmp_path):
        notes = scope_a_later_sprint_delivers(_plan([THE_RUNS_ITEM]), TEXTS)

        body = build_sprint_planning_request("spec", str(tmp_path), built_ahead=notes)["messages"][0]["content"]

        assert "YOUR LAST PLAN BUILT THESE BEFORE THE SPRINT THAT NEEDS THEM" in body
        assert "Sprint 1's scope builds edit, delete, filter" in body

    def test_the_standing_rule_is_given_with_the_criteria(self, tmp_path):
        body = build_sprint_planning_request("spec", str(tmp_path), acceptance_criteria="AC-1: x")["messages"][0]["content"]

        assert "not built ahead as functions, wiring or placeholders" in body

    def test_the_new_words_name_no_product(self, tmp_path):
        from app.agents.scrum_master import _built_ahead, _the_acceptance_criteria

        text = (_built_ahead(["n"]) + _the_acceptance_criteria("AC-1: x")).lower()

        for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
            assert not re.search(rf"\b{re.escape(word)}\b", text), word


def _two_sprints(first_scope: list[str]) -> SprintPlanOutput:
    return SprintPlanOutput(
        sprints=[
            SprintDefinition(goal="Sprint 1: adding", user_value="Users add", in_scope=first_scope, criteria=["AC-1"]),
            SprintDefinition(goal="Sprint 2: the rest", user_value="Users manage", in_scope=DELIVERS_ALL, criteria=["AC-2"]),
        ],
        success_measure_coverage=["1: Sprint 1 and Sprint 2", "2: Sprint 2", "3: Sprint 2", "4: Sprint 2", "5: every sprint"],
    )


def _two_sprints_built(agents: ScriptedAgents) -> None:
    """Every role that runs once a sprint answers for both."""
    agents.script("technical_lead", [responds_with(_milestone("backend")) for _ in range(2)])
    agents.script("specialist_backend", [responds_with(_specialist()) for _ in range(2)])
    agents.script("specialist_testing", [responds_with(_specialist()) for _ in range(2)])
    agents.script("milestone_reviewer", [responds_with(_milestone_review()) for _ in range(2)])
    agents.script("security_reviewer", [responds_with(_security_review()) for _ in range(2)])


def _criteria(monkeypatch: Any) -> None:
    from app.acceptance import suite
    from app.acceptance.criteria import Criterion

    criteria = [
        Criterion(id="AC-1", text="Users can add notes", source="brief"),
        Criterion(id="AC-2", text="Users can delete notes", source="brief"),
    ]
    monkeypatch.setattr(suite, "criteria", lambda root: list(criteria))
    monkeypatch.setattr(suite, "deferred", lambda root: {})


class TestTheWorkflow:
    def test_a_plan_that_builds_ahead_is_asked_for_again_once(
        self, agents: ScriptedAgents, tmp_path: Any, monkeypatch: Any
    ) -> None:
        _criteria(monkeypatch)
        _script(
            agents,
            _two_sprints(["The form that adds a note", "A delete control on each note"]),
            _two_sprints(["The form that adds a note"]),
        )
        _two_sprints_built(agents)

        start_workflow(_graph(), _document(), _repository(tmp_path), "run-ahead")

        assert len(agents.requests["scrum_master"]) == 2
        second = agents.last_request_text("scrum_master")
        assert "Sprint 1's scope builds delete" in second.split("BUILT THESE BEFORE")[1]

    def test_a_plan_that_builds_nothing_ahead_is_not_asked_again(
        self, agents: ScriptedAgents, tmp_path: Any, monkeypatch: Any
    ) -> None:
        _criteria(monkeypatch)
        _script(agents, _two_sprints(["The form that adds a note"]))
        _two_sprints_built(agents)

        start_workflow(_graph(), _document(), _repository(tmp_path), "run-not-ahead")

        assert len(agents.requests["scrum_master"]) == 1

    def test_the_lead_is_told_what_later_sprints_deliver(
        self, agents: ScriptedAgents, tmp_path: Any, monkeypatch: Any
    ) -> None:
        """Even where the sprint's scope still lists that work."""
        _criteria(monkeypatch)
        _script(agents, _two_sprints(["The form that adds a note"]))
        _two_sprints_built(agents)

        start_workflow(_graph(), _document(), _repository(tmp_path), "run-lead-told")

        first, second = (
            "\n".join(str(m.get("content")) for m in request["messages"])
            for request in agents.requests["technical_lead"][:2]
        )
        assert "--- What later sprints build - not this sprint's work ---" in first
        assert "- AC-2: Users can delete notes" in first
        assert "No work order builds what only those criteria need" in first
        assert "What later sprints build" not in second

    def test_a_second_plan_that_still_builds_ahead_is_not_looped_on(
        self, agents: ScriptedAgents, tmp_path: Any, monkeypatch: Any
    ) -> None:
        _criteria(monkeypatch)
        ahead = ["The form that adds a note", "A delete control on each note"]
        _script(agents, _two_sprints(ahead), _two_sprints(ahead))
        _two_sprints_built(agents)

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-still-ahead")

        assert len(agents.requests["scrum_master"]) == 2
        assert not state.get("sprint_plan_built_ahead")
