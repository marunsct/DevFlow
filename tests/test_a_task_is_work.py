"""A delegated task that says there is nothing to do.

run-bb1ee9bb's milestone plan read

    #### backend — N/A
    #### database — N/A
    #### documentation — N/A

The lead was right that those roles had nothing to do: the technical
specification says "no server-side infrastructure", "no server-side storage or
transmission", "No server-side processing required" and "No server side needed".

But a task was delegated anyway, so `specialist_backend_1` was dispatched with
the description "N/A", spent thirty model calls, and wrote a 3,696-byte
`server.js` - in a project whose `app.js` is 84 bytes. An agent handed an empty
task does not stop; it finds something to do.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask


@pytest.mark.parametrize(
    "description",
    ["N/A", "n/a", "N/A.", "none", "None", "nothing", "Not applicable",
     "not required", "skip", "TBD", "-", "--", "", "   "],
)
def test_a_task_that_is_not_work_is_refused(description: str) -> None:
    with pytest.raises(ValidationError) as caught:
        SpecialistTask(specialist_role="backend", task_description=description)

    assert "leave it out of `delegated_tasks`" in str(caught.value)


@pytest.mark.parametrize(
    "description",
    [
        "Implement addTask in app.js.",
        "Add a filter bar to index.html with All, Active and Completed buttons.",
        "Write app.test.mjs covering addTask, editTask and deleteTask.",
    ],
)
def test_a_real_task_is_accepted(description: str) -> None:
    assert SpecialistTask(
        specialist_role="backend", task_description=description
    ).task_description == description


def test_a_plan_that_leaves_the_role_out_is_the_right_shape() -> None:
    """Which is what the lead should do instead, and the schema allows."""
    plan = MilestonePlanOutput(
        selected_sprint_goal="Build the page",
        milestone_scope=["index.html and style.css"],
        delegated_tasks=[
            {"specialist_role": "ui_ux", "task_description": "Write index.html and style.css."}
        ],
    )

    assert [t.specialist_role for t in plan.delegated_tasks] == ["ui_ux"]


def test_the_whole_plan_is_refused_when_one_task_is_empty() -> None:
    """Better one rejected plan than a specialist dispatched with nothing."""
    with pytest.raises(ValidationError):
        MilestonePlanOutput(
            selected_sprint_goal="Build the page",
            milestone_scope=["index.html"],
            delegated_tasks=[
                {"specialist_role": "ui_ux", "task_description": "Write index.html."},
                {"specialist_role": "backend", "task_description": "N/A"},
            ],
        )
