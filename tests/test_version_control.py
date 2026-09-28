"""A commit per accepted milestone, so there is always a known-good state.

Nothing in a run could answer "what did the last sprint change?" or "what did
this look like when it last worked?". Every stage re-read the workspace to find
out - 257 `read_file` calls over 22 distinct files on one run - and a
sprint that broke something had nothing to fall back to.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.tools.version_control import (
    changed_since,
    commit_milestone,
    initialise_repository,
    is_repository,
    last_good_commit,
)

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _log(root: Path) -> str:
    return subprocess.run(
        ["git", "log", "--oneline"], cwd=root, capture_output=True, text=True
    ).stdout


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "app.js").write_text("function createTask(){}\n", encoding="utf-8")
    return tmp_path


@needs_git
def test_a_new_workspace_is_a_repository_with_a_baseline(workspace: Path) -> None:
    """Without a baseline the first sprint commit has nothing to diff against,
    and "what changed this sprint" is the whole point."""
    assert initialise_repository(workspace)
    assert is_repository(workspace)
    assert "Baseline" in _log(workspace)


@needs_git
def test_an_accepted_milestone_is_committed_and_tagged(workspace: Path) -> None:
    initialise_repository(workspace)
    (workspace / "app.js").write_text("function createTask(){}\nfunction init(){}\n", encoding="utf-8")

    commit = commit_milestone(workspace, sprint=1, goal="Users can create tasks")

    assert commit
    assert "Sprint 1: Users can create tasks" in _log(workspace)
    tags = subprocess.run(["git", "tag"], cwd=workspace, capture_output=True, text=True).stdout
    assert "sprint-1" in tags


@needs_git
def test_the_agents_package_cache_is_never_committed(workspace: Path) -> None:
    """One `npm install` leaves tens of thousands of files that are not the
    product, and the sandbox puts them inside the workspace because container
    mode mounts nothing else."""
    cache = workspace / ".agent-home/.npm/_cacache"
    cache.mkdir(parents=True)
    (cache / "sha512blob").write_text("cached\n", encoding="utf-8")

    initialise_repository(workspace)
    commit_milestone(workspace, sprint=1, goal="anything")

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=workspace, capture_output=True, text=True
    ).stdout
    assert "agent-home" not in tracked
    assert "app.js" in tracked


@needs_git
def test_a_later_sprint_can_see_what_an_earlier_one_changed(workspace: Path) -> None:
    """The cheap answer to a question every stage currently re-reads the whole
    workspace to work out."""
    initialise_repository(workspace)
    commit_milestone(workspace, sprint=1, goal="first")
    (workspace / "style.css").write_text("body{}\n", encoding="utf-8")
    (workspace / "app.js").write_text("function createTask(){}\n// more\n", encoding="utf-8")
    commit_milestone(workspace, sprint=2, goal="second")

    changed = changed_since(workspace, "sprint-1")

    assert sorted(changed) == ["app.js", "style.css"]


@needs_git
def test_a_sprint_that_changed_nothing_is_not_an_error(workspace: Path) -> None:
    """It still passed its review; there is simply nothing to record."""
    initialise_repository(workspace)

    assert commit_milestone(workspace, sprint=1, goal="nothing changed") is None


@needs_git
def test_a_long_goal_does_not_become_a_long_subject_line(workspace: Path) -> None:
    """A commit subject is a line; a sprint goal is a sentence."""
    initialise_repository(workspace)
    (workspace / "app.js").write_text("changed\n", encoding="utf-8")

    commit_milestone(workspace, sprint=1, goal="x" * 200)

    subject = _log(workspace).splitlines()[0]
    assert len(subject) < 90
    assert subject.endswith("...")


@needs_git
def test_the_evidence_is_kept_in_the_body(workspace: Path) -> None:
    initialise_repository(workspace)
    (workspace / "app.js").write_text("changed\n", encoding="utf-8")

    commit_milestone(workspace, sprint=1, goal="short goal", summary="27 tests pass")

    body = subprocess.run(
        ["git", "log", "-1", "--pretty=%b"], cwd=workspace, capture_output=True, text=True
    ).stdout
    assert "27 tests pass" in body


def test_a_workspace_that_is_not_a_repository_reports_so(tmp_path: Path) -> None:
    assert not is_repository(tmp_path)


def test_nothing_here_raises_on_a_missing_directory() -> None:
    """A run that has just passed its review must not fail over history."""
    missing = "/definitely/not/here"

    assert initialise_repository(missing) is False
    assert commit_milestone(missing, sprint=1, goal="x") is None
    assert last_good_commit(missing) is None
    assert changed_since(missing, "HEAD") == []


def test_the_repository_is_created_after_seeding_not_before() -> None:
    """`git clone` has to own an empty directory.

    Initialising at allocation meant a brownfield run cloned into a directory
    that was already a repository, and every one of them would have failed to
    start. Three seeding tests caught it. A seeded codebase that is already a
    repository keeps its own history; this only adds one where there is none.
    """
    import inspect

    from app.server import runs, workspaces

    assert "initialise_repository" not in inspect.getsource(workspaces.allocate_workspace)

    start = inspect.getsource(runs)
    assert "initialise_repository" in start
    assert start.index("seed_workspace, workspace") < start.index(
        "await run_in_threadpool(initialise_repository, workspace)"
    )


@needs_git
def test_an_accepted_milestone_commits_from_the_workflow() -> None:
    """The commit must happen where acceptance is decided, not in a helper
    someone has to remember to call."""
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)

    assert "commit_milestone(" in source
    assert "Could not record a commit for this sprint" in source


@needs_git
def test_a_sprint_that_changed_nothing_is_still_addressable(workspace: Path) -> None:
    """Tagging only on a new commit left a later `git diff sprint-1` pointing at
    a tag that did not exist - which returns nothing and reads as "nothing
    changed" rather than "the question could not be answered"."""
    initialise_repository(workspace)
    commit_milestone(workspace, sprint=1, goal="nothing changed")

    (workspace / "style.css").write_text("body{}\n", encoding="utf-8")
    commit_milestone(workspace, sprint=2, goal="something changed")

    assert changed_since(workspace, "sprint-1") == ["style.css"]


