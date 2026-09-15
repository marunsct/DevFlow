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
