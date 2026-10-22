"""A read written relative to the project, not the workspace, is served.

The mirror of an invented prefix. One run's `defect_fix_2_3` asked for
`tests/e2e/todo-app.spec.ts`, was told "There is a file of that name at
/todo-list/tests/e2e/todo-app.spec.ts", and spent its next call asking for
exactly that.

Held to the same bar as the prefix case: one file carries that name, the only
thing missing is a single top-level directory, and the request names at least
one directory of its own that agrees with the answer.
"""

from __future__ import annotations

import pytest

from app.agents.workspace_backend import _Suggesting


class _Probe(_Suggesting):
    def __init__(self, cwd):
        self.cwd = str(cwd)


@pytest.fixture
def workspace(tmp_path):
    e2e = tmp_path / "todo-list" / "tests" / "e2e"
    e2e.mkdir(parents=True)
    (e2e / "todo-app.spec.ts").write_text("test('x', () => {});\n")
    (tmp_path / "todo-list" / "app.js").write_text("export const a = 1;\n")
    return tmp_path


class TestTheProjectDirectoryIsSupplied:
    @pytest.mark.parametrize("asked", ["tests/e2e/todo-app.spec.ts", "/tests/e2e/todo-app.spec.ts"])
    def test_it_resolves(self, workspace, asked):
        assert (
            _Probe(workspace)._the_one_path_it_meant(asked)
            == "/todo-list/tests/e2e/todo-app.spec.ts"
        )

    def test_a_read_through_the_backend_returns_the_file(self, workspace):
        from app.agents.workspace_backend import WorkspaceBackend

        backend = WorkspaceBackend(root_dir=str(workspace), virtual_mode=True)

        result = backend.read("/tests/e2e/todo-app.spec.ts")

        assert not result.error
        assert "test('x'" in result.file_data["content"]


class TestItStaysStrict:
    def test_a_bare_name_is_left_alone(self, workspace):
        """It may have meant a file at the root that does not exist."""
        assert _Probe(workspace)._the_one_path_it_meant("app.js") == ""

    def test_a_disagreeing_directory_is_left_alone(self, workspace):
        assert _Probe(workspace)._the_one_path_it_meant("spec/e2e/todo-app.spec.ts") == ""

    def test_more_than_one_missing_directory_is_left_alone(self, workspace):
        assert _Probe(workspace)._the_one_path_it_meant("e2e/todo-app.spec.ts") == ""

    def test_an_ambiguous_name_is_left_alone(self, workspace):
        other = workspace / "other" / "tests" / "e2e"
        other.mkdir(parents=True)
        (other / "todo-app.spec.ts").write_text("x\n")

        assert _Probe(workspace)._the_one_path_it_meant("tests/e2e/todo-app.spec.ts") == ""
