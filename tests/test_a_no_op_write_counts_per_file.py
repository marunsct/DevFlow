"""A write that changes nothing counts per file, not per byte sent.

One run's `specialist_backend_0` wrote `docs/README.md` ten times:

    1.     0B  ?
    2.   479B  written
    3.   278B  written
    4.   278B  unchanged
    5.   278B  unchanged
    6.   278B  REFUSED
    7.   278B  REFUSED
    8.   277B  unchanged     <- one trailing newline removed
    9.   277B  unchanged
   10.   277B  REFUSED

The guard fired twice and the stage still spent ten calls on one file. The
counter was keyed on the tool's arguments, which include `content`, so
removing a single byte started a fresh count - and `_with_one_trailing_newline`
means that byte changed nothing at all.
"""

from app.agents import stage_memory
from app.agents.repeated_queries import (
    NO_OP_WRITES_BEFORE_REFUSING,
    build_repeated_query_middleware,
)


class _Result:
    def __init__(self, content):
        self.content = content
        self.status = "success"

    def model_copy(self, update=None):
        copy = _Result(self.content)
        for key, value in (update or {}).items():
            setattr(copy, key, value)
        return copy


class _Request:
    def __init__(self, name, args):
        self.tool_call = {"name": name, "args": args, "id": "c1"}


UNCHANGED = (
    '{"path": "docs/README.md", "status": "unchanged", "detail": "This file '
    'already contained exactly this content, so nothing was rewritten."}'
)


def _write(middleware, content):
    request = _Request("write_artifact", {"relative_path": "docs/README.md", "content": content})
    return middleware.wrap_tool_call(request, lambda _r: _Result(UNCHANGED))


def test_changing_one_byte_does_not_reset_the_count():
    stage_memory.forget_everything()
    middleware = build_repeated_query_middleware()

    for _ in range(NO_OP_WRITES_BEFORE_REFUSING):
        _write(middleware, "# Title\n")

    # The measured escape: same file, one trailing newline fewer.
    result = _write(middleware, "# Title")

    assert "Refusing this write" in result.content


def test_the_first_no_op_writes_are_only_noted():
    stage_memory.forget_everything()
    middleware = build_repeated_query_middleware()

    first = _write(middleware, "# Title\n")

    assert "Refusing this write" not in first.content


def test_a_different_file_keeps_its_own_count():
    stage_memory.forget_everything()
    middleware = build_repeated_query_middleware()

    for _ in range(NO_OP_WRITES_BEFORE_REFUSING + 1):
        _write(middleware, "# Title\n")

    other = _Request("write_artifact", {"relative_path": "docs/OTHER.md", "content": "x"})
    result = middleware.wrap_tool_call(other, lambda _r: _Result(UNCHANGED))

    assert "Refusing this write" not in result.content


def test_a_write_that_actually_changed_the_file_is_never_refused():
    stage_memory.forget_everything()
    middleware = build_repeated_query_middleware()
    written = '{"path": "docs/README.md", "status": "written", "summary": "x"}'

    for index in range(6):
        request = _Request(
            "write_artifact", {"relative_path": "docs/README.md", "content": f"# {index}\n"}
        )
        result = middleware.wrap_tool_call(request, lambda _r: _Result(written))
        assert "Refusing this write" not in result.content


def test_repeated_edit_failures_count_by_file_not_by_the_passage_sent():
    """The failure is the event; the passage the stage guessed at is not.

    `edit_artifact` answers "Could not find that text in 'a.js'" and a stage
    that cannot find it responds by sending a different passage, so `find`
    changes on every retry. Counting per arguments saw every retry as a first
    attempt. Measured on one run: ten retries in `test_round_1`, seven in
    `specialist_testing_2`, each a different `find` against the same file.
    """
    stage_memory.forget_everything()
    middleware = build_repeated_query_middleware()
    failure = '{"error": "Could not find that text in \'a.js\'."}'

    for find in ("x", "y", "z"):
        request = _Request(
            "edit_artifact", {"relative_path": "a.js", "find": find, "replace": "r"}
        )
        result = middleware.wrap_tool_call(request, lambda _r: _Result(failure))

    assert "failed the same way" in result.content


def test_repeated_failures_on_another_file_keep_their_own_count():
    """The path is part of the shape, so a failure on one file is not charged
    to another."""
    stage_memory.forget_everything()
    middleware = build_repeated_query_middleware()
    failure = '{"error": "Could not find that text in \'a.js\'."}'
    other_failure = '{"error": "Could not find that text in \'b.js\'."}'

    for _ in range(3):
        request = _Request(
            "edit_artifact", {"relative_path": "a.js", "find": "x", "replace": "y"}
        )
        middleware.wrap_tool_call(request, lambda _r: _Result(failure))

    other = _Request("edit_artifact", {"relative_path": "b.js", "find": "p", "replace": "q"})
    result = middleware.wrap_tool_call(other, lambda _r: _Result(other_failure))

    assert "failed the same way" not in result.content
