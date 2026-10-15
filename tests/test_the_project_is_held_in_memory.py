"""The project's documents and files are handed to a stage from memory, kept current.

Measured on one run: 204 `read_file` calls, 55 listings and 37 searches, most
of them a stage finding again what an earlier one had read.
"""

from __future__ import annotations

import inspect
import os
import re
import time
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from app.agents import project_memory, role_agent

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text("# Spec\ncreateStore(dir)\n")
    (tmp_path / "docs" / "sprint_plan.md").write_text("# Sprint 1\n")
    (tmp_path / "docs" / "decision_log.md").write_text("# Decisions\n")
    src = tmp_path / "notes-api" / "src"
    src.mkdir(parents=True)
    (src / "store.ts").write_text("export const store = 1;\n")
    (tmp_path / "notes-api" / "tests").mkdir()
    (tmp_path / "notes-api" / "tests" / "store.test.ts").write_text("// test\n")
    (tmp_path / "notes-api" / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "notes-api" / "node_modules" / "x" / "index.js").write_text("ignored")
    (tmp_path / "notes-api" / "package-lock.json").write_text("{}")
    return tmp_path


def test_documents_come_first_then_the_product_then_its_tests(workspace):
    memory, held = project_memory.render(workspace, 100_000)

    order = [line[4:-4] for line in memory.splitlines() if line.startswith("=== ")]
    assert order == ["docs/technical_specification.md", "docs/sprint_plan.md",
                     "notes-api/src/store.ts", "notes-api/tests/store.test.ts"]
    assert "node_modules" not in memory and "package-lock" not in memory
    assert "docs/decision_log.md" in memory.split("Not included here")[1], "records are named, not handed over"
    assert not BANNED.search(memory.split("\n\n")[0])


def test_a_change_by_anyone_is_in_the_next_memory_and_a_deleted_file_leaves_it(workspace):
    project_memory.render(workspace, 100_000)
    store = workspace / "notes-api" / "src" / "store.ts"
    store.write_text("export const store = 2;\n")
    os.utime(store, ns=(time.time_ns() + 10**9, time.time_ns() + 10**9))
    (workspace / "docs" / "sprint_plan.md").unlink()

    memory, held = project_memory.render(workspace, 100_000)

    assert held["notes-api/src/store.ts"] == "export const store = 2;\n"
    assert "docs/sprint_plan.md" not in held


def test_what_does_not_fit_is_named_and_a_named_file_comes_first(workspace):
    memory, held = project_memory.render(workspace, 120, focus="please fix store.test.ts")

    assert list(held)[0] == "notes-api/tests/store.test.ts"
    assert "notes-api/src/store.ts" not in held
    assert "notes-api/src/store.ts" in memory.split("Not included here")[1]


def test_each_call_gets_it_and_a_read_of_what_it_holds_is_a_pointer(workspace):
    middleware = project_memory.build_project_memory_middleware(str(workspace))
    seen = []

    class Request(SimpleNamespace):
        def override(self, **changes):
            return Request(**{**self.__dict__, **changes})

    middleware.wrap_model_call(Request(messages=[HumanMessage(content="Build it")], model=None),
                               lambda request: seen.append(request.messages))
    assert seen[0][0].content.startswith("[Project memory") and seen[0][0].content.endswith("Build it")

    read = SimpleNamespace(tool_call={"name": "read_file", "id": "r1", "args": {"file_path": "notes-api/src/store.ts"}})
    pointer = middleware.wrap_tool_call(read, lambda request: "the file again")
    assert isinstance(pointer, ToolMessage) and "has not changed" in pointer.content
    (workspace / "notes-api" / "src" / "store.ts").write_text("export const store = 3;\n// longer\n")
    assert middleware.wrap_tool_call(read, lambda request: "the file again") == "the file again"


def test_every_role_agent_has_it():
    source = inspect.getsource(role_agent.create_role_agent)
    assert "build_project_memory_middleware(resolved_repo_root)" in source


def test_it_is_on_in_every_delivery_mode_unless_switched_off(monkeypatch):
    from app import delivery

    monkeypatch.delenv("PROJECT_MEMORY", raising=False)
    monkeypatch.setattr(delivery, "fast", lambda environment=None: False)
    assert project_memory.enabled()
    monkeypatch.setenv("PROJECT_MEMORY", "off")
    assert not project_memory.enabled()


def test_a_read_with_the_path_middleware_s_default_limit_is_a_pointer_too(workspace):
    """The path middleware gives every read a default `limit`; not one read was ever answered from memory."""
    from app.agents.workspace_paths import DEFAULT_READ_LINES

    middleware = project_memory.build_project_memory_middleware(str(workspace))

    class Request(SimpleNamespace):
        def override(self, **changes):
            return Request(**{**self.__dict__, **changes})

    middleware.wrap_model_call(Request(messages=[HumanMessage(content="Build it")], model=None), lambda r: None)
    whole = SimpleNamespace(tool_call={"name": "read_file", "id": "r1",
                                       "args": {"file_path": "notes-api/src/store.ts", "limit": DEFAULT_READ_LINES}})
    part = SimpleNamespace(tool_call={"name": "read_file", "id": "r2",
                                      "args": {"file_path": "notes-api/src/store.ts", "offset": 1, "limit": 1}})

    assert isinstance(middleware.wrap_tool_call(whole, lambda request: "the file again"), ToolMessage)
    assert isinstance(middleware.wrap_tool_call(part, lambda request: "a window"), ToolMessage)


def test_a_window_of_a_held_file_is_a_pointer_and_of_any_other_file_is_read(workspace):
    """A third of all reads were windows (`offset`); each went to disk for lines already in the conversation."""
    (workspace / "docs" / "huge.md").write_text("x" * (project_memory.LARGEST_FILE_CHARACTERS + 10))
    middleware = project_memory.build_project_memory_middleware(str(workspace))

    class Request(SimpleNamespace):
        def override(self, **changes):
            return Request(**{**self.__dict__, **changes})

    middleware.wrap_model_call(Request(messages=[HumanMessage(content="Build it")], model=None), lambda r: None)

    def window(path):
        return SimpleNamespace(tool_call={"name": "read_file", "id": "w", "args": {"file_path": path, "offset": 40, "limit": 20}})

    pointer = middleware.wrap_tool_call(window("/notes-api/tests/store.test.ts"), lambda request: "lines 40-60")
    assert isinstance(pointer, ToolMessage) and "any lines of it" in pointer.content
    assert not BANNED.search(pointer.content)
    assert middleware.wrap_tool_call(window("docs/huge.md"), lambda request: "lines 40-60") == "lines 40-60"
    (workspace / "notes-api" / "tests" / "store.test.ts").write_text("// changed\n")
    assert middleware.wrap_tool_call(window("notes-api/tests/store.test.ts"), lambda request: "fresh") == "fresh"
