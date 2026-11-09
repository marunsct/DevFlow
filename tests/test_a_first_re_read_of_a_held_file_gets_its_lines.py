"""A stage's first read of a file the memory holds gets the file's numbered lines; the second gets the pointer.

Measured on one run: 28 of 197 model calls were reads of files already in the stage's opening memory, each answered
with a one-line pointer to it - a model turn that brought nothing back, after which the stage read on or asked again.
Behind `FIRST_REREAD_ANSWERED`.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from app.agents import project_memory


@pytest.fixture
def middleware(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    src = tmp_path / "notes-api" / "src"
    src.mkdir(parents=True)
    (src / "store.ts").write_text("export const store = 1;\nexport const two = 2;\n")
    built = project_memory.build_project_memory_middleware(str(tmp_path))

    class Request(SimpleNamespace):
        def override(self, **changes):
            return Request(**{**self.__dict__, **changes})

    built.wrap_model_call(Request(messages=[HumanMessage(content="Build it")], model=None), lambda request: None)
    return built


def _read(call_id: str) -> SimpleNamespace:
    return SimpleNamespace(tool_call={"name": "read_file", "id": call_id, "args": {"file_path": "notes-api/src/store.ts"}})


def test_the_first_read_gets_the_numbered_lines_and_the_second_the_pointer(middleware, monkeypatch):
    monkeypatch.setenv("FIRST_REREAD_ANSWERED", "on")

    first = middleware.wrap_tool_call(_read("r1"), lambda request: "the file again")
    second = middleware.wrap_tool_call(_read("r2"), lambda request: "the file again")

    assert isinstance(first, ToolMessage) and "     1\texport const store = 1;" in first.content
    assert "     2\texport const two = 2;" in first.content
    assert project_memory.HELD_POINTER not in first.content, "not counted as a pointer"
    assert isinstance(second, ToolMessage) and project_memory.HELD_POINTER in second.content


def test_off_the_first_read_is_the_pointer_as_before(middleware, monkeypatch):
    monkeypatch.setenv("FIRST_REREAD_ANSWERED", "off")

    first = middleware.wrap_tool_call(_read("r1"), lambda request: "the file again")

    assert project_memory.HELD_POINTER in first.content


def test_it_is_a_switch_the_admin_page_lists():
    from app.observability.provenance import SWITCHES

    assert SWITCHES["FIRST_REREAD_ANSWERED"] == "app.agents.project_memory:first_reread_switch"
