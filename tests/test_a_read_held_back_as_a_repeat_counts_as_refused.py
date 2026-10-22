"""A read whose content is held back as a repeat counts toward taking the read tool away.

Measured live: a fixer read one file fourteen times with the same arguments.
The last eleven came back "This file has given you these same bytes N times
... The content is not repeated here", which held the content back but never
said "Refusing to read" - so the read tool was never withheld, and the stage
ran out of its budget reading.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents.settled_answer import READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL, build_settled_answer_middleware
from app.agents.workspace_backend import READ_WITHHELD_MARKER


class Verdict(BaseModel):
    status: str
    reason: str


class _Tool:
    def __init__(self, name):
        self.name = name


class _Request:
    def __init__(self, messages, tools):
        self.messages = messages
        self.tools = tools
        self.captured: dict = {}

    def override(self, **changes):
        self.captured.update(changes)
        other = _Request(changes.get("messages", self.messages), changes.get("tools", self.tools))
        other.captured = self.captured
        return other


def _held_back(times):
    messages = [HumanMessage(content="fix it")]
    for i in range(times):
        messages.append(AIMessage(content="", id=f"a{i}"))
        messages.append(ToolMessage(
            content=f"[This file {READ_WITHHELD_MARKER} {i + 3} times in this stage and has not "
                    "changed once. The content is not repeated here.]",
            tool_call_id=f"c{i}",
        ))
    messages.append(AIMessage(content="reading again", id="last"))
    return messages


def _kept(messages):
    request = _Request(messages, [_Tool("read_file"), _Tool("grep"), _Tool("write_artifact")])
    build_settled_answer_middleware(Verdict, "defect_fix_1_2", 40).wrap_model_call(request, lambda r: r)
    return {t.name for t in request.captured.get("tools", request.tools)}


def test_reads_held_back_as_repeats_take_the_read_tool_away():
    kept = _kept(_held_back(READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL))

    assert "read_file" not in kept
    assert {"grep", "write_artifact"} <= kept


def test_fewer_than_the_threshold_keep_it():
    assert "read_file" in _kept(_held_back(READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL - 1))


def test_the_backend_s_message_carries_the_marker():
    import inspect

    from app.agents import workspace_backend

    assert "{READ_WITHHELD_MARKER}" in inspect.getsource(workspace_backend)
