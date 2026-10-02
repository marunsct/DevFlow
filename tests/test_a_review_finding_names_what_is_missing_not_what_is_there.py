"""A finding about a missing action is read for what it says is missing.

Measured on one run. Sprint 1 was planned to build add and delete, sprint 2
editing. The milestone review wrote "The brief explicitly states that users
must be able to add, edit, and delete tasks. The current implementation only
supports adding and deleting; there is no UI or store logic for editing a
task." Read whole it names three actions, two of which this sprint builds, so
it was taken as a finding about this sprint's work and stayed blocking - and
the run ended on a sprint that had done what it was planned to do.
"""

from __future__ import annotations

import pytest

from app.analysis.integration_checks import _what_it_says_is_missing, later_sprint_work_in

THIS_SPRINT = "Initialize the page and implement add and delete with localStorage persistence."
LATER = "Implement task editing, completion toggling and the filter selector. Add editTask to the store."

AS_THE_REVIEWER_WROTE_IT = (
    "The brief explicitly states that users must be able to add, edit, and delete tasks. "
    "The current implementation only supports adding and deleting; there is no UI or "
    "store logic for editing a task."
)


def test_only_the_clause_that_says_something_is_absent_is_the_claim() -> None:
    assert _what_it_says_is_missing(AS_THE_REVIEWER_WROTE_IT) == (
        "there is no UI or store logic for editing a task."
    )


def test_the_run_s_finding_is_about_the_next_sprint_s_work() -> None:
    assert later_sprint_work_in(AS_THE_REVIEWER_WROTE_IT, THIS_SPRINT, LATER) == ["edit"]


@pytest.mark.parametrize("finding", [
    # What this sprint builds is what is missing.
    "Deleting a task does not remove it from storage.",
    "Users cannot add a task: the form is not wired to the store.",
    # Both a later sprint's action and this sprint's are said to be missing.
    "There is no way to edit a task, and deleting one is not implemented either.",
])
def test_a_finding_about_this_sprint_s_work_stays_as_it_was(finding: str) -> None:
    assert later_sprint_work_in(finding, THIS_SPRINT, LATER) == []


def test_the_remedy_is_not_read_as_the_complaint() -> None:
    finding = "Deleting a task does not persist. -> Call save() in deleteTask; do not add an edit form yet."

    assert "edit" not in _what_it_says_is_missing(finding)
    assert later_sprint_work_in(finding, THIS_SPRINT, LATER) == []


def test_a_finding_with_no_absence_in_it_is_read_as_before() -> None:
    assert _what_it_says_is_missing("Editing a task is broken.") == ""
    assert later_sprint_work_in("Editing a task is broken.", THIS_SPRINT, LATER) == ["edit"]
