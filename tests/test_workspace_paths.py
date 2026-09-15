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
