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


def _read_error(root: Path, path: str) -> str:
    return str(getattr(WorkspaceBackend(str(root), virtual_mode=True).read(path), "error", "") or "")


def test_a_file_nobody_has_written_says_so(tmp_path: Path) -> None:
    """One run's documentation stage read `README.md` before writing it, got a
    bare "not found", and spent its next call on `ls` to learn the same."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "app.js").write_text("export {}\n", encoding="utf-8")

    error = _read_error(tmp_path, "/app/README.md")

    assert "not found" in error
    assert "No file named 'README.md' exists anywhere in the workspace yet" in error


def test_a_file_that_exists_elsewhere_is_not_called_missing(tmp_path: Path) -> None:
    (tmp_path / "app" / "docs").mkdir(parents=True)
    (tmp_path / "app" / "docs" / "README.md").write_text("# App\n", encoding="utf-8")

    error = _read_error(tmp_path, "/README.md")

    assert "exists anywhere in the workspace yet" not in error


def test_a_copy_in_a_hidden_directory_does_not_count(tmp_path: Path) -> None:
    """A dependency's README is not the product's."""
    (tmp_path / "app" / "node_modules" / "jest").mkdir(parents=True)
    (tmp_path / "app" / "node_modules" / "jest" / "README.md").write_text("# jest\n", encoding="utf-8")

    error = _read_error(tmp_path, "/app/README.md")

    assert "No file named 'README.md' exists anywhere in the workspace yet" in error


def test_a_missing_folder_inside_an_existing_project_does_not_empty_the_project(tmp_path: Path) -> None:
    """Asked for `/task-manager/e2e`, one run was told `/task-manager` - which held
    nine files - "has no file written into it yet"."""
    (tmp_path / PROJECT_MARKER).write_text("task-manager\n", encoding="utf-8")
    (tmp_path / "task-manager").mkdir()
    (tmp_path / "task-manager" / "app.js").write_text("export {}\n", encoding="utf-8")

    error = _error(tmp_path, "/task-manager/e2e")

    assert "no stage has written a file into it yet" not in error
    assert "'/task-manager' exists, but nothing has been written under 'e2e' in it yet" in error
