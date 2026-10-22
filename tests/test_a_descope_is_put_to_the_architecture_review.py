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

        assert "Brief requirements this specification defers, redefines or never describes" in request
        assert "`edit`" in request
        assert "Users can add, edit, delete tasks" in request

    def test_it_says_what_severity_it_is(self):
        assert "is a major finding" in _request(SPEC)

    def test_nothing_is_added_when_nothing_is_deferred(self):
        request = _request(
            "# Spec\n- Add: the form's submit handler appends a task.\n"
            "- Editing uses an inline input.\n- Delete: a button removes the task.\n"
        )

        assert "defers, redefines or never describes" not in request

    def test_nothing_is_added_without_a_brief(self):
        assert "defers, redefines or never describes" not in _request(SPEC, brief="")


class TestASilentOmission:
    """One run's specification described every flow but editing, and deferred nothing.

    It said "full CRUD operations (create, read, update, delete tasks)" and
    gave create, toggle, delete and filter each a flow. The sprint plan raised
    editing as an open question and answered it: "treat as toggle-only".
    """

    SILENT = """# Technical Specification
This release covers full CRUD operations (create, read, update, delete tasks).
- Create Task Flow: the submit handler calls createTask and re-renders.
- Toggle Completion Flow: a click flips completed and re-renders.
- Delete Task Flow: a click calls deleteTask and re-renders.
<!-- Generated from the architect's structured specification. Editing this file does not change what the pipeline reads. -->
"""

    def test_the_undescribed_action_is_found(self):
        from app.analysis.integration_checks import brief_actions_the_text_never_describes

        assert [a for a, _ in brief_actions_the_text_never_describes(BRIEF, self.SILENT)] == ["edit"]

    def test_the_rendered_footer_does_not_count_as_describing_it(self):
        """"Editing this file does not change..." names `edit` on a line of its own."""
        from app.analysis.integration_checks import brief_actions_the_text_never_describes

        assert brief_actions_the_text_never_describes(BRIEF, self.SILENT)

    def test_the_review_is_told(self):
        request = _request(self.SILENT)

        assert "`edit`" in request
        assert "never in a line of its own that says how it is done" in request

    def test_a_described_flow_is_enough(self):
        from app.analysis.integration_checks import brief_actions_the_text_never_describes

        described = self.SILENT + "- Edit Task Flow: clicking a title opens an input.\n"

        assert brief_actions_the_text_never_describes(BRIEF, described) == []

    def test_a_deferred_action_is_listed_once(self):
        request = _request(SPEC)

        assert request.count("- `edit`.") == 1


class TestACapabilityDeclaredAway:
    """Dropped without a deferral word: declared impossible instead.

    One run's specification: 'There is no separate "edit" mode - the title and
    description are immutable after creation (future work may add it)', for a
    brief requiring "Users can add, edit, delete tasks". It names `edit` on a
    line of its own, so it read as describing it, and no deferral word matched.
    """

    LINE = (
        'State is derived from localStorage. There is no separate "edit" mode - the '
        "title and description are immutable after creation (future work may add it)."
    )

    def test_it_is_found(self):
        assert [a for a, _, _ in brief_actions_the_text_defers(BRIEF, self.LINE)] == ["edit"]

    def test_the_plan_after_a_modal_is_not_what_is_dropped(self):
        """"future work may add it" does not defer `add`."""
        assert "add" not in [a for a, _, _ in brief_actions_the_text_defers(BRIEF, self.LINE)]

    @pytest.mark.parametrize(
        "line",
        [
            "Tasks cannot be edited once created.",
            "Editing is not supported in this release.",
            "Editing is left to future releases.",
        ],
    )
    def test_other_ways_of_saying_it(self, line):
        assert "edit" in [a for a, _, _ in brief_actions_the_text_defers(BRIEF, line)]

    @pytest.mark.parametrize(
        "line",
        [
            "Pure functions: deleteTask returns a new array and never mutates its input.",
            "addTask returns a new array; the input array is left unchanged.",
            "Design tokens live in an immutable configuration layer.",
        ],
    )
    def test_immutability_of_data_is_not_a_descope(self, line):
        assert brief_actions_the_text_defers(BRIEF, line) == []
