"""A read of a test's name as if it were a file says which file defines that test.

Measured on one hosted run: an acceptance author read `tasks-api/acceptance/test_ac9_signup_missing_username` six
times - the name of a test from a failure report, taken for a path - and was told six times that no such file exists.
"""
from __future__ import annotations

from pathlib import Path

from app.agents.workspace_backend import WorkspaceBackend


def _read_error(root: Path, path: str) -> str:
    return str(getattr(WorkspaceBackend(str(root), virtual_mode=True).read(path), "error", "") or "")


def test_a_python_test_name_is_pointed_at_its_file(tmp_path: Path) -> None:
    (tmp_path / "tasks-api" / "acceptance").mkdir(parents=True)
    (tmp_path / "tasks-api" / "acceptance" / "test_auth.py").write_text(
        "def test_ac9_signup_missing_username(base_url):\n    assert True\n")

    said = _read_error(tmp_path, "/tasks-api/acceptance/test_ac9_signup_missing_username")

    assert "tasks-api/acceptance/test_auth.py" in said
    assert "not a file" in said


def test_a_go_test_function_is_pointed_at_its_file(tmp_path: Path) -> None:
    (tmp_path / "notes-api").mkdir()
    (tmp_path / "notes-api" / "store_test.go").write_text("package main\n\nfunc TestStoreKeepsNotes(t *testing.T) {}\n")

    said = _read_error(tmp_path, "/notes-api/TestStoreKeepsNotes")

    assert "notes-api/store_test.go" in said


def test_a_name_nothing_defines_gets_the_plain_answer(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("x = 1\n")

    said = _read_error(tmp_path, "/app/no_such_thing_here")

    assert "not a file" not in said
