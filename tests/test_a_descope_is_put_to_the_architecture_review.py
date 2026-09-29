"""A specification that defers a brief requirement is put to the architecture review.

The reviewer was given the brief's constraints and not its acceptance
criteria. One run's specification, for a brief saying "Users can add, edit,
delete tasks", wrote "ADR-03 - 'Edit' means toggle completion only" and
"Inline description editing is deferred"; the review accepted it as a
trade-off. The objection then came from the integration check in every
sprint-one test round, handed to defect-fix stages scoped to a milestone that
never included editing. One renamed a test to contain "edit", and three test
rounds ran.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.architecture_reviewer import build_architecture_review_request
from app.analysis.integration_checks import brief_actions_the_text_defers

BRIEF = Path(__file__).with_name("brief_low.md").read_text(encoding="utf-8")

SPEC = """# Technical Specification
The acceptance criteria reference "edit" - the specification interprets this as
toggling completion status only. Inline description editing is deferred to avoid adding complexity.
Filtering is implemented in sprint 2.
"""


def _request(spec: str, brief: str = BRIEF) -> str:
    return build_architecture_review_request(spec, "/", brief)["messages"][0]["content"]


class TestWhatIsFound:
    def test_the_deferred_action_is_found(self):
        assert [action for action, _, _ in brief_actions_the_text_defers(BRIEF, SPEC)] == ["edit"]

    def test_it_quotes_both_lines(self):
        (_, brief_line, spec_line), = brief_actions_the_text_defers(BRIEF, SPEC)

        assert brief_line == "- Users can add, edit, delete tasks"
        assert "editing is deferred" in spec_line

    def test_an_action_in_the_reason_is_not_deferred(self):
        """`adding` in "to avoid adding complexity" is why, not what."""
        found = brief_actions_the_text_defers(BRIEF, SPEC)

        assert "add" not in [action for action, _, _ in found]

    @pytest.mark.parametrize(
        "line",
        [
            "Defer editing to v2.",
            "Title editing is deferred; description editing is deferred entirely.",
            "Out of scope: editing tasks.",
        ],
    )
    def test_other_spellings_of_a_deferral(self, line):
        assert "edit" in [action for action, _, _ in brief_actions_the_text_defers(BRIEF, line)]

    @pytest.mark.parametrize(
        "line",
        [
            "Editing is implemented with a double-click handler; sync is deferred because it needs a server.",
            "Authentication is deferred.",
            "Editing a task opens an inline input.",
        ],
    )
    def test_a_specification_that_builds_it_is_silent(self, line):
        assert brief_actions_the_text_defers(BRIEF, line) == []

    def test_a_brief_that_does_not_ask_is_silent(self):
        assert brief_actions_the_text_defers("# A calculator\nIt adds numbers.\n", SPEC) == []


class TestTheReviewIsTold:
    def test_the_request_names_the_descope(self):
        request = _request(SPEC)

        assert "Brief requirements this specification defers or redefines" in request
        assert "`edit`" in request
        assert "Users can add, edit, delete tasks" in request

    def test_it_says_what_severity_it_is(self):
        assert "is a major finding" in _request(SPEC)

    def test_nothing_is_added_when_nothing_is_deferred(self):
        request = _request("# Spec\nEditing uses an inline input.\n")

        assert "defers or redefines" not in request

    def test_nothing_is_added_without_a_brief(self):
        assert "defers or redefines" not in _request(SPEC, brief="")
