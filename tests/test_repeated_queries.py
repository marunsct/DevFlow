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


def test_the_query_notice_also_comes_first() -> None:
    """Same reason as the read notice: it must be seen to change the next call."""
    middleware = build_repeated_query_middleware()
    listing = "\n".join(f"file{i}.js" for i in range(300))

    for _ in range(2):
        _call(middleware, "ls", {"path": "/p"}, listing)
    third = _call(middleware, "ls", {"path": "/p"}, listing)

    assert third.index("returned exactly what it returned") < 200
    assert "file299.js" in third


def _failing_edit(middleware, args, error):
    return _call(middleware, "edit_artifact", args, error)


def test_a_repeated_failing_edit_is_told_so() -> None:
    """The member of the set nobody had added.

    Command repeats are answered by the sandbox notices, listing and search
    repeats by this middleware, and mutations by nothing. run-36eb1260 died on
    it: `specialist_backend_2` sent the same failing `edit_artifact` over and
    over against a five-line file and was stopped as a loop at 1,137 events.
    """
    middleware = build_repeated_query_middleware()
    error = '{"error": "That text appears 2 times in app.test.mjs"}'
    args = {"relative_path": "app.test.mjs", "find": "import x"}

    assert "failed the same way" not in _failing_edit(middleware, args, error)
    assert "failed the same way" not in _failing_edit(middleware, args, error)
    assert "failed the same way" in _failing_edit(middleware, args, error)


def test_a_successful_write_is_not_nagged() -> None:
    """A repeated successful write is already answered by "unchanged" and by
    the no-op edit refusal. A third notice on it would be noise."""
    middleware = build_repeated_query_middleware()
    ok = '{"path": "a.mjs", "status": "written"}'

    for _ in range(4):
        content = _call(middleware, "write_artifact", {"relative_path": "a.mjs"}, ok)
        assert "failed the same way" not in content
        assert "returned exactly what it returned" not in content


def test_a_different_edit_failure_starts_the_count_again() -> None:
    middleware = build_repeated_query_middleware()
    args = {"relative_path": "a.mjs", "find": "x"}

    _failing_edit(middleware, args, '{"error": "appears 2 times"}')
    _failing_edit(middleware, args, '{"error": "appears 2 times"}')
    changed = _failing_edit(middleware, args, '{"error": "Could not find that text"}')

    assert "failed the same way" not in changed


def test_both_error_shapes_are_recognised() -> None:
    """Filesystem tools return `Error: ...`; repository tools return JSON."""
    from app.agents.repeated_queries import _looks_like_a_failure

    assert _looks_like_a_failure("Error: Path '/x': path_not_found")
    assert _looks_like_a_failure('{"error": "Could not find that text"}')
    assert not _looks_like_a_failure('{"path": "a.mjs", "status": "written"}')
    assert not _looks_like_a_failure("app.js\nindex.html")


def _write(middleware, args, content):
    return _call(middleware, "write_artifact", args, content)


UNCHANGED = '{"path": "docs/spec.md", "status": "unchanged", "detail": "already contained"}'
WRITTEN = '{"path": "docs/spec.md", "status": "written"}'


def test_a_third_no_op_write_is_refused_not_noted() -> None:
    """A note the model has ignored twice does not need rewording.

    run-5f4cdd55: `specialist_backend_1` wrote docs/technical_specification.md,
    was told "unchanged ... Do not write it again; continue with your
    response", and wrote it three more times until the run-level guard ended
    the run at 728 events. run-2bcdc19b did the same with final_output.json.

    Refusing a write that would change nothing costs nothing: by definition the
    file already holds exactly that content.
    """
    middleware = build_repeated_query_middleware()

    _write(middleware, {"p": "spec"}, WRITTEN)
    second = _write(middleware, {"p": "spec"}, UNCHANGED)
    third = _write(middleware, {"p": "spec"}, UNCHANGED)
    fourth = _write(middleware, {"p": "spec"}, UNCHANGED)

    assert "error" not in second
    assert "error" not in third
    assert '"error"' in fourth
    assert "already been told that twice" in fourth
    # It must say what to do instead.
    assert "Move on" in fourth


def test_a_write_that_changes_the_file_is_never_touched() -> None:
    """Only a write that changed nothing is refused. A real one always lands."""
    middleware = build_repeated_query_middleware()

    for _ in range(5):
        assert _write(middleware, {"p": "real"}, WRITTEN) == WRITTEN


def test_a_no_op_write_to_a_different_file_keeps_its_own_count() -> None:
    middleware = build_repeated_query_middleware()

    for _ in range(3):
        _write(middleware, {"p": "one"}, UNCHANGED)
    other = _write(middleware, {"p": "two"}, UNCHANGED)

    assert '"error"' not in other


def test_the_unchanged_status_is_what_is_matched() -> None:
    from app.agents.repeated_queries import _changed_nothing

    assert _changed_nothing(UNCHANGED)
    assert not _changed_nothing(WRITTEN)
    assert not _changed_nothing('{"path": "a", "status": "edited"}')
