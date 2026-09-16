"""The other read tool, given the hints `read_file` has had all along.

`read_file` has said "There is a file of that name at ..." since run-3f8e387d,
where 56 of 72 failed reads named a file that was in the workspace under a
different path. `read_repository_file` had none of it - the third piece of
machinery it turned out to be missing, after the repeat notice and the span
tracking.

Measured across run-499c771a, run-454adf22 and run-04576307: every one failed a
`read_repository_file` of `README.md` at the workspace root while the project's
README sat one directory down.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import (
    RepositoryToolError,
    read_text_file,
    write_approved_artifact,
)


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    write_approved_artifact(tmp_path, "proj/README.md", "# Project\n")
    write_approved_artifact(tmp_path, "proj/app.js", "export const a = 1;\n")
    return tmp_path


def test_a_missing_file_is_told_where_it_is(workspace: Path) -> None:
    with pytest.raises(RepositoryToolError) as caught:
        read_text_file(workspace, "README.md")

    assert "proj/README.md" in str(caught.value)


def test_a_directory_is_told_what_it_holds(workspace: Path) -> None:
    with pytest.raises(RepositoryToolError) as caught:
        read_text_file(workspace, "proj")

    message = str(caught.value)
    assert "is a directory containing" in message
    assert "README.md" in message and "app.js" in message


def test_an_empty_directory_says_so(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()

    with pytest.raises(RepositoryToolError, match="it is empty"):
        read_text_file(tmp_path, "empty")


def test_a_name_that_is_nowhere_gets_no_invented_hint(workspace: Path) -> None:
    with pytest.raises(RepositoryToolError) as caught:
        read_text_file(workspace, "nowhere.md")

    assert "There is a file of that name" not in str(caught.value)


def test_a_file_that_is_there_is_simply_read(workspace: Path) -> None:
    assert read_text_file(workspace, "proj/README.md").strip() == "# Project"


def test_the_hint_does_not_look_inside_ignored_directories(tmp_path: Path) -> None:
    modules = tmp_path / "node_modules" / "left-pad"
    modules.mkdir(parents=True)
    (modules / "README.md").write_text("# vendored\n", encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        read_text_file(tmp_path, "README.md")

    assert "node_modules" not in str(caught.value)
