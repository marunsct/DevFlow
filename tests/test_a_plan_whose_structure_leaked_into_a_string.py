"""A sprint whose list entries are the response's own structure is refused.

Measured on one run. The plan arrived as one sprint whose `in_scope` held the
sprint's work and then the rest of the JSON - `out_of_scope":"..."`,
`dependencies_on_sprints":[]`, `acceptance_criteria":[...]} ,{` - with every
later sprint closed inside a string. It was a valid one-sprint plan; the run
built that sprint and completed with a product that could only add a task.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.scrum_master import SprintDefinition


def _sprint(**fields):
    return SprintDefinition(goal="Foundation", user_value="A base to build on", **fields)


@pytest.mark.parametrize("entry", [
    'out_of_scope":"Any UI styling beyond a basic layout."},',
    'dependencies_on_sprints":[]',
    'acceptance_criteria":["Unit tests pass.","UI renders an empty list."]} ,{',
    '"goal": "Implement CRUD"',
])
def test_an_entry_that_is_a_field_of_the_response_is_refused(entry) -> None:
    with pytest.raises(ValidationError) as caught:
        _sprint(in_scope=["Create the project directory.", entry])

    assert "written inside a string" in str(caught.value)
    assert "every sprint as its own object" in str(caught.value)


@pytest.mark.parametrize("entry", [
    'Add package.json with "type": "module" and scripts: {"test":"node --test tests/*.js"}.',
    "Note: the list renders on load.",
    'Persist tasks to localStorage under key "tasks": an array of task objects.',
    "Implement addTask(), editTask() and deleteTask().",
])
def test_prose_that_quotes_code_is_kept(entry) -> None:
    assert _sprint(in_scope=[entry]).in_scope == [entry]


def test_every_list_field_is_checked() -> None:
    for field in ("out_of_scope", "acceptance_criteria", "risks", "test_strategy"):
        with pytest.raises(ValidationError):
            _sprint(**{field: ['user_value":"x"']})


def test_a_plan_that_assigns_nothing_is_recognised() -> None:
    from app.graph.workflow import _the_plan_assigns_nothing

    measures = ["add, edit, delete", "persists", "filters"]

    assert _the_plan_assigns_nothing([1, 2, 3], measures) is True
    assert _the_plan_assigns_nothing([1, 3], measures) is False
    assert _the_plan_assigns_nothing([], measures) is False
    assert _the_plan_assigns_nothing([], []) is False
