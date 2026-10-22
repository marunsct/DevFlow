"""A feature the brief lists and the specification defers is put to the architecture review.

Measured on two gate runs of one brief whose features include "Due dates and
reminders": both intakes put "Reminder system" under "Deferred scope", the
specification deferred testing it, no criterion named reminders, and both
products shipped without them. The check for deferred brief requirements read
only user actions, and "reminders" names none.
"""

from __future__ import annotations

from app.analysis.integration_checks import brief_features_the_text_defers

BRIEF = """# Product Brief
## Requirements
- Create, read, update, delete tasks
- Due dates and reminders
- Task categories and tags
## Technical Constraints
- Backend: Python/FastAPI or Node.js/Express
"""


def test_a_feature_under_a_deferring_heading_is_found():
    intake = "## MVP Candidates\n- Due dates\n## Deferred scope\n- Reminder system - mechanism not specified\n"

    assert brief_features_the_text_defers(BRIEF, intake) == [
        ("reminders", "- Due dates and reminders", "- Reminder system - mechanism not specified"),
    ]


def test_a_feature_a_line_defers_is_found():
    spec = "- AC-5: the due date is shown on the card. (Note: reminder testing is deferred per the intake.)\n"
    assert [found[0] for found in brief_features_the_text_defers(BRIEF, spec)] == ["reminders"]


def test_a_feature_built_or_merely_named_is_not():
    spec = "## Features\n- Reminders are sent in-app an hour before the due date.\n- Tags filter the list.\n"
    assert brief_features_the_text_defers(BRIEF, spec) == []


def test_a_choice_and_the_actions_are_left_to_their_own_checks():
    spec = "## Out of scope\n- Express\n- Deleting tasks in bulk\n"
    assert brief_features_the_text_defers(BRIEF, spec) == []


def test_the_review_is_told():
    from app.agents.architecture_reviewer import _what_the_brief_requires_that_this_defers

    section = _what_the_brief_requires_that_this_defers(BRIEF, "## Deferred scope\n- Reminder system\n")
    assert "`reminders`. The brief: \"- Due dates and reminders\"" in section


def test_a_specification_as_json_is_read_line_by_line_and_the_deferring_sentence_quoted():
    # Handed to the review as JSON while written, one "line" held a whole section,
    # and the check quoted the first 200 characters of the scope as its evidence.
    spec = ('{"product_scope": "**IN SCOPE (MVP):**\\n- User registration with email and password.\\n'
            '- Task CRUD with due dates.\\n**DEFERRED:** Users want reminders. Reminders are deferred to a later release."}')

    (found,) = brief_features_the_text_defers(BRIEF, spec)

    assert found[0] == "reminders" and "reminders" in found[2].lower()
    assert "registration" not in found[2] and len(found[2]) < 60


def test_a_deferred_action_in_a_json_specification_is_quoted_by_its_sentence():
    from app.analysis.integration_checks import brief_actions_the_text_defers

    spec = ('{"product_scope": "**IN SCOPE (MVP):**\\n- Task creation and listing.\\n'
            '- Bulk delete is deferred to a later release. Single deletes ship now."}')

    (found,) = brief_actions_the_text_defers(BRIEF, spec)

    assert found[0] == "delete" and found[2] == "- Bulk delete is deferred to a later release."


def _state(**extra):
    from types import SimpleNamespace

    return {"document": SimpleNamespace(text=BRIEF), "architecture_revision_count": 0, **extra}


def test_the_workflow_raises_it_as_a_major_finding_when_the_review_does_not():
    # Measured on one gate run: the review was told and its eight findings never named it.
    from app.graph.workflow import _a_brief_feature_the_specification_defers

    finding = _a_brief_feature_the_specification_defers(_state(), "## Deferred scope\n- Reminder system\n")

    assert finding.severity == "major" and "`reminders`" in finding.description
    assert "acceptance criterion" in finding.required_remediation


def test_once_per_run_and_never_on_the_last_revision():
    from app.graph.workflow import MAX_ARCHITECTURE_REVISIONS, _a_brief_feature_the_specification_defers

    spec = "## Deferred scope\n- Reminder system\n"
    assert _a_brief_feature_the_specification_defers(_state(specification_deferrals_checked=True), spec) is None
    last = _state(architecture_revision_count=MAX_ARCHITECTURE_REVISIONS - 1)
    assert _a_brief_feature_the_specification_defers(last, spec) is None
    assert _a_brief_feature_the_specification_defers(_state(), "## Features\n- Reminders by email\n") is None


def test_the_review_node_adds_it():
    import inspect

    from app.graph import workflow

    assert "deferral_finding = _a_brief_feature_the_specification_defers(state, spec_text)" in inspect.getsource(workflow)
