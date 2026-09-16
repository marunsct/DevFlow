"""A task whose whole deliverable is a document no agent may write is refused.

The sibling of `_a_task_is_work`, and the same lesson: an agent handed a task
it cannot complete does not stop, it finds something to do.

Measured on run f81808a4. The lead delegated

    Update docs/sprint_plan.md to include a new section detailing the
    filtering feature implementation.
    - docs/sprint_plan.md contains updated content with filtering details

The brief carried the note that exists for exactly this, which says plainly
that the tool refuses and that the content belongs in the structured
response. `specialist_documentation_3` read it and wrote
`docs/placeholder_for_sprint_plan_content.md`; `specialist_ui_ux_3` later
wrote the same invented file twice more, empty. Seven model calls across two
stages for a file nothing reads.

The note cannot be enough here: it says "do the part of this task that is
real work" and there is no such part.
"""

import pytest
from pydantic import ValidationError

from app.agents.technical_lead import SpecialistTask


def _task(description, criteria=None):
    return SpecialistTask(
        specialist_role="documentation",
        task_description=description,
        acceptance_criteria=criteria or [],
    )


def test_the_measured_task_is_refused():
    with pytest.raises(ValidationError) as caught:
        _task(
            "Update docs/sprint_plan.md to include a new section detailing the "
            "filtering feature implementation.",
            ["docs/sprint_plan.md contains updated content with filtering details"],
        )

    message = str(caught.value)
    assert "writes itself" in message
    assert "Delegate the real work instead" in message


def test_a_task_with_no_criteria_at_all_is_refused():
    """Nothing narrows it, so the document is the whole of it."""
    with pytest.raises(ValidationError):
        _task("Update docs/technical_specification.md with the new API")


@pytest.mark.parametrize(
    "name",
    [
        "architecture_review.md",
        "milestone_plan.md",
        "milestone_review.md",
        "product_intake.md",
        "security_review.md",
        "sprint_plan.md",
        "technical_specification.md",
        "technology_stack.md",
        "tools_and_models.md",
    ],
)
def test_every_document_the_workflow_owns_is_covered(name):
    with pytest.raises(ValidationError):
        _task(f"Update docs/{name} with this milestone's outcome")


def test_a_task_with_real_work_beside_it_is_allowed():
    """The existing note handles this one; there is something to do."""
    task = _task(
        "Implement filtering and update docs/sprint_plan.md",
        ["Filtering works in the browser"],
    )

    assert task.specialist_role == "documentation"


def test_an_ordinary_task_is_untouched():
    assert _task("Write the filter module", ["main.js exports filterTasks"])


def test_a_document_the_workflow_does_not_own_is_allowed():
    """`docs/README.md` is the project's, not the workflow's."""
    assert _task("Document the filter feature in docs/README.md", ["docs/README.md explains it"])


def test_the_refusal_says_where_the_content_should_go():
    """A prohibition with no alternative is what produced the invented file."""
    with pytest.raises(ValidationError) as caught:
        _task("Update docs/sprint_plan.md", ["docs/sprint_plan.md is updated"])

    assert "structured response" in str(caught.value)
