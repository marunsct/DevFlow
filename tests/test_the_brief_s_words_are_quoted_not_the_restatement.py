"""A missing action is quoted in the brief's words, not the run's narrowing of them.

One run's intake wrote "Users can add, edit (toggle complete/incomplete), and
delete tasks" for a brief saying "Users can add, edit, delete tasks". The
final gate found editing unbuilt and sent the last sprint back - quoting the
intake. The technical lead read "edit" as toggling, found toggling built, and
assigned a documentation fix; the run escalated with editing still unbuilt.

The run's documents outrank the brief when choosing which line to quote, so a
finding can point at the file the run acts on. That is right until the
document narrows the requirement: then the narrowing is what gets quoted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _a_required_action_nothing_implements,
    _source_files,
)

BRIEF = """# Product Brief: Simple To-Do List App

## Acceptance Criteria
- Users can add, edit, delete tasks
"""

NARROWED = """# Product Intake

## Acceptance criteria
- Users can add, edit (toggle complete/incomplete), and delete tasks without errors
"""

APP = """
export function addTask(title) { return { title }; }
export function toggleTask(id) { return id; }
export function deleteTask(id) { return id; }
"""


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "product_intake.md").write_text(NARROWED, encoding="utf-8")
    (tmp_path / "app.js").write_text(APP, encoding="utf-8")
    return tmp_path


def _problem(root: Path, brief: str = BRIEF) -> str:
    problems = _a_required_action_nothing_implements(_source_files(root), root, brief)
    assert len(problems) == 1, problems
    return problems[0]


def test_the_brief_is_quoted(workspace):
    problem = _problem(workspace)

    assert "The operator's brief requires that a user can `edit`" in problem
    assert '"- Users can add, edit, delete tasks"' in problem


def test_the_narrowing_is_named_as_a_restatement(workspace):
    problem = _problem(workspace)

    assert "restate it as" in problem
    assert "edit (toggle complete/incomplete)" in problem
    assert "does not satisfy the brief's own words" in problem


def test_a_deferral_is_quoted_the_same_way(workspace):
    (workspace / "docs" / "technical_specification.md").write_text(
        "Inline description editing is deferred.\n", encoding="utf-8"
    )

    problem = _problem(workspace)

    assert "The operator's brief requires that a user can `edit`" in problem
    assert "and also defer it" in problem


def test_a_restatement_in_the_same_words_is_not_called_one(workspace):
    (workspace / "docs" / "product_intake.md").write_text(
        "## Acceptance criteria\n- Users can add, edit, delete tasks\n", encoding="utf-8"
    )

    problem = _problem(workspace)

    assert "restate it as" not in problem


def test_without_a_brief_the_documents_are_quoted(workspace):
    problem = _problem(workspace, brief="")

    assert "This project's own documents require that a user can `edit`" in problem
