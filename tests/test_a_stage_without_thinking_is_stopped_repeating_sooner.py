"""A stage running without thinking is stopped after three identical calls running.

Measured on one run: 35% of the tool calls made without thinking repeated the
call before them exactly, against 3% with thinking on. One fix stage sent one
refused edit 6 times and one refused `replace_lines` 13 times; two stages read
one file 14 times. Every repeat came after the stage lost a reply to reasoning
and was asked on without it, and the ordinary rungs wait for refusals.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from langchain_core.messages import AIMessage
from pydantic import BaseModel

from app.agents.settled_answer import (
    SAME_CALL_RUNNING_WITHOUT_THINKING,
    _the_same_call_running,
    _the_same_call_running_notice,
    build_settled_answer_middleware,
)

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


class _Tool:
    type = "tool"

    def __init__(self, content: str, call_id: str) -> None:
        self.content, self.tool_call_id = content, call_id


def _call(n: int, args: dict, name: str = "read_file") -> list[object]:
    return [
        SimpleNamespace(type="ai", content="", tool_calls=[{"name": name, "args": args, "id": f"c{n}"}]),
        _Tool("1  const a = 1;", f"c{n}"),
    ]


def _repeats(times: int) -> list[object]:
    return [m for n in range(times) for m in _call(n, {"file_path": "app/main.js", "limit": 50})]


def test_the_threshold_is_three_running() -> None:
    assert _the_same_call_running(_repeats(SAME_CALL_RUNNING_WITHOUT_THINKING)) == ("read_file", 3)
    assert _the_same_call_running(_repeats(SAME_CALL_RUNNING_WITHOUT_THINKING - 1)) is None


def test_a_different_call_between_breaks_the_run() -> None:
    messages = [*_repeats(2), *_call(9, {"file_path": "app/other.js"}), *_call(10, {"file_path": "app/main.js", "limit": 50})]

    assert _the_same_call_running(messages) is None


def test_the_notice_fits_any_product() -> None:
    notice = _the_same_call_running_notice("read_file", 3)
    outside = re.sub(r"`[^`]*`", "", notice).lower()
    for word in BANNED:
        assert not re.search(rf"\b{word}\b", outside), word


class _Answer(BaseModel):
    ok: bool = True


class _Request:
    def __init__(self, messages, tools):
        self.messages, self.tools, self.model, self.model_settings = messages, tools, None, {}

    def override(self, **changes):
        return _Request(changes.get("messages", self.messages), changes.get("tools", self.tools))


def _sent(messages) -> _Request:
    tools = [SimpleNamespace(name="read_file"), SimpleNamespace(name="edit_artifact")]
    sent: list = []
    middleware = build_settled_answer_middleware(_Answer, "defect_fix", step_limit=40)
    middleware.wrap_model_call(_Request(messages, tools), lambda request: sent.append(request))
    return sent[0]


def test_without_thinking_the_tool_is_withheld() -> None:
    lost = AIMessage(content="", response_metadata={"finish_reason": "length"})
    request = _sent([SimpleNamespace(type="human", content="Fix it."), lost, *_repeats(3)])

    assert [tool.name for tool in request.tools] == ["edit_artifact"]
    assert "sent it the same arguments 3 times in a row" in str(request.messages[-1]["content"])


def test_with_thinking_on_the_ordinary_rungs_decide() -> None:
    request = _sent([SimpleNamespace(type="human", content="Fix it."), *_repeats(3)])

    assert [tool.name for tool in request.tools] == ["read_file", "edit_artifact"]
