"""A milestone with scope and no tasks is not a plan.

run-a7150a6c's fifth plan named a full scope - "Add event handlers and UI
rendering for add, edit, delete, toggle in app.js; unit tests for these
functions; documentation for CRUD functionality; encrypt data before saving to
localStorage; sanitize..." - and delegated nothing, with no blockers.

The workflow accepted it, found no specialists to dispatch, and ran a test
round, a security review and a milestone review on a milestone where nothing
had been built. Thirteen model calls later the lead was asked again and
produced three tasks.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.technical_lead import MilestonePlanOutput

TASK = {"specialist_role": "backend", "task_description": "Implement addTask in app.js."}


def test_a_plan_that_assigns_nothing_is_refused() -> None:
    with pytest.raises(ValidationError) as caught:
        MilestonePlanOutput(
            selected_sprint_goal="Implement CRUD UI operations",
            milestone_scope=["Add event handlers and UI rendering for add, edit, delete"],
        )

    assert "nobody will build any of it" in str(caught.value)


def test_a_plan_with_tasks_is_accepted() -> None:
    plan = MilestonePlanOutput(
        selected_sprint_goal="g", milestone_scope=["build it"], delegated_tasks=[TASK]
    )

    assert len(plan.delegated_tasks) == 1


def test_a_milestone_that_cannot_start_says_so_in_blockers() -> None:
    """The field exists for exactly this, and is the honest way to say it."""
    plan = MilestonePlanOutput(
        selected_sprint_goal="g",
        milestone_scope=["build it"],
        blockers=["The database schema has not been approved."],
    )

    assert plan.delegated_tasks == []


def test_a_plan_with_no_scope_at_all_is_not_judged() -> None:
    """Nothing claimed, nothing unassigned."""
    assert MilestonePlanOutput(selected_sprint_goal="g").milestone_scope == []


def test_the_revision_shape_still_validates() -> None:
    """A revision assigns each requested change to a task; it must not be
    caught by this."""
    plan = MilestonePlanOutput(
        selected_sprint_goal="g",
        milestone_scope=["fix the failing suite"],
        delegated_tasks=[TASK],
        review_task_assignments=["Fix the localStorage mock -> task 1 (backend)"],
    )

    assert plan.review_task_assignments
