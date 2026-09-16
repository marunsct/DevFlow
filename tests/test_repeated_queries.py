"""A listing or a search that answers identically is worth saying so.

`read_file` has had this since finding 59, and finding 80's content key made it
effective: on run-fa7b7286 only 1 of 50 reads returned content the stage
already had. The tools beside it never had it and the waste moved there - 4 of
10 `ls` calls and 4 of 12 `grep` calls returned byte-identical results in that
run, with `ls {'path': 'task-manager'}` run five times inside one stage.
"""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import ToolMessage

from app.agents.repeated_queries import build_repeated_query_middleware


def _call(middleware, name, args, content):
    request = SimpleNamespace(
        tool_call={"name": name, "args": args, "id": "c1"}, tool=None, state=None, runtime=None
    )
    return middleware.wrap_tool_call(
        request, lambda _r: ToolMessage(content=content, tool_call_id="c1")
    ).content


def test_a_third_identical_listing_is_told_so() -> None:
    middleware = build_repeated_query_middleware()

    first = _call(middleware, "ls", {"path": "task-manager"}, "app.js\nindex.html")
    second = _call(middleware, "ls", {"path": "task-manager"}, "app.js\nindex.html")
    third = _call(middleware, "ls", {"path": "task-manager"}, "app.js\nindex.html")

    assert "returned exactly what it returned" not in first
    assert "returned exactly what it returned" not in second
    assert "returned exactly what it returned" in third


def test_a_changed_listing_starts_the_count_again() -> None:
    """A result that differs is evidence something moved, which is the whole
    signal - these results carry their own sizes and modification times."""
    middleware = build_repeated_query_middleware()

    _call(middleware, "ls", {"path": "p"}, "a.js")
    _call(middleware, "ls", {"path": "p"}, "a.js")
    changed = _call(middleware, "ls", {"path": "p"}, "a.js\nb.js")
    after = _call(middleware, "ls", {"path": "p"}, "a.js\nb.js")

    assert "returned exactly what it returned" not in changed
    assert "returned exactly what it returned" not in after


def test_a_different_query_keeps_its_own_count() -> None:
    middleware = build_repeated_query_middleware()

    for _ in range(3):
        _call(middleware, "ls", {"path": "one"}, "x")
    other = _call(middleware, "ls", {"path": "two"}, "y")

    assert "returned exactly what it returned" not in other


def test_a_search_is_covered_too() -> None:
    middleware = build_repeated_query_middleware()

    for _ in range(2):
        _call(middleware, "grep", {"pattern": "taskList", "path": "index.html"}, "12: taskList")
    third = _call(middleware, "grep", {"pattern": "taskList", "path": "index.html"}, "12: taskList")

    assert "returned exactly what it returned" in third


def test_read_file_is_left_to_its_own_notice() -> None:
    """The backend's is better - keyed on the file's identity as well as the
    bytes - and two notices on one result are just noise."""
    middleware = build_repeated_query_middleware()

    for _ in range(4):
        content = _call(middleware, "read_file", {"file_path": "/a.js"}, "same")

    assert "returned exactly what it returned" not in content


def test_the_content_is_never_withheld() -> None:
    middleware = build_repeated_query_middleware()

    for _ in range(4):
        content = _call(middleware, "ls", {"path": "p"}, "app.js\nindex.html")
        assert "app.js" in content and "index.html" in content


def test_a_tool_that_returns_something_else_is_passed_through() -> None:
    """A Command, or anything without string content, must not break the call."""
    middleware = build_repeated_query_middleware()
    request = SimpleNamespace(
        tool_call={"name": "ls", "args": {}, "id": "c1"}, tool=None, state=None, runtime=None
    )
    sentinel = SimpleNamespace(content=None)

    assert middleware.wrap_tool_call(request, lambda _r: sentinel) is sentinel


def test_every_role_agent_gets_it() -> None:
    """Reaching twelve of thirteen is the mistake this codebase has made four
    times."""
    import inspect

    from app.agents.role_agent import create_role_agent

    assert "build_repeated_query_middleware()" in inspect.getsource(create_role_agent)


def test_a_repeated_failure_is_told_it_failed_not_that_it_returned() -> None:
    """The repeated case is usually an error, and the wording has to match.

    Measured on run-9506d3ab's `specialist_ui_ux_0`: three identical
    `ls {'path': 'task-manager'}` within four seconds, every one
    `path_not_found`. The filesystem tools return their errors rather than
    raising, so the notice already saw them - it just described a failure as
    something that "returned", which reads as though content came back.
    """
    middleware = build_repeated_query_middleware()
    error = "Error: Path '/nope': path_not_found"

    for _ in range(2):
        _call(middleware, "ls", {"path": "/nope"}, error)
    third = _call(middleware, "ls", {"path": "/nope"}, error)

    assert "failed the same way" in third
    assert "returned exactly what it returned" not in third
    # The error itself must survive, or the agent loses what went wrong.
    assert "path_not_found" in third


def test_a_successful_repeat_still_says_returned() -> None:
    middleware = build_repeated_query_middleware()

    for _ in range(2):
        _call(middleware, "ls", {"path": "/p"}, "app.js\nindex.html")
    third = _call(middleware, "ls", {"path": "/p"}, "app.js\nindex.html")

    assert "returned exactly what it returned" in third
    assert "failed the same way" not in third
