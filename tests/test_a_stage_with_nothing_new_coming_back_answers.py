"""A stage whose last tool calls all gave it nothing new is left only the answer.

One run's architect on a local model began twenty replies with "I have
everything I need; I'll write the specification now" and each time called
`glob` or `ls` for a file it had already read, for 20 minutes.
"""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents.settled_answer import (
    IDENTICAL_ANSWERS_BEFORE_WITHHOLDING_THE_TOOL,
    NOTHING_NEW_BEFORE_THE_ANSWER,
    WITHHELD_CALLS_BEFORE_THE_ANSWER,
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


def _captured(messages, tools=None):
    request = _Request(messages, tools)
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
    captured = _captured(_stage([SAME] * IDENTICAL_ANSWERS_BEFORE_WITHHOLDING_THE_TOOL, tools=("glob",)))

    assert captured.get("tools") != []


def test_a_withheld_tool_called_again_and_again_leaves_only_the_answer():
    """A 1-bit build model sent one withheld query 23 more times; each call still ran."""
    again = IDENTICAL_ANSWERS_BEFORE_WITHHOLDING_THE_TOOL + WITHHELD_CALLS_BEFORE_THE_ANSWER
    looking = [SimpleNamespace(name=name) for name in ("glob", "ls", "read_file", "changed_since_sprint")]
    captured = _captured(_stage([SAME] * again, tools=("glob",)), looking)

    assert captured.get("tools") == []
    assert TOOLS_WITHHELD_NOTICE in str(captured["messages"][-1])
    assert "`glob`" in str(captured["messages"][-1])


def test_a_stage_that_also_writes_keeps_only_its_writers():
    again = IDENTICAL_ANSWERS_BEFORE_WITHHOLDING_THE_TOOL + WITHHELD_CALLS_BEFORE_THE_ANSWER
    tools = [SimpleNamespace(name=name) for name in ("glob", "read_file", "edit_artifact")]
    captured = _captured(_stage([SAME] * again, tools=("glob",)), tools)

    assert [tool.name for tool in captured["tools"]] == ["edit_artifact"]


def test_one_call_of_a_withheld_tool_is_not_yet_the_end():
    captured = _captured(_stage([SAME] * (IDENTICAL_ANSWERS_BEFORE_WITHHOLDING_THE_TOOL + 1), tools=("glob",)))

    assert captured.get("tools") != []


def test_invalid_tool_errors_repeated_leave_only_the_answer():
    """An unoffered tool returning 'is not a valid tool' yields nothing new; five in a row leaves only the answer."""
    invalid1 = "Error: edit_file is not a valid tool, try one of [glob, ls, read_file]."
    invalid2 = "Error: SearchReplace is not a valid tool, try one of [glob, ls, read_file]."
    results = [NEW] + [invalid1 if i % 2 == 0 else invalid2 for i in range(NOTHING_NEW_BEFORE_THE_ANSWER)]
    captured = _captured(_stage(results, tools=("edit_file", "SearchReplace")))

    assert captured.get("tools") == []
    assert TOOLS_WITHHELD_NOTICE in str(captured["messages"][-1])


