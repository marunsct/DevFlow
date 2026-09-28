"""Listing a directory no stage has created yet says so, not just "not found".

One run's `scrum_master` listed `/`, got `.gitignore` and `docs/`, then listed
`/task-manager` - the right name, empty because nothing had been written - and
was answered with a bare "path_not_found". Two more stages did the same.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.workspace_backend import WorkspaceBackend
from app.tools.repository import PROJECT_MARKER


def _error(root: Path, path: str) -> str:
    return str(getattr(WorkspaceBackend(str(root), virtual_mode=True).ls(path), "error", "") or "")


def test_a_directory_nothing_has_created(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()

    error = _error(tmp_path, "/task-manager")

    assert "path_not_found" in error
    assert "Nothing named 'task-manager' exists anywhere in the workspace yet" in error
    assert "created by the first file written under it" in error


def test_the_pinned_project_directory_is_named_as_such(tmp_path: Path) -> None:
    (tmp_path / PROJECT_MARKER).write_text("task-manager\n", encoding="utf-8")

    error = _error(tmp_path, "/task-manager")

    assert "'/task-manager' is this run's project directory" in error


def test_a_directory_that_exists_elsewhere_still_gets_the_better_hint(tmp_path: Path) -> None:
    """Where it really is beats "not yet"."""
    (tmp_path / "app" / "task-manager").mkdir(parents=True)

    error = _error(tmp_path, "/task-manager")

    assert "/app/task-manager" in error
    assert "yet" not in error


def test_a_missing_file_is_not_told_about_directories(tmp_path: Path) -> None:
    assert "Nothing named" not in _error(tmp_path, "/docs/plan.md")
