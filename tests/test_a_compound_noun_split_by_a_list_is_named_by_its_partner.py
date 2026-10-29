"""An item of a measure's list that is half of a compound noun counts as named when its partner is.

Measured on three runs: "Every HTTP operation returns the correct status code and response shape" was read as the list
"code", "response", and the plan was handed back once more though it delivered every status and the JSON shape.
"""
from __future__ import annotations

from app.agents.success_measures import capabilities_never_named

MEASURE = "Every HTTP operation returns the correct status code and response shape per the interface spec"


def test_the_partners_name_the_compound_items():
    plan = "Sprint 1: every route answers with the status the contract gives and the JSON note shape."
    assert capabilities_never_named(plan, [MEASURE]) == {}


def test_a_plan_naming_neither_half_is_still_handed_back():
    assert capabilities_never_named("Sprint 1: store notes in a file.", [MEASURE]) == {1: ["code", "response"]}


def test_a_real_list_is_still_checked_item_by_item():
    found = capabilities_never_named("Sprint 1: users can add and delete notes.", ["Users can add, edit, and delete notes"])
    assert found == {1: ["edit"]}
