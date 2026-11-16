"""A compiler's relative path already holding the project directory is not given it twice (found on a run).

Measured on one run (a Java service): a compiler finding named `notes-api/notes-api/src/test/java/.../X.java`, a file
that does not exist - the compiler printed the path from the workspace, and the project directory was put in front of
it again; a fixer told of it is sent to a tree that is not there.
"""
from __future__ import annotations

from app.analysis import compiler_check


def _tree(tmp_path):
    source = tmp_path / "notes-api" / "src" / "test" / "X.java"
    source.parent.mkdir(parents=True)
    source.write_text("class X {}\n")
    return tmp_path, tmp_path / "notes-api"


def test_a_path_from_the_workspace_is_kept_as_it_is(tmp_path):
    workspace, project = _tree(tmp_path)
    assert compiler_check._relative("notes-api/src/test/X.java", project, workspace) == "notes-api/src/test/X.java"


def test_a_path_from_the_project_is_given_the_project_as_before(tmp_path):
    workspace, project = _tree(tmp_path)
    assert compiler_check._relative("src/test/X.java", project, workspace) == "notes-api/src/test/X.java"
    assert compiler_check._relative("./src/test/X.java", project, workspace) == "notes-api/src/test/X.java"
