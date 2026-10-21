"""A command argument written under the sandbox's `/workspace`, or another invented root, finds its file.

The read tools take `/workspace/notes-api/...` and the command tools did not:
one run's fixer ran `cat /workspace/notes-api/notes_api/storage.py` and
`ls /workspace/notes-api/notes_api/` and was told "No such file" each time.
"""
from __future__ import annotations

from pathlib import Path

from app.tools.sandbox import workspace_rooted_arguments


def _project(root: Path) -> Path:
    (root / "notes-api" / "notes_api").mkdir(parents=True)
    (root / "notes-api" / "notes_api" / "storage.py").write_text("x = 1\n")
    return root / "notes-api"


def test_a_file_and_a_folder_under_the_mount_are_found(tmp_path: Path):
    project = _project(tmp_path)
    root = str(tmp_path.resolve())

    argv = workspace_rooted_arguments(
        ["cat", "/workspace/notes-api/notes_api/storage.py"], root, str(project.resolve()))
    listing = workspace_rooted_arguments(["ls", "/workspace/notes-api/notes_api/"], root, str(project.resolve()))

    assert argv == ["cat", "notes_api/storage.py"]
    assert listing == ["ls", "notes_api"]


def test_what_nothing_in_the_workspace_matches_is_left_alone(tmp_path: Path):
    project = _project(tmp_path)
    root = str(tmp_path.resolve())

    for argument in ("/workspace/nothing/here.py", "/^a.*b$/", "/usr/bin/env"):
        assert workspace_rooted_arguments(["grep", argument], root, str(project.resolve())) == ["grep", argument]


def test_the_project_spelled_from_the_root_still_works(tmp_path: Path):
    project = _project(tmp_path)

    assert workspace_rooted_arguments(["cat", "/notes-api/notes_api/storage.py"], str(tmp_path.resolve()),
                                      str(project.resolve())) == ["cat", "notes_api/storage.py"]
