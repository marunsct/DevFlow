"""A stage whose last tool calls all gave it nothing new is left only the answer.

One run's architect on a local model began twenty replies with "I have
everything I need; I'll write the specification now" and each time called
`glob` or `ls` for a file it had already read, for 20 minutes.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents.settled_answer import (
    NOTHING_NEW_BEFORE_THE_ANSWER,
    TOOLS_WITHHELD_NOTICE,
    build_settled_answer_middleware,
)


class Spec(BaseModel):
    product_scope: str


class _Request:
    def __init__(self, messages, tools=None):
        self.messages, self.tools, self.captured = messages, list(tools or ["glob", "ls", "read_file"]), {}

    def override(self, **changes):
        self.captured.update(changes)
        other = _Request(changes.get("messages", self.messages), changes.get("tools", self.tools))
        other.captured = self.captured
        return other


def _stage(results: list[str], tools: tuple[str, ...] = ("glob", "ls", "read_file")) -> list:
    messages: list = [HumanMessage(content="write the specification")]
    for index, result in enumerate(results):
        tool = tools[index % len(tools)]
        messages.append(AIMessage(content="I have everything I need; writing it now.", id=f"a{index}",
                                  tool_calls=[{"name": tool, "args": {"pattern": "docs/*"}, "id": f"c{index}"}]))
        messages.append(ToolMessage(content=result, tool_call_id=f"c{index}"))
    return messages


SAME = "[This `glob` returned exactly what it returned the 3 previous times you ran it in this stage.]"
NEW = "docs/technical_specification.md"


def _captured(messages):
    request = _Request(messages)
    build_settled_answer_middleware(Spec, "principal_architect", 120).wrap_model_call(request, lambda r: r)
    return request.captured


def test_nothing_new_from_the_last_calls_leaves_only_the_answer():
    captured = _captured(_stage([NEW] + [SAME] * NOTHING_NEW_BEFORE_THE_ANSWER))

    assert captured.get("tools") == []
    assert TOOLS_WITHHELD_NOTICE in str(captured["messages"][-1])


def test_a_stage_still_learning_keeps_its_tools():
    captured = _captured(_stage([SAME] * (NOTHING_NEW_BEFORE_THE_ANSWER - 1) + [NEW]))

    assert captured.get("tools") != []


def test_one_tool_repeating_is_left_to_the_repeat_rung():
    captured = _captured(_stage([SAME] * (NOTHING_NEW_BEFORE_THE_ANSWER + 2), tools=("glob",)))

    assert captured.get("tools") != []
