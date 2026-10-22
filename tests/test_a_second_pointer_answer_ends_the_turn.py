"""A second read the project memory answers ends the stage's reading (Initiative BC).

A read of a file the memory holds is answered with a pointer to it, and the stall
rule waited for five results with nothing new before acting: three more full
prefills and replies per stall, 774 pointer answers on one run. The files are in
the conversation already, so the second pointer is the stall.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents import project_memory
from app.agents.settled_answer import (
    POINTERS_BEFORE_THE_ANSWER,
    TOOLS_WITHHELD_NOTICE,
    _STALLED_WITH_WRITERS_NOTICE,
    build_settled_answer_middleware,
)

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
POINTER = f"`docs/a.md` {project_memory.HELD_POINTER}, whole and as it is now. {project_memory.POINTER_ENDS_READING}"


class Answer(BaseModel):
    summary: str


class _Request:
    def __init__(self, messages, tools):
        self.messages, self.tools, self.captured = messages, tools, {}

    def override(self, **changes):
        self.captured.update(changes)
        other = _Request(changes.get("messages", self.messages), changes.get("tools", self.tools))
        other.captured = self.captured
        return other


def _stage(results: list[str]) -> list:
    messages: list = [HumanMessage(content="make the change")]
    for index, result in enumerate(results):
        messages.append(AIMessage(content="", id=f"a{index}", tool_calls=[
            {"name": "read_file", "args": {"file_path": f"docs/{index}.md"}, "id": f"c{index}"}]))
        messages.append(ToolMessage(content=result, tool_call_id=f"c{index}"))
    return messages


def _captured(messages, names):
    request = _Request(messages, [SimpleNamespace(name=n) for n in names])
    build_settled_answer_middleware(Answer, "specialist_backend_0", 120).wrap_model_call(request, lambda r: r)
    return request.captured


def test_two_pointers_in_a_row_leave_a_writer_only_its_writers():
    captured = _captured(_stage(["new bytes"] + [POINTER] * POINTERS_BEFORE_THE_ANSWER),
                         ("read_file", "glob", "edit_artifact"))

    assert [t.name for t in captured["tools"]] == ["edit_artifact"]
    assert _STALLED_WITH_WRITERS_NOTICE in str(captured["messages"][-1])


def test_two_pointers_leave_a_reviewer_only_its_answer():
    captured = _captured(_stage(["new bytes"] + [POINTER] * POINTERS_BEFORE_THE_ANSWER), ("read_file", "glob"))

    assert captured.get("tools") == []
    assert TOOLS_WITHHELD_NOTICE in str(captured["messages"][-1])


def test_one_pointer_is_not_yet_a_stall():
    captured = _captured(_stage(["new bytes", POINTER]), ("read_file", "glob", "edit_artifact"))

    assert "tools" not in captured or [t.name for t in captured["tools"]] != ["edit_artifact"]


def test_the_pointer_says_a_second_one_ends_reading():
    assert POINTERS_BEFORE_THE_ANSWER == 2
    assert not BANNED.search(project_memory.POINTER_ENDS_READING)
