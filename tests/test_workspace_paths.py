"""The host workspace path and `/` name the same place.

Prompts hand agents `repository.root_path` - the real host path - while the
agent filesystem is rooted at the workspace in virtual mode, so `/` is the
workspace. An agent that believes the prompt asks for
`/app/data/workspaces/<run>/todo-app/package.json` and is told the file does
not exist, which it cannot distinguish from a genuinely missing file.

Measured on run-95ca3f72: seven `read_file` calls and one `ls` failed this way,
all for files that existed, and the same path was retried three times in a row.
"""

from __future__ import annotations

import pytest

from app.agents.workspace_paths import rewrite_tool_arguments, workspace_relative

ROOT = "/app/data/workspaces/low2-run-95ca3f72"


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (f"{ROOT}/todo-app/package.json", "/todo-app/package.json"),
        (f"{ROOT}/docs/spec.md", "/docs/spec.md"),
        (ROOT, "/"),
        (f"{ROOT}/", "/"),
    ],
)
def test_a_host_path_is_read_as_the_workspace_root(given, expected):
    assert workspace_relative(given, ROOT) == expected


@pytest.mark.parametrize(
    "already_relative",
    ["/todo-app/package.json", "/docs/spec.md", "todo-app/package.json", "/"],
)
def test_a_root_relative_path_is_left_alone(already_relative):
    assert workspace_relative(already_relative, ROOT) == already_relative


def test_a_path_that_merely_shares_a_prefix_is_left_alone():
    """`/app/data/workspaces/low2-run-95ca3f72-other` is a different workspace."""
    other = f"{ROOT}-other/package.json"

    assert workspace_relative(other, ROOT) == other


def test_the_path_argument_is_rewritten_per_tool():
    assert rewrite_tool_arguments(
        "read_file", {"file_path": f"{ROOT}/todo-app/x.js", "limit": 20}, ROOT
    ) == {"file_path": "/todo-app/x.js", "limit": 20}

    assert rewrite_tool_arguments("ls", {"path": ROOT}, ROOT) == {"path": "/"}


def test_a_tool_without_a_path_argument_is_untouched():
    arguments = {"command": ["npm", "test"]}

    assert rewrite_tool_arguments("run_terminal_command", arguments, ROOT) is arguments


def test_an_unchanged_call_returns_the_same_object():
    """Identity is how the middleware decides whether to override the call.

    `read_file` is no longer an example of one: a call that omits `limit` now
    gains one, which is a change and must override. A call with nothing to
    normalise still returns untouched.
    """
    arguments = {"file_path": "/todo-app/x.js", "limit": 50}

    assert rewrite_tool_arguments("read_file", arguments, ROOT) is arguments


# --- the read window ------------------------------------------------------


def test_a_read_with_no_window_gets_a_useful_one():
    """`read_file`'s own default is 100 lines, less than half what the
    tool-result budget affords. Measured on run-61c5a5b6: 148 of 257 read calls
    carried an explicit offset - they were paging, not sampling, and
    `tests.test.js` alone was paged 57 times."""
    from app.agents.workspace_paths import DEFAULT_READ_LINES, rewrite_tool_arguments

    arguments = rewrite_tool_arguments("read_file", {"file_path": "/app.js"}, "/ws")

    assert arguments["limit"] == DEFAULT_READ_LINES


def test_a_window_the_model_asked_for_is_respected():
    """46 calls in that run set their own limit. Overriding those would be
    reading more than the model wanted, which is the opposite of the point."""
    from app.agents.workspace_paths import rewrite_tool_arguments

    arguments = rewrite_tool_arguments(
        "read_file", {"file_path": "/app.js", "limit": 30}, "/ws"
    )

    assert arguments["limit"] == 30


def test_paging_still_gets_the_wider_window():
    """An agent already on page two is the one paging costs most."""
    from app.agents.workspace_paths import DEFAULT_READ_LINES, rewrite_tool_arguments

    arguments = rewrite_tool_arguments(
        "read_file", {"file_path": "/app.js", "offset": 100}, "/ws"
    )

    assert arguments["offset"] == 100
    assert arguments["limit"] == DEFAULT_READ_LINES


