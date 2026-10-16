from __future__ import annotations

from types import SimpleNamespace
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents.settled_answer import build_settled_answer_middleware


class Verdict(BaseModel):
    status: str
    reason: str


class _Tool:
    def __init__(self, name: str) -> None:
        self.name = name


class _Request:
    def __init__(self, messages, tools=None):
        self.messages = messages
        self.tools = list(tools or [])
        self.captured: dict = {}

    def override(self, **changes):
        self.captured.update(changes)
        other = _Request(changes.get("messages", self.messages), changes.get("tools", self.tools))
        other.captured = self.captured
        return other


def test_withheld_repeated_writer_is_not_restored_when_looking_tools_withheld():
    """When a writer tool repeats past threshold and ignored is True, the withheld tool
    must NOT be restored back into kept tools by the ignored branch.
    """
    tools = [
        _Tool("read_file"),
        _Tool("grep"),
        _Tool("replace_lines"),
        _Tool("edit_artifact"),
    ]

    messages = [HumanMessage(content="build")]
    # 6 identical refused replace_lines calls
    for i in range(6):
        messages.append(
            AIMessage(
                content="",
                tool_calls=[{"id": f"c{i}", "name": "replace_lines", "args": {"path": "a.js", "content": "x"}}],
            )
        )
        messages.append(
            ToolMessage(
                content="Refusing to change 'a.js': identical syntax error",
                tool_call_id=f"c{i}",
            )
        )
    messages.append(AIMessage(content="retry", id="last"))

    request = _Request(messages, tools=tools)
    middleware = build_settled_answer_middleware(Verdict, "specialist_testing", step_limit=40)
    middleware.wrap_model_call(request, lambda r: r)

    captured_tools = [getattr(t, "name", "") for t in request.captured.get("tools", [])]

    # Looking tools must be withheld
    assert "read_file" not in captured_tools
    assert "grep" not in captured_tools

    # The repeated tool must NOT be in tools!
    assert "replace_lines" not in captured_tools, f"replace_lines was restored: {captured_tools}"
    # Other writers should remain
    assert "edit_artifact" in captured_tools

