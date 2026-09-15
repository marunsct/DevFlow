"""The workspace an agent sees, without the machinery that runs it.

The sandbox points HOME at `.agent-home` inside the workspace so package caches
land per-run. In container mode that is not a choice - only the workspace is
mounted, so anything a command writes must be inside it.

Measured on run-61c5a5b6: 42 tool results across ten stages carried
`.agent-home`, every `ls /` opened with it, and one `npm install` left 26 cache
blobs with sha512 filenames. `list_repository_files` skipped it; `ls`, `glob`
and `grep` come from the deep-agent backend and did not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.workspace_backend import WorkspaceBackend, _is_hidden, _path_of


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    cache = tmp_path / ".agent-home/.npm/_cacache"
    cache.mkdir(parents=True)
    (cache / "sha512blob").write_text("cached\n", encoding="utf-8")
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj/app.js").write_text("function createTask(){}\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules/dep.js").write_text("//\n", encoding="utf-8")
    return tmp_path


def _backend(workspace: Path) -> WorkspaceBackend:
    return WorkspaceBackend(root_dir=str(workspace), virtual_mode=True)


def test_the_run_s_own_cache_is_not_listed(workspace: Path) -> None:
    entries = _backend(workspace).ls("/").entries

    assert not any("agent-home" in _path_of(e) for e in entries)
    assert any("proj" in _path_of(e) for e in entries)


def test_glob_does_not_reach_into_it(workspace: Path) -> None:
    matches = _backend(workspace).glob("**/*").matches

    assert not any("agent-home" in _path_of(m) for m in matches)
    assert any("app.js" in _path_of(m) for m in matches)


def test_dependencies_are_hidden_by_the_same_list(workspace: Path) -> None:
    """One list, so the repository tools and the agent's tools cannot drift."""
    matches = _backend(workspace).glob("**/*").matches

    assert not any("node_modules" in _path_of(m) for m in matches)


def test_the_hidden_list_comes_from_the_repository_tools() -> None:
    import inspect

    from app.agents import workspace_backend

    source = inspect.getsource(workspace_backend)

    assert "from app.tools.repository import IGNORED_DIRECTORIES" in source


def test_reading_a_hidden_path_still_works(workspace: Path) -> None:
    """An agent that names a path inside one of these has a reason, and a read
    that silently failed would be a worse surprise than a quiet listing."""
    result = _backend(workspace).read("/.agent-home/.npm/_cacache/sha512blob")

    assert "cached" in str(getattr(result, "content", result))


def test_the_directory_is_still_there_for_the_sandbox(workspace: Path) -> None:
    """It is the agent's view that changes. Hiding it from a listing must not
    mean a command cannot write to it."""
    _backend(workspace).ls("/")

    assert (workspace / ".agent-home/.npm/_cacache/sha512blob").exists()


@pytest.mark.parametrize(
    ("entry", "hidden"),
    [
        ({"path": "/.agent-home/x", "is_dir": False}, True),
        ({"path": "/proj/app.js", "is_dir": False}, False),
        ({"path": "/proj/build/out.js", "is_dir": False}, True),
        # A file merely *named* like a hidden directory is not one.
        ({"path": "/proj/build.js", "is_dir": False}, False),
        ("/node_modules/dep.js", True),
    ],
)
def test_an_entry_is_judged_by_its_path_not_its_repr(entry, hidden) -> None:
    """Entries arrive as dicts, objects or strings. Matching the string form of
    a whole dict would work by accident and break on the first entry whose
    other fields happened to contain a directory name."""
    assert _is_hidden(entry) is hidden


def test_role_agents_use_it() -> None:
    import inspect

    from app.agents import role_agent

    source = inspect.getsource(role_agent._workspace_filesystem_middleware)

    assert "WorkspaceBackend(" in source
    assert "FilesystemBackend(" not in source


# --- "not found" that says where it actually is --------------------------


import tempfile
from pathlib import Path as _Path

import pytest

from app.agents.workspace_backend import WorkspaceBackend


@pytest.fixture
def backend(tmp_path):
    (tmp_path / "todo-app").mkdir()
    (tmp_path / "todo-app/app.js").write_text("export function a(){}\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/plan.md").write_text("# plan\n", encoding="utf-8")
    return WorkspaceBackend(str(tmp_path), virtual_mode=True)


def test_an_invented_prefix_is_told_where_the_file_is(backend) -> None:
    """The guesses agents actually make, from the stored runs.

    On run-3f8e387d - the run that died of gate exhaustion - 72 reads failed
    and 56 of them (77%) named a file that was in the workspace under a
    different path. The error named only the path the agent had invented, so
    it invented another.
    """
    for invented in (
        "/home/user/docs/plan.md",
        "/workspace/docs/plan.md",
        "/app/data/workspaces/t1/docs/plan.md",
    ):
        error = backend.read(invented).error
        assert "/docs/plan.md" in error
        assert "relative to the workspace root" in error


def test_a_project_file_named_at_the_root_is_located(backend) -> None:
    """`/app.js` when the file is `todo-app/app.js` - run-2f252e4e made this
    call 21 times and run-3f8e387d 87 times."""
    assert "/todo-app/app.js" in backend.read("/app.js").error


def test_a_missing_directory_is_located_too(tmp_path) -> None:
    """`ls` misses directory names, which have no extension to match on:
    run-2eb3aa24 asked for `/simple-to-do-list-app` four times."""
    (tmp_path / "nested/todo-app").mkdir(parents=True)
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    assert "/nested/todo-app" in backend.ls("/todo-app").error


def test_a_file_that_is_nowhere_gets_no_suggestion(backend) -> None:
    """A genuine typo must not be answered with a guess."""
    error = backend.read("/nope.js").error

    assert "not found" in error
    assert "There is a file" not in error


def test_a_successful_read_is_untouched(backend) -> None:
    result = backend.read("/todo-app/app.js")

    assert not getattr(result, "error", None)


def test_the_agent_s_own_cache_is_never_suggested(tmp_path) -> None:
    """`.agent-home` is hidden from listings; suggesting a path inside it would
    put it back."""
    cache = tmp_path / ".agent-home/.npm/_cacache"
    cache.mkdir(parents=True)
    (cache / "plan.md").write_text("junk\n", encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    error = backend.read("/docs/plan.md").error

    assert "agent-home" not in error