def test_no_other_tool_gains_a_limit():
    from app.agents.workspace_paths import rewrite_tool_arguments

    for name, args in (("ls", {"path": "/"}), ("grep", {"path": "/", "pattern": "x"})):
        assert "limit" not in rewrite_tool_arguments(name, args, "/ws")


def test_the_path_rewrite_still_happens_alongside_it():
    """Both normalisations share one function; neither may shadow the other."""
    from app.agents.workspace_paths import rewrite_tool_arguments

    arguments = rewrite_tool_arguments(
        "read_file", {"file_path": "/ws/app.js"}, "/ws"
    )

    assert arguments["file_path"] == "/app.js"
    assert arguments["limit"] == 400


def test_arguments_are_returned_unchanged_when_nothing_applies():
    """The middleware only calls `override` when something actually changed."""
    from app.agents.workspace_paths import rewrite_tool_arguments

    original = {"path": "/already/fine"}

    assert rewrite_tool_arguments("ls", original, "/ws") is original


# --- a root the model invented ------------------------------------------


def test_an_invented_workspace_root_is_stripped(tmp_path) -> None:
    """Measured on run-44653bd2, on North-Mini-Code-1.0.

    16 `read_file` calls for `/workspace/docs/technical_specification.md` and
    two `ls` of `/workspace` - 18 of that run's 33 tool failures, every one for
    a file that existed one level down. The brief says "The workspace is rooted
    at '/'" and the "there is a file of that name at ..." hint fired on every
    one of them; the model asked again regardless.
    """
    from app.agents.workspace_paths import without_an_invented_root

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/spec.md").write_text("x", encoding="utf-8")

    assert without_an_invented_root("/workspace/docs/spec.md", str(tmp_path)) == "/docs/spec.md"


def test_a_real_directory_of_that_name_is_left_alone(tmp_path) -> None:
    """The reason this resolves against the disk instead of matching a list of
    known prefixes: a workspace may genuinely contain `workspace/`."""
    from app.agents.workspace_paths import without_an_invented_root

    (tmp_path / "workspace/docs").mkdir(parents=True)
    (tmp_path / "workspace/docs/real.md").write_text("y", encoding="utf-8")

    path = "/workspace/docs/real.md"
    assert without_an_invented_root(path, str(tmp_path)) == path


def test_a_genuinely_missing_file_still_fails_as_one(tmp_path) -> None:
    """Rewriting only ever turns a failing path into a working one. A path that
    is wrong in some other way must still be reported wrong."""
    from app.agents.workspace_paths import without_an_invented_root

    (tmp_path / "docs").mkdir()

    assert without_an_invented_root("/docs/missing.md", str(tmp_path)) == "/docs/missing.md"
    assert without_an_invented_root("/nope/deep/gone.md", str(tmp_path)) == "/nope/deep/gone.md"


def test_a_single_segment_is_not_collapsed_to_the_root(tmp_path) -> None:
    """`ls /nowhere` must not quietly become `ls /`.

    The listing tools already answer a bad path with "there is a directory of
    that name at ...", which is worth more than silently showing the root.
    """
    from app.agents.workspace_paths import without_an_invented_root

    assert without_an_invented_root("/workspace", str(tmp_path)) == "/workspace"


def test_the_rewrite_reaches_the_tool_arguments(tmp_path) -> None:
    from app.agents.workspace_paths import rewrite_tool_arguments

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/spec.md").write_text("x", encoding="utf-8")

    rewritten = rewrite_tool_arguments(
        "read_file", {"file_path": "/workspace/docs/spec.md", "limit": 400}, str(tmp_path)
    )

    assert rewritten["file_path"] == "/docs/spec.md"


def test_the_host_path_rewrite_still_runs_first(tmp_path) -> None:
    """Both rewrites apply, in the order that makes each one's input sane."""
    from app.agents.workspace_paths import rewrite_tool_arguments

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/spec.md").write_text("x", encoding="utf-8")

    rewritten = rewrite_tool_arguments(
        "read_file", {"file_path": f"{tmp_path}/docs/spec.md", "limit": 400}, str(tmp_path)
    )

    assert rewritten["file_path"] == "/docs/spec.md"
