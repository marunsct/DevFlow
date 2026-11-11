"""The sections one review finding names are rewritten by one call, so a contradiction between them can be settled.

Measured on one run: a finding said `file_plan` declares `create_app(storage)` while `function_contracts` declares
`create_app()`; the revision rewrote the two in different parallel calls, each blind to the other's new text, and the
second review raised the same contradiction word for word, then the run escalated.
"""
from __future__ import annotations

from app.graph.specification_parts import SECTIONS_PER_REVISION, grouped_by_finding

CHOSEN = ["api_and_event_contracts", "acceptance_criteria", "configuration", "deployment", "error_catalogue",
          "file_plan", "function_contracts", "interface_contract", "test_cases"]
CHANGES = (
    "- [blocking] Contradictory signatures for `create_app`: `file_plan` declares `create_app(storage)` while "
    "`function_contracts` declares `create_app()`.\n"
    "- [major] The deployment section omits the worker count.\n"
)


def test_two_sections_one_finding_names_share_a_call():
    groups = grouped_by_finding(CHOSEN, CHANGES)
    together = [group for group in groups if "file_plan" in group]
    assert together and "function_contracts" in together[0]
    assert sorted(name for group in groups for name in group) == sorted(CHOSEN)  # every section, once
    assert all(len(group) <= SECTIONS_PER_REVISION for group in groups)


def test_with_nothing_tying_them_the_groups_are_as_before():
    groups = grouped_by_finding(CHOSEN, "- [major] Something general.\n")
    assert groups == [tuple(CHOSEN[n:n + SECTIONS_PER_REVISION]) for n in range(0, len(CHOSEN), SECTIONS_PER_REVISION)]


def test_sections_named_in_words_are_tied_too_and_a_large_tie_stays_whole():
    changes = ("- [major] The file plan, the function contracts, the configuration and the test cases disagree on "
               "the storage path.\n")
    groups = grouped_by_finding(CHOSEN, changes)
    tied = [group for group in groups if "file_plan" in group][0]
    assert {"file_plan", "function_contracts", "configuration", "test_cases"} <= set(tied)
