"""A run may defer a requirement. It may not define one out of existence.

Measured on run-3c8e772e. `tests/brief_low.md` states "Users can add, edit,
delete tasks". The run's technical specification records:

    Q3: Is inline editing of title/description desired beyond toggling
    completion status? The acceptance criteria mention 'edit' but the core
    workflows only describe marking complete/incomplete. Decision recorded:
    'Edit' refers to toggling completion status. Inline text editing is
    deferred.

From there the documents enumerate create, update, complete and delete, and
never edit. `_actions_the_documents_require` therefore returns a set with no
`edit` in it, `_a_required_action_nothing_implements` finds nothing missing,
and the run completed with no way to edit a task - as did three others. Every
check in the workspace read the restatement, so every check agreed with it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _a_required_action_nothing_implements,
    _a_required_action_no_test_covers,
    _actions_the_brief_requires,
    _source_files,
    summarise_integration,
)

BRIEF = """# Product Brief: Simple To-Do List App

## Acceptance Criteria
- Users can add, edit, delete tasks
- Tasks persist between page refreshes
"""

#: The run's restatement, with `edit` reinterpreted away - run-3c8e772e's shape.
RESTATED = """# Product Intake

## Acceptance Criteria
- A user can create a task, complete it and delete it

## Decisions
- Q3: 'Edit' refers to toggling completion status; inline text editing is deferred.
"""

APP = """
export function addTask(title) { return { title }; }
export function toggleTask(id) { return id; }
export function deleteTask(id) { return id; }
"""

SUITE = """
import { test } from 'node:test';
test('adds', () => {});
test('toggles', () => {});
test('deletes', () => {});
"""


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "product_intake.md").write_text(RESTATED, encoding="utf-8")
    (tmp_path / "app.js").write_text(APP, encoding="utf-8")
    (tmp_path / "app.test.mjs").write_text(SUITE, encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><script type="module" src="app.js"></script></body></html>',
        encoding="utf-8",
    )
    return tmp_path


def test_the_brief_states_what_the_operator_asked_for() -> None:
    assert sorted(_actions_the_brief_requires(BRIEF)) == ["add", "delete", "edit"]


def test_without_the_brief_the_redefinition_is_invisible(workspace: Path) -> None:
    """The behaviour before this change, kept as the thing being fixed."""
    files = _source_files(workspace)

    assert _a_required_action_nothing_implements(files, workspace) == []


def test_with_the_brief_the_redefinition_is_a_finding(workspace: Path) -> None:
    files = _source_files(workspace)

    problems = _a_required_action_nothing_implements(files, workspace, BRIEF)

    assert len(problems) == 1, problems
    assert "`edit`" in problems[0]
    assert "no longer ask for it" in problems[0]


def test_the_finding_says_a_restatement_is_not_a_change(workspace: Path) -> None:
    problem = _a_required_action_nothing_implements(
        _source_files(workspace), workspace, BRIEF
    )[0]

    assert "Restating a brief is not the same as changing it" in problem
    assert "put the descope to the operator" in problem


def test_it_quotes_the_brief_rather_than_the_documents(workspace: Path) -> None:
    """A finding that misattributes its source sends the reviewer to the wrong
    file - and the documents are exactly where the requirement is not."""
    problem = _a_required_action_nothing_implements(
        _source_files(workspace), workspace, BRIEF
    )[0]

    assert "Users can add, edit, delete tasks" in problem


def test_a_deferral_the_run_recorded_is_still_quoted(workspace: Path) -> None:
    """The decision was real and the reasoning was sound. It is the authority
    that is missing, so the finding names the record rather than ignoring it."""
    problem = _a_required_action_nothing_implements(
        _source_files(workspace), workspace, BRIEF
    )[0]

    assert "The run recorded why" in problem


def test_a_product_that_built_it_is_silent(workspace: Path) -> None:
    (workspace / "app.js").write_text(APP + "\nexport function editTask(id, t) {}\n", encoding="utf-8")

    assert _a_required_action_nothing_implements(
        _source_files(workspace), workspace, BRIEF
    ) == []


def test_the_test_check_reads_the_brief_too(workspace: Path) -> None:
    (workspace / "app.js").write_text(APP + "\nexport function editTask(id, t) {}\n", encoding="utf-8")

    problems = _a_required_action_no_test_covers(
        _source_files(workspace), workspace, BRIEF
    )

    assert len(problems) == 1, problems
    assert "`edit`" in problems[0]
    assert "the brief requires" in problems[0]


def test_an_action_the_documents_keep_is_still_attributed_to_them(workspace: Path) -> None:
    (workspace / "docs" / "product_intake.md").write_text(
        "## Acceptance Criteria\n- Users can add, edit and delete tasks\n", encoding="utf-8"
    )
    (workspace / "app.js").write_text(APP + "\nexport function editTask(id, t) {}\n", encoding="utf-8")

    problem = _a_required_action_no_test_covers(
        _source_files(workspace), workspace, BRIEF
    )[0]

    assert "this project's own documents require" in problem


def test_no_brief_leaves_every_check_as_it_was(workspace: Path) -> None:
    """Callers that have no brief - and the tests of every other check - get
    exactly the behaviour they had."""
    assert summarise_integration(str(workspace)) == summarise_integration(
        str(workspace), None, ""
    )


def test_the_summary_carries_it_through(workspace: Path) -> None:
    assert "`edit`" in summarise_integration(str(workspace), None, BRIEF)
