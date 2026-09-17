"""A task whose opening verb acts on a document no agent may write.

`_a_task_is_more_than_a_document_the_workflow_owns` already refused a task
whose description and every acceptance criterion named such a document. It
missed the commoner shape, because a criterion usually continues the sentence
rather than repeating the filename:

    Update docs/milestone_review.md to reflect that the test suite passed.
    - docs/milestone_review.md contains a section titled 'Test Results'
    - contains a section titled "Global Export" with relevant details.

The second criterion is about the same file and never says so, so `all(...)`
failed and the task was delegated.

Measured across the stored transcripts: 25 documentation stages, 223 model
calls, two writes between them. Every task sampled opened "Update
docs/technical_specification.md ...", "Update docs/milestone_review.md ..." or
"Edit the existing docs/architecture_review.md ...", and the tool refuses all
three - so the specialist spent its budget being told no.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.technical_lead import SpecialistTask


def _task(description: str, criteria: list[str] | None = None) -> SpecialistTask:
    return SpecialistTask(
        specialist_role="documentation",
        task_description=description,
        acceptance_criteria=criteria or [],
    )


@pytest.mark.parametrize(
    "description",
    [
        "Update docs/technical_specification.md to reflect implementation details",
        "Edit the existing docs/architecture_review.md file to include chunking",
        "Revise docs/sprint_plan.md with the filtering section",
        "Rewrite docs/milestone_review.md to record the passing suite",
    ],
)
def test_a_task_that_opens_on_a_workflow_document_is_refused(description: str):
    with pytest.raises(ValidationError) as raised:
        _task(description, ["- the section is present"])

    assert "no agent can change" in str(raised.value)


def test_a_criterion_that_continues_the_sentence_no_longer_saves_it():
    """The shape that let 223 model calls through."""
    with pytest.raises(ValidationError):
        _task(
            "Update docs/milestone_review.md to reflect that the test suite passed",
            [
                "- docs/milestone_review.md contains a section titled 'Test Results'",
                "- contains a section titled 'Global Export' with relevant details.",
            ],
        )


def test_real_work_that_also_updates_a_document_is_left_alone():
    """The `and` boundary is what protects this, and it is the common good case."""
    task = _task(
        "Implement filtering and update docs/sprint_plan.md",
        ["- Filtering works for all, active and completed"],
    )

    assert task.specialist_role == "documentation"


def test_ordinary_application_work_is_untouched():
    task = _task(
        "Create app.js implementing CRUD operations against localStorage",
        ["- addTask adds a task with a unique id"],
    )

    assert "app.js" in task.task_description


def test_a_task_naming_no_workflow_document_is_untouched():
    task = _task("Update README.md with setup instructions", ["- README explains setup"])

    assert "README" in task.task_description