# --- the tool agents actually reach for --------------------------------------


@needs_git
def test_an_agent_can_ask_what_the_last_sprint_changed(workspace: Path) -> None:
    """Every stage otherwise works this out by re-reading the workspace: 257
    `read_file` calls over 22 files on one run, most of them untouched."""
    from app.tools.agent_toolkit import build_sprint_history_tool

    initialise_repository(workspace)
    commit_milestone(workspace, sprint=1, goal="first")
    (workspace / "style.css").write_text("body{}\n", encoding="utf-8")
    commit_milestone(workspace, sprint=2, goal="second")

    result = build_sprint_history_tool(str(workspace)).invoke({"sprint": 1})

    assert result["changed"] == ["style.css"]
    assert result["since"] == "sprint-1"


@needs_git
def test_asking_about_a_sprint_that_has_not_happened_is_not_an_error(workspace: Path) -> None:
    """Normal in the first sprint of a run, and a crash there would be worse
    than an answer of "nothing"."""
    from app.tools.agent_toolkit import build_sprint_history_tool

    initialise_repository(workspace)

    result = build_sprint_history_tool(str(workspace)).invoke({"sprint": 3})

    assert result["changed"] == []
    assert "not been accepted yet" in result["note"]


def test_a_workspace_without_history_says_so(tmp_path: Path) -> None:
    from app.tools.agent_toolkit import build_sprint_history_tool

    result = build_sprint_history_tool(str(tmp_path)).invoke({"sprint": 1})

    assert "no sprint history" in result["error"]


def test_the_history_tool_is_not_gated() -> None:
    """It reads history this run wrote itself and changes nothing."""
    from app.tools.agent_toolkit import HUMAN_APPROVAL_TOOLS, build_sprint_history_tool

    assert build_sprint_history_tool("/tmp").name not in HUMAN_APPROVAL_TOOLS


def test_every_role_agent_gets_it() -> None:
    import inspect

    from app.agents.role_agent import create_role_agent

    assert "build_sprint_history_tool(resolved_repo_root)" in inspect.getsource(create_role_agent)
