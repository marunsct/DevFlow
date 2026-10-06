"""A sprint keeps the criteria its plan names, and a guess reads the words that tell sprints apart.

Measured on one run: the planner left every sprint's `criteria` empty and listed
the ids under `acceptance_criteria` instead - sprint 2 "AC-2, AC-3, AC-4". Read
from `criteria` alone, all nine were assigned by their words, and "Edit an
item's title" went to sprint 1, which adds items with a title and says editing
is out of its scope - over sprint 2, whose goal was editing.
"""

from __future__ import annotations

from app.agents.scrum_master import SprintDefinition, SprintPlanOutput, with_every_criterion_assigned

IDS = ["AC-1", "AC-2", "AC-3", "AC-4", "AC-5"]
TEXTS = {
    "AC-1": "Add new items with title and description",
    "AC-2": "Mark items as complete/incomplete",
    "AC-3": "Edit an item's title",
    "AC-4": "Delete items",
    "AC-5": "Filter items by status (all, active, completed)",
}


def _sprint(goal: str, value: str, scope: list[str], named: list[str], out: list[str] = ()) -> SprintDefinition:
    return SprintDefinition(goal=goal, user_value=value, in_scope=scope,
                            acceptance_criteria=named, out_of_scope=list(out))


def _the_run_s_plan(named: bool) -> SprintPlanOutput:
    return SprintPlanOutput(sprints=[
        _sprint("Deliver a working add-item flow that shows the new item in the list.",
                "Users can create items with a title; the list updates immediately.",
                ["Form with Title input, Description field and Add control", "Render the item list"],
                ["AC-1"] if named else [], out=["Editing, deleting, toggling, filtering"]),
        _sprint("Add edit, delete and toggle completion features.",
                "Users can manage their items.",
                ["Edit control per item", "Delete control per item", "Toggle completion"],
                ["AC-2", "AC-3", "AC-4"] if named else []),
        _sprint("Implement filtering by All/Active/Completed.", "Users can focus on what is left.",
                ["Filter controls", "Filtered rendering"], ["AC-5"] if named else []),
    ])


def test_the_ids_a_sprint_lists_under_its_acceptance_criteria_are_its_own() -> None:
    plan, notes = with_every_criterion_assigned(_the_run_s_plan(named=True), IDS, TEXTS)

    assert [s.criteria for s in plan.sprints] == [["AC-1"], ["AC-2", "AC-3", "AC-4"], ["AC-5"]]
    assert not any("by what each sprint says it builds" in note for note in notes)


def test_a_guess_follows_the_word_only_one_sprint_says() -> None:
    plan, _ = with_every_criterion_assigned(_the_run_s_plan(named=False), IDS, TEXTS)

    assert "AC-3" in plan.sprints[1].criteria
    assert "AC-1" in plan.sprints[0].criteria and "AC-5" in plan.sprints[2].criteria


def test_criteria_named_in_criteria_still_win() -> None:
    plan = _the_run_s_plan(named=True)
    plan.sprints[0].criteria = ["AC-1", "AC-2"]

    assigned, _ = with_every_criterion_assigned(plan, IDS, TEXTS)

    assert assigned.sprints[0].criteria == ["AC-1", "AC-2"]
    assert assigned.sprints[1].criteria == ["AC-3", "AC-4"]
