"""The project memory is taken once per stage visit and kept byte for byte (Initiative AA/O.3).

It was rendered again on every call, at the start of the opening request, so
every write a stage made changed the conversation's first message and the
server's prefix cache missed for everything after it on the next call. What
changed since is named in a note at the end, where it invalidates nothing.
"""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import HumanMessage, ToolMessage

from app.agents import project_memory

from tests.test_the_project_is_held_in_memory import workspace  # noqa: F401 - the fixture


class _Request(SimpleNamespace):
    def override(self, **changes):
        return _Request(**{**self.__dict__, **changes})


def _two_calls_with_a_write_between(workspace):
    middleware = project_memory.build_project_memory_middleware(str(workspace))
    seen = []
    middleware.wrap_model_call(_Request(messages=[HumanMessage(content="Fix it")], model=None),
                               lambda r: seen.append(r.messages))
    (workspace / "notes-api" / "src" / "store.ts").write_text("export const store = 2;\nexport const x = 1;\n")
    (workspace / "notes-api" / "src" / "new.ts").write_text("export {};\n")
    middleware.wrap_model_call(_Request(messages=[HumanMessage(content="Fix it")], model=None),
                               lambda r: seen.append(r.messages))
    return middleware, seen


def test_the_opening_request_is_the_same_bytes_after_a_write(workspace):  # noqa: F811
    _, seen = _two_calls_with_a_write_between(workspace)

    assert seen[0][0].content == seen[1][0].content
    assert "export const store = 1;" in seen[1][0].content


def test_what_changed_is_named_at_the_end(workspace):  # noqa: F811
    _, seen = _two_calls_with_a_write_between(workspace)

    note = seen[1][-1]["content"]
    assert note.startswith("[Project memory update]")
    assert "notes-api/src/store.ts (2 lines now)" in note and "notes-api/src/new.ts" in note
    assert len(seen[0]) == 1  # nothing changed before the first call: no note


def test_a_read_of_the_changed_file_returns_the_file(workspace):  # noqa: F811
    middleware, _ = _two_calls_with_a_write_between(workspace)
    read = SimpleNamespace(tool_call={"name": "read_file", "id": "r", "args": {"file_path": "notes-api/src/store.ts"}})

    assert middleware.wrap_tool_call(read, lambda r: "the file now") == "the file now"
    unchanged = SimpleNamespace(tool_call={"name": "read_file", "id": "u",
                                           "args": {"file_path": "notes-api/tests/store.test.ts"}})
    assert isinstance(middleware.wrap_tool_call(unchanged, lambda r: "again"), ToolMessage)


def _a_call(workspace, seen):
    middleware = project_memory.build_project_memory_middleware(str(workspace))
    middleware.wrap_model_call(_Request(messages=[HumanMessage(content="Fix it")], model=None),
                               lambda r: seen.append(r.messages))
    return middleware


def test_an_agent_rebuilt_within_the_visit_keeps_the_visit_s_memory(workspace):  # noqa: F811
    """Measured live: every approved write rebuilt the stage's agent, the new
    middleware took the memory afresh, and the opening request changed 18 times
    in one fix stage's 33 calls - each a prefix-cache miss for the whole request."""
    from app.agents import stage_memory

    stage_memory.forget_everything()
    seen = []
    with stage_memory.remembering("thread-fix-1:defect_fix_1_0"):
        _a_call(workspace, seen)
        (workspace / "notes-api" / "src" / "store.ts").write_text("export const store = 2;\nexport const x = 1;\n")
        rebuilt = _a_call(workspace, seen)

    assert seen[0][0].content == seen[1][0].content
    assert "notes-api/src/store.ts (2 lines now)" in seen[1][-1]["content"]
    read = SimpleNamespace(tool_call={"name": "read_file", "id": "r", "args": {"file_path": "notes-api/src/store.ts"}})
    assert rebuilt.wrap_tool_call(read, lambda r: "the file now") == "the file now"


def test_another_visit_takes_the_memory_afresh(workspace):  # noqa: F811
    from app.agents import stage_memory

    stage_memory.forget_everything()
    seen = []
    with stage_memory.remembering("thread-a:defect_fix_1_0"):
        _a_call(workspace, seen)
    (workspace / "notes-api" / "src" / "store.ts").write_text("export const store = 2;\nexport const x = 1;\n")
    with stage_memory.remembering("thread-b:defect_fix_1_1"):
        _a_call(workspace, seen)

    assert seen[0][0].content != seen[1][0].content
    assert "export const store = 2;" in seen[1][0].content
