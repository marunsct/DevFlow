"""A read whose only fault is an invented path prefix is served, not refused.

`_where_it_actually_is` has always found the file and said where it is. It then
returned an error, and the stage spent a model call re-asking with the path it
had just been handed.

Measured on the run of 2026-09-21. `technical_lead` asked for::

    /home/user/workspace/task-manager/package.json
    /home/user/workspace/task-manager/style.css
    /home/user/task-manager/style.css
    /home/user/task-manager/package.json

Four reads, four errors, each naming the real path in its own message. The
container prefix is invented; everything after it was right.

Resolved only when the answer cannot be wrong: exactly one file carries that
basename, and the path asked for *ends with* the workspace path - so the request
agrees about the directory as well as the name.
"""

from __future__ import annotations

import pytest

from app.agents.workspace_backend import _Suggesting


class _Probe(_Suggesting):
    """`_Suggesting` with a workspace root, which is all the lookup needs."""

    def __init__(self, cwd):
        self.cwd = str(cwd)


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "task-manager").mkdir()
    (tmp_path / "task-manager" / "app.js").write_text("export const a = 1;\n")
    (tmp_path / "task-manager" / "style.css").write_text("body { margin: 0 }\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "plan.md").write_text("# plan\n")
    return tmp_path


class TestAnInventedPrefixResolves:
    @pytest.mark.parametrize(
        "asked",
        [
            "/home/user/workspace/task-manager/app.js",
            "/home/user/task-manager/app.js",
            "/workspace/task-manager/app.js",
            "/some/deep/host/path/task-manager/app.js",
        ],
    )
    def test_the_prefix_is_discarded(self, workspace, asked):
        assert _Probe(workspace)._the_one_path_it_meant(asked) == "/task-manager/app.js"

    def test_it_returns_a_workspace_relative_path(self, workspace):
        found = _Probe(workspace)._the_one_path_it_meant(
            "/home/user/workspace/docs/plan.md"
        )
        assert found == "/docs/plan.md"


class TestItRefusesToGuess:
    def test_a_bare_basename_is_left_alone(self, workspace):
        """`/app.js` may mean a file at the root that does not exist.

        Silently reading a different one is the wrong kind of helpful.
        """
        assert _Probe(workspace)._the_one_path_it_meant("/app.js") == ""

    def test_a_path_that_disagrees_about_the_directory_is_left_alone(self, workspace):
        """The request must agree about the directory, not only the name."""
        assert _Probe(workspace)._the_one_path_it_meant("/somewhere/else/app.js") == ""

    def test_an_ambiguous_basename_is_left_alone(self, workspace):
        (workspace / "second").mkdir()
        (workspace / "second" / "app.js").write_text("x\n")
        assert _Probe(workspace)._the_one_path_it_meant(
            "/home/user/task-manager/app.js"
        ) == ""

    def test_a_correct_path_is_not_rewritten(self, workspace):
        """Already right; there is nothing to correct."""
        assert _Probe(workspace)._the_one_path_it_meant("/task-manager/app.js") == ""

    def test_a_directory_name_is_left_alone(self, workspace):
        """No extension means a directory, which `ls` answers, not `read`."""
        assert _Probe(workspace)._the_one_path_it_meant("/home/user/task-manager") == ""

    def test_a_file_that_does_not_exist_anywhere_is_left_alone(self, workspace):
        assert _Probe(workspace)._the_one_path_it_meant("/home/user/nope.js") == ""

    def test_no_workspace_root_is_not_a_crash(self):
        probe = _Suggesting()
        assert probe._the_one_path_it_meant("/anything.js") == ""


class TestItCannotReachOutsideTheWorkspace:
    def test_the_candidate_always_comes_from_inside(self, workspace, tmp_path):
        """The lookup is an rglob rooted at the workspace.

        This widens what a path may be *spelled* as, never what it may reach.
        """
        outside = tmp_path.parent / "outside-secret.js"
        outside.write_text("secret\n")
        assert _Probe(workspace)._the_one_path_it_meant(str(outside)) == ""


class TestItIsWiredIntoRead:
    def test_read_tries_the_corrected_path_before_erroring(self):
        import inspect

        from app.agents.workspace_backend import WorkspaceBackend

        source = inspect.getsource(WorkspaceBackend.read)
        correction = source.index("_the_one_path_it_meant")
        hint = source.index("_where_it_actually_is")
        assert correction < hint, "the file should be read before explaining where it is"


class TestTheHarnessesOwnRecordsAreNotCandidates:
    """`.harness/` is the harness's, invisible to the stages, and the name
    searches did not skip it. One run's technical lead asked for the locked
    acceptance spec under `/home/user/`; the harness keeps a private copy of
    that spec under `.harness/`, so two files carried the name, the request was
    refused as ambiguous four times, and each refusal offered the copy."""

    @pytest.fixture
    def with_a_private_copy(self, workspace):
        spec = workspace / "task-manager" / "acceptance" / "flow.spec.js"
        spec.parent.mkdir()
        spec.write_text("test('[AC-1] adds', async () => {});\n")
        copy = workspace / ".harness" / "acceptance-snapshot" / "task-manager" / "acceptance" / "flow.spec.js"
        copy.parent.mkdir(parents=True)
        copy.write_text(spec.read_text())
        return workspace

    def test_the_invented_prefix_still_resolves_to_the_spec(self, with_a_private_copy):
        assert _Probe(with_a_private_copy)._the_one_path_it_meant(
            "/home/user/task-manager/acceptance/flow.spec.js"
        ) == "/task-manager/acceptance/flow.spec.js"

    def test_a_miss_never_offers_the_copy(self, with_a_private_copy):
        hint = _Probe(with_a_private_copy)._where_it_actually_is("/elsewhere/flow.spec.js")

        assert "/task-manager/acceptance/flow.spec.js" in hint
        assert ".harness" not in hint

    def test_the_other_read_tool_never_offers_it_either(self, with_a_private_copy):
        from app.tools.repository import RepositoryToolError, read_text_file

        with pytest.raises(RepositoryToolError) as refused:
            read_text_file(str(with_a_private_copy), "elsewhere/flow.spec.js")

        assert "task-manager/acceptance/flow.spec.js" in str(refused.value)
        assert ".harness" not in str(refused.value)
