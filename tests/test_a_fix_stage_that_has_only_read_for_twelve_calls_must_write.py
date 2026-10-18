"""A fix stage that has read for twelve calls and changed nothing has its looking tools taken away (plan: measured live).

One fix stage made 123 model calls and one edit over 47 minutes, writing "I have
all the information I need" before each further read; another made 118 tool calls
and none. Its change is measured after it returns and a wrong one is undone, so
a best attempt costs less than another reading of the same files.
"""
from __future__ import annotations

import re

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents import settled_answer
from app.agents.settled_answer import CALLS_BEFORE_A_FIX_MUST_WRITE, build_settled_answer_middleware

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


class Verdict(BaseModel):
    status: str
    reason: str


class _Tool:
    def __init__(self, name):
        self.name = name


TOOLS = [_Tool(n) for n in ("read_file", "ls", "grep", "edit_artifact", "write_artifact", "run_terminal_command")]


class _Request:
    def __init__(self, messages, tools=None):
        self.messages = messages
        self.tools = list(TOOLS if tools is None else tools)
        self.captured: dict = {}

    def override(self, **changes):
        self.captured.update(changes)
        other = _Request(changes.get("messages", self.messages), changes.get("tools", self.tools))
        other.captured = self.captured
        return other


def _reads(count, *, write_after=None):
    messages = [HumanMessage(content="fix it")]
    for n in range(count):
        messages.append(AIMessage(content="", id=f"a{n}", tool_calls=[{"name": "read_file", "args": {"file_path": f"f{n}.py"}, "id": f"c{n}"}]))
        messages.append(ToolMessage(content=f"   1  contents of f{n}", tool_call_id=f"c{n}"))
        if write_after is not None and n == write_after:
            messages.append(AIMessage(content="", id=f"w{n}", tool_calls=[{"name": "edit_artifact", "args": {"relative_path": "x.py"}, "id": f"e{n}"}]))
            messages.append(ToolMessage(content='{"status": "edited"}', tool_call_id=f"e{n}"))
    messages.append(AIMessage(content="thinking", id="last"))
    return messages


def _call(messages, monkeypatch, stage="defect_fix_2_14", tools=None):
    monkeypatch.setattr(settled_answer, "_the_graph_stage", lambda role="": stage)
    request = _Request(messages, tools)
    build_settled_answer_middleware(Verdict, "specialist_backend", 40).wrap_model_call(request, lambda r: r)
    return request.captured


def _names(captured):
    return {t.name for t in captured.get("tools", [])}


def test_twelve_calls_without_a_write_take_the_looking_tools_and_say_why(monkeypatch):
    captured = _call(_reads(CALLS_BEFORE_A_FIX_MUST_WRITE), monkeypatch)

    assert _names(captured) == {"edit_artifact", "write_artifact", "run_terminal_command"}
    said = str(captured["messages"][-1])
    assert "changed nothing" in said and "Change the files now" in said
    assert not BANNED.search(said)


def test_fewer_calls_keep_every_tool(monkeypatch):
    assert "tools" not in _call(_reads(CALLS_BEFORE_A_FIX_MUST_WRITE - 1), monkeypatch)


def test_a_write_resets_the_count(monkeypatch):
    assert "tools" not in _call(_reads(CALLS_BEFORE_A_FIX_MUST_WRITE + 2, write_after=CALLS_BEFORE_A_FIX_MUST_WRITE), monkeypatch)


def test_a_stage_that_is_not_a_fix_is_left_alone(monkeypatch):
    assert "tools" not in _call(_reads(CALLS_BEFORE_A_FIX_MUST_WRITE + 5), monkeypatch, stage="specialist_testing_0")


def test_a_fix_stage_with_no_tool_that_writes_is_not_left_with_only_an_answer(monkeypatch):
    looking_only = [_Tool("read_file"), _Tool("ls"), _Tool("grep")]

    assert "tools" not in _call(_reads(CALLS_BEFORE_A_FIX_MUST_WRITE + 5), monkeypatch, tools=looking_only)
