"""A sprint plan that delivers a success measure is not sent back over how it says so.

One run's plan was handed back for never delivering three things it delivered:
"dependencies" (it said "dependency-free"), "newly" (an adverb, read as an item
of "empty list, all-completed list, and newly added tasks"), and "mobile" (it
built a responsive layout for "the layout adapts to mobile and desktop").
"""

from __future__ import annotations

import pytest

from app.agents.success_measures import capabilities_never_named


def test_a_plural_in_ies_is_named_by_its_singular() -> None:
    assert capabilities_never_named(
        "A dependency-free single page.", ["Zero external dependencies and a single page"]
    ) == {}


def test_an_adverb_is_not_an_item_of_a_list() -> None:
    assert capabilities_never_named(
        "Filters hold for an empty list and for tasks added while a filter is active.",
        ["Filter behaviour is correct for: empty list, all-completed list, and newly added tasks"],
    ) == {}


def test_places_after_a_verb_of_fitting_are_delivered_by_the_thing_that_fits() -> None:
    assert capabilities_never_named(
        "Sprint 1 builds a responsive layout checked at 375px and 1280px.",
        ["the layout adapts to mobile and desktop"],
    ) == {}


@pytest.mark.parametrize("measure", [
    "The app allows users to add, edit and delete tasks",
    "Users need to add, edit and delete tasks",
    "It lets a person add, edit and delete notes",
])
def test_capabilities_handed_to_someone_are_still_each_required(measure) -> None:
    assert capabilities_never_named("Sprint 1 allows adding and deleting; it lets people add.", [measure]) == {1: ["edit"]}


def test_a_verb_of_fitting_whose_subject_is_never_built_still_counts_its_places() -> None:
    assert capabilities_never_named("Sprint 1: a page.", ["the layout adapts to mobile and desktop"]) == {
        1: ["mobile", "desktop"]
    }
