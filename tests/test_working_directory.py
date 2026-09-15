"""A command must be able to run inside the project without a shell.

There is no shell in the sandbox, so an agent cannot `cd`. Before
`working_directory` existed, the only way to aim a command at a subdirectory
was a flag the tool happened to provide: `npm --prefix` has one, `npx` and a
shell script have nothing.

Measured on run-95ca3f72, the specialists spent eight commands discovering
`--prefix`, and these were refused outright with no alternative:

    ["cd", "todo-app", "&&", "npx", "jest"]              x2
    ["cd", "todo-app", "&&", "npm", "ci"]
    ["cd", "todo-app", "&&", "./scripts/line_count_check.sh"]
    ["bash", "-lc", "cd todo-app && ./scripts/line_count_check.sh"]

Allowlisting `cd` or `bash` would hand back the shell the sandbox exists to
withhold. This parameter is the alternative.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import (
    WorkingDirectoryRejected,
    resolve_working_directory,
)


def test_no_working_directory_means_the_workspace_root(tmp_path):
    assert resolve_working_directory(str(tmp_path), None) == str(tmp_path.resolve())
    assert resolve_working_directory(str(tmp_path), "") == str(tmp_path.resolve())


def test_a_subdirectory_resolves_inside_the_workspace(tmp_path):
    (tmp_path / "todo-app").mkdir()

    resolved = resolve_working_directory(str(tmp_path), "todo-app")

    assert resolved == str((tmp_path / "todo-app").resolve())


def test_the_workspace_own_absolute_path_is_accepted(tmp_path):
    """Agents read the absolute path out of tool results and pass it back."""
    (tmp_path / "todo-app").mkdir()

    resolved = resolve_working_directory(str(tmp_path), str(tmp_path / "todo-app"))

    assert resolved == str((tmp_path / "todo-app").resolve())


@pytest.mark.parametrize("escape", ["..", "../..", "/etc", "todo-app/../.."])
def test_a_path_outside_the_workspace_is_refused(tmp_path, escape):
    (tmp_path / "todo-app").mkdir()

    with pytest.raises(WorkingDirectoryRejected):
        resolve_working_directory(str(tmp_path), escape)


def test_a_file_is_not_a_working_directory(tmp_path):
    (tmp_path / "package.json").write_text("{}")

    with pytest.raises(WorkingDirectoryRejected) as exc:
        resolve_working_directory(str(tmp_path), "package.json")

    assert "not a directory" in str(exc.value)


def test_a_missing_directory_is_refused(tmp_path):
    with pytest.raises(WorkingDirectoryRejected):
        resolve_working_directory(str(tmp_path), "nope")


def test_validation_runs_in_the_pinned_project_by_default(tmp_path, monkeypatch):
    """`npm test` at the workspace root ran npm's `exit 1` placeholder.

    The pin already decides where code is written. A test command that ignored
    it reported a failure that had nothing to do with the tests.
    """
    from app.tools import repository

    (tmp_path / "todo-app").mkdir()
    (tmp_path / ".project-directory").write_text("todo-app")

    seen = {}

    class _Executor:
        @staticmethod
        def execute(**kwargs):
            seen.update(kwargs)
            return {"returncode": "0", "stdout": "", "stderr": ""}

    monkeypatch.setattr("app.tools.sandbox.SandboxExecutor", _Executor)
    result = repository.run_approved_validation(str(tmp_path), ["npm", "test"])

    assert seen["working_directory"] == "todo-app"
    assert result["working_directory"] == "todo-app"


def test_validation_without_a_pin_runs_at_the_root(tmp_path, monkeypatch):
    seen = {}

    class _Executor:
        @staticmethod
        def execute(**kwargs):
            seen.update(kwargs)
            return {"returncode": "0", "stdout": "", "stderr": ""}

    monkeypatch.setattr("app.tools.sandbox.SandboxExecutor", _Executor)
    from app.tools import repository as repo

    repo.run_approved_validation(str(tmp_path), ["pytest", "-q"])

    assert seen["working_directory"] is None


def test_a_manifest_command_aimed_at_the_project_is_allowed(tmp_path, monkeypatch):
    """The guard refuses a root manifest. Naming the project is the fix it asks for."""
    from app.tools.sandbox import SandboxExecutor

    (tmp_path / "todo-app").mkdir()
    (tmp_path / ".project-directory").write_text("todo-app")

    ran = {}

    def _fake_run(cls, *args, **kwargs):
        ran["ok"] = True
        return {"returncode": "0", "stdout": "", "stderr": ""}

    monkeypatch.setattr(SandboxExecutor, "_run", classmethod(_fake_run))

    refused = SandboxExecutor.execute(["npm", "init", "-y"], str(tmp_path), "testing_specialist")
    assert "workspace root" in refused.get("error", "")

    ran.clear()
    SandboxExecutor.execute(
        ["npm", "init", "-y"], str(tmp_path), "testing_specialist", working_directory="todo-app"
    )
    assert ran.get("ok") is True


def test_the_backend_specialist_can_run_node():
    """It was refused `node -e ...` on code it had just written, while `npx` was allowed."""
    from app.tools.sandbox import allowed_executables

    assert "node" in allowed_executables("backend_specialist")


def test_a_workspace_rooted_path_names_the_subdirectory(tmp_path):
    """`/project` is how every other tool in this codebase is addressed.

    The read tools, the write tool and the prompt all teach the leading slash
    as "from the workspace root". `working_directory` alone read it as the
    filesystem root and refused it. Measured on run-61c5a5b6: the UI
    specialist ran its verifier with `working_directory="/simple-to-do-list-app"`
    and was told that directory was "outside the workspace".
    """
    from app.tools.sandbox import resolve_working_directory

    (tmp_path / "simple-to-do-list-app").mkdir()

    resolved = resolve_working_directory(str(tmp_path), "/simple-to-do-list-app")

    assert resolved == str((tmp_path / "simple-to-do-list-app").resolve())


def test_the_workspace_s_own_absolute_path_still_works(tmp_path):
    """Agents read it out of tool results; it must not regress."""
    from app.tools.sandbox import resolve_working_directory

    (tmp_path / "app").mkdir()

    resolved = resolve_working_directory(str(tmp_path), str(tmp_path / "app"))

    assert resolved == str((tmp_path / "app").resolve())


def test_a_workspace_rooted_path_cannot_reach_the_real_filesystem(tmp_path):
    """Reading the slash as workspace-relative must not become a way out."""
    import pytest

    from app.tools.sandbox import WorkingDirectoryRejected, resolve_working_directory

    with pytest.raises(WorkingDirectoryRejected):
        resolve_working_directory(str(tmp_path), "/etc")

    with pytest.raises(WorkingDirectoryRejected):
        resolve_working_directory(str(tmp_path), "/../..")


def test_the_bare_workspace_root_is_accepted(tmp_path):
    """`working_directory="/"` means the workspace root, not the host's.

    Measured on run-61c5a5b6: the defect-fix agent passed `/`, was refused,
    and spent two more gates on `pwd` and `ls` working out where it was.
    """
    from app.tools.sandbox import resolve_working_directory

    assert resolve_working_directory(str(tmp_path), "/") == str(tmp_path.resolve())


# --- the same convention, in command arguments ----------------------------


def test_a_workspace_rooted_argument_names_the_file_it_means(tmp_path):
    """`/project/file` is how every other tool in this codebase is addressed.

    Measured on run-61c5a5b6: `wc -l /simple-to-do-list-app/index.html` found
    nothing, and the documentation specialist spent six approval gates on
    `pwd`, `ls /`, `find` and two more spellings of the same command.
    """
    from app.tools.sandbox import workspace_rooted_arguments

    (tmp_path / "proj").mkdir()
    (tmp_path / "proj/index.html").write_text("x", encoding="utf-8")

    argv = workspace_rooted_arguments(
        ["wc", "-l", "/proj/index.html"], str(tmp_path), str(tmp_path)
    )

    assert argv == ["wc", "-l", "proj/index.html"]


def test_the_rewrite_is_relative_to_where_the_command_runs(tmp_path):
    """The workspace is mounted at /workspace in a sandbox container and used
    in place otherwise; a relative path is right in both."""
    from app.tools.sandbox import workspace_rooted_arguments

    (tmp_path / "proj").mkdir()
    (tmp_path / "proj/index.html").write_text("x", encoding="utf-8")

    argv = workspace_rooted_arguments(
        ["wc", "-l", "/proj/index.html"], str(tmp_path), str(tmp_path / "proj")
    )

    assert argv == ["wc", "-l", "index.html"]


def test_a_real_absolute_path_is_left_alone(tmp_path):
    from app.tools.sandbox import workspace_rooted_arguments

    argv = workspace_rooted_arguments(["node", "/usr"], str(tmp_path), str(tmp_path))

    assert argv == ["node", "/usr"]


def test_an_argument_that_is_not_a_path_is_left_alone(tmp_path):
    """A regex, a URL or a flag has no workspace file behind it, so nothing fires."""
    from app.tools.sandbox import workspace_rooted_arguments

    argv = workspace_rooted_arguments(
        ["grep", "/nothing-here/", "-r"], str(tmp_path), str(tmp_path)
    )

    assert argv == ["grep", "/nothing-here/", "-r"]


def test_the_executable_itself_is_never_rewritten(tmp_path):
    """argv[0] goes through the allowlist by basename; rewriting it would change
    which program the allowlist approved."""
    from app.tools.sandbox import workspace_rooted_arguments

    (tmp_path / "node").write_text("#!/bin/sh\n", encoding="utf-8")

    argv = workspace_rooted_arguments(["/node", "x"], str(tmp_path), str(tmp_path))

    assert argv[0] == "/node"


def test_a_rewrite_cannot_reach_outside_the_workspace(tmp_path):
    """`/../secret` must not become a way to name a file the sandbox hides."""
    from app.tools.sandbox import workspace_rooted_arguments

    outside = tmp_path.parent / "secret.txt"
    outside.write_text("s", encoding="utf-8")
    workspace = tmp_path / "ws"
    workspace.mkdir()

    argv = workspace_rooted_arguments(
        ["wc", "-l", f"/../{outside.name}"], str(workspace), str(workspace)
    )

    assert argv == ["wc", "-l", f"/../{outside.name}"]


def test_a_directory_being_created_is_rewritten_too(tmp_path):
    """A `mkdir` target does not exist yet by definition.

    Requiring the path itself to be present excluded exactly the case that
    needs the rewrite. Measured on run-2b5def74: the testing specialist spent
    five gates on `mkdir -p /simple-to-do-list-app/tests`, `mkdir -p /tests`,
    `ls`, `pwd` and finally a relative path - and left the tests in the wrong
    directory as a result.
    """
    from app.tools.sandbox import workspace_rooted_arguments

    (tmp_path / "proj").mkdir()

    argv = workspace_rooted_arguments(
        ["mkdir", "-p", "/proj/tests"], str(tmp_path), str(tmp_path)
    )

    assert argv == ["mkdir", "-p", "proj/tests"]


def test_a_new_directory_at_the_workspace_root_is_rewritten(tmp_path):
    from app.tools.sandbox import workspace_rooted_arguments

    argv = workspace_rooted_arguments(
        ["mkdir", "-p", "/tests"], str(tmp_path), str(tmp_path)
    )

    assert argv == ["mkdir", "-p", "tests"]


def test_a_path_whose_parent_is_not_here_is_left_alone(tmp_path):
    """Accepting a missing path must not widen the rule to everything absolute."""
    from app.tools.sandbox import workspace_rooted_arguments

    argv = workspace_rooted_arguments(
        ["mkdir", "-p", "/nothing/here/deep"], str(tmp_path), str(tmp_path)
    )

    assert argv == ["mkdir", "-p", "/nothing/here/deep"]


def test_a_real_system_path_is_still_left_alone(tmp_path):
    from app.tools.sandbox import workspace_rooted_arguments

    argv = workspace_rooted_arguments(["cat", "/etc/passwd"], str(tmp_path), str(tmp_path))

    assert argv == ["cat", "/etc/passwd"]
