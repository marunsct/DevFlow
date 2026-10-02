"""A bulleted list a model sent as one list entry is read as its entries.

Measured on one run: the intake's first success measure was four bulleted
lines in one string. The sprint plan's coverage checklist numbered them as one
measure, the plan was handed back for it, and the document rendered "- - ...".
"""

from __future__ import annotations

from app.agents.list_items import one_item_each
from app.agents.product_manager import ProductManagerOutput
from app.agents.success_measures import capabilities_never_named

FOUR_IN_ONE = (
    "- Tasks can be added, edited, deleted, and marked complete within the UI.\n"
    "- Data persists after page reload.\n"
    "- Filter buttons correctly display subsets of tasks.\n"
    "- App layout remains usable on mobile and desktop screens."
)


def test_a_bulleted_list_in_one_entry_is_split() -> None:
    assert one_item_each([FOUR_IN_ONE, "Users can add, edit, delete tasks"]) == [
        "Tasks can be added, edited, deleted, and marked complete within the UI.",
        "Data persists after page reload.",
        "Filter buttons correctly display subsets of tasks.",
        "App layout remains usable on mobile and desktop screens.",
        "Users can add, edit, delete tasks",
    ]


def test_a_numbered_list_in_one_entry_is_split() -> None:
    assert one_item_each(["1. Open app\n2. Add task\n3) Delete task"]) == [
        "Open app", "Add task", "Delete task",
    ]


def test_a_marker_on_a_single_entry_is_removed() -> None:
    assert one_item_each(["- Responsive layout", "* Filters"]) == ["Responsive layout", "Filters"]


def test_prose_with_a_line_break_is_left_whole() -> None:
    prose = "Users need a simple way to track tasks.\nThey also want it to persist."

    assert one_item_each([prose]) == [prose]


def test_an_entry_that_only_starts_like_a_list_is_left_whole() -> None:
    mixed = "- Core features\nand whatever else fits"

    assert one_item_each([mixed]) == [mixed]


def test_ordinary_entries_and_other_values_are_untouched() -> None:
    plain = ["Add a task", "3 retries are allowed", "re-open a task - optional"]

    assert one_item_each(plain) == plain
    assert one_item_each("not a list") == "not a list"
    assert one_item_each([1, 2]) == [1, 2]


def test_the_intake_s_fields_are_read_that_way() -> None:
    intake = ProductManagerOutput(product_name="App", success_measures=[FOUR_IN_ONE])

    assert len(intake.success_measures) == 4
    assert intake.success_measures[1] == "Data persists after page reload."


def test_added_is_named_by_add() -> None:
    """A plan saying "add form" and "add/edit/delete" delivers "added"."""
    plan = "Render UI: add form, task list items with edit/delete/complete toggle buttons"

    missing = capabilities_never_named(plan, ["Tasks can be added, edited, and deleted."])

    assert missing == {}
