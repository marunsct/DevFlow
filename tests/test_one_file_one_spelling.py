"""Two spellings of one path were two files to every repeat guard.

The workspace is rooted at `/`, so `/task-manager/app.js`,
`task-manager/app.js` and `./task-manager/app.js` are the same file, and every
filesystem tool here accepts all three. Three guards keyed on the raw
argument, so each spelling got its own allowance before anything was said.

Found on one run's `specialist_ui_ux_1`, which read `style.css` six times
as `/task-manager/style.css` and four more as `task-manager/style.css`, and
`app.js` six and four the same way.

`read_file` was already safe: `_note_if_repeated` keys on the file's identity
through the *resolved* path, so spelling cannot split it - and reading is by
far the commonest repeat, so most of the raw difference in the transcripts
(247 calls across 36 runs) was already being caught there. The guards that
were not safe are the ones keying on the argument as typed: the repeated-query
middleware over `ls`, `grep`, `glob`, `inspect_repository` and
`read_repository_file`, every mutating tool, `seen_content`'s per-file history
of what a stage has written, and `workspace_backend`'s memory of a read that
failed. Restricted to those, 16 more repeats become visible across 12 of the
50 stored runs.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage

from app.agents.repeated_queries import _comparable, build_repeated_query_middleware
from app.agents.workspace_paths import the_same_place


@pytest.mark.parametrize(
    "written",
    ["task-manager/app.js", "/task-manager/app.js", "./task-manager/app.js",
     "task-manager//app.js", "task-manager/./app.js", "  /task-manager/app.js  ",
     "task-manager/tests/../app.js", "task-manager\\app.js"],
)
def test_every_spelling_names_one_file(written: str):
    assert the_same_place(written) == "task-manager/app.js"


def test_two_different_files_stay_different():
    assert the_same_place("/a/app.js") != the_same_place("/b/app.js")


def test_the_workspace_root_itself_normalises_to_nothing():
    assert the_same_place("/") == ""
    assert the_same_place("") == ""


def test_a_parent_it_cannot_resolve_is_kept_rather_than_dropped():
    """Leaving the workspace is not the same place as staying in it."""
    assert the_same_place("../outside.js") == "../outside.js"


def test_only_path_arguments_are_normalised():
    """A search pattern that looks like a path is not one."""
    assert _comparable({"pattern": "/a//b", "file_path": "/a//b"}) == {
        "pattern": "/a//b",
        "file_path": "a/b",
    }


def test_a_non_string_path_is_left_alone():
    assert _comparable({"file_path": None, "offset": 0}) == {"file_path": None, "offset": 0}


@pytest.fixture
def call():
    middleware = build_repeated_query_middleware()

    def go(path: str, content: str = "the same bytes", name: str = "ls") -> str:
        request = SimpleNamespace(
            tool_call={"name": name, "args": {"path": path}, "id": "c1"},
            tool=None,
            state=None,
            runtime=None,
        )
        return middleware.wrap_tool_call(
            request, lambda _r: ToolMessage(content=content, tool_call_id="c1")
        ).content

    return go


def test_a_repeat_in_another_spelling_is_still_a_repeat(call):
    """`read_file` resolves the path itself; `ls`, `grep` and `glob` did not."""
    call("task-manager")
    call("/task-manager")

    out = call("./task-manager")

    assert "returned exactly what it returned" in out


def test_a_genuinely_different_place_is_not_a_repeat(call):
    call("task-manager")
    call("/task-manager")

    out = call("task-manager/src")

    assert "returned exactly what it returned" not in out
