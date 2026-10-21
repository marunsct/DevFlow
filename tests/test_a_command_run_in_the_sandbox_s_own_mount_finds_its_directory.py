"""A command's working directory given as the sandbox's mount, or with an invented root, finds its directory.

The read tools rewrote `/workspace/docs/...` and the command tools did not: one
run's acceptance writer ran `run_validation` with `working_directory=
"/workspace/notes-api"`, then `"/workspace"`, and was told each time it was
"not a directory in this workspace" - the mount every command it ran had stood in.
"""
from __future__ import annotations

from pathlib import Path

from app.agents.workspace_paths import rewrite_tool_arguments
from app.tools import sandbox


def _run_in(root: Path, directory: str) -> str:
    rewritten = rewrite_tool_arguments(
        "run_validation", {"command": ["python", "-m", "pytest"], "working_directory": directory}, str(root),
    )
    return sandbox.resolve_working_directory(str(root), rewritten["working_directory"])


def test_the_mount_and_a_path_under_it_resolve_to_the_workspace(tmp_path: Path):
    (tmp_path / "notes-api").mkdir()

    assert _run_in(tmp_path, "/workspace/notes-api") == str((tmp_path / "notes-api").resolve())
    assert _run_in(tmp_path, "/workspace") == str(tmp_path.resolve())


def test_a_workspace_that_has_a_workspace_folder_keeps_it(tmp_path: Path):
    (tmp_path / "workspace" / "notes-api").mkdir(parents=True)
    (tmp_path / "notes-api").mkdir()

    assert _run_in(tmp_path, "/workspace/notes-api") == str((tmp_path / "workspace" / "notes-api").resolve())
    assert _run_in(tmp_path, "/workspace") == str((tmp_path / "workspace").resolve())


def test_a_relative_directory_is_untouched(tmp_path: Path):
    (tmp_path / "notes-api").mkdir()

    assert _run_in(tmp_path, "notes-api") == str((tmp_path / "notes-api").resolve())
