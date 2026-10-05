"""After a reply lost to reasoning, a stage keeps its tools when thinking can be switched off.

Withholding the tools was the remedy from before thinking could be switched off
per call. It forces an answer, and a stage whose work is writing files cannot
do that work by answering. Measured on one run: QA reasoned through its whole
reply before writing a test, the tools were withheld, and the only answer left
was an empty suite marking two criteria "not automatable" - one of them adding
a task - which cost QA a second visit.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from app.agents import settled_answer, thinking


class _Answer(BaseModel):
    summary: str


class _Request:
    def __init__(self, messages: list, model: Any, tools: list | None = None, settings=None):
        self.messages = messages
        self.model = model
        self.tools = tools if tools is not None else [SimpleNamespace(name="write_artifact")]
        self.model_settings = settings or {}

    def override(self, **changes: Any) -> "_Request":
        return _Request(
            changes.get("messages", self.messages),
            changes.get("model", self.model),
            changes.get("tools", self.tools),
            changes.get("model_settings", self.model_settings),
        )


def _model(base_url: str | None = "http://model-server:8888/v1"):
    from app.models import CompatibleChatOpenAI

    return CompatibleChatOpenAI(base_url=base_url, api_key="k", model="m", max_tokens=10)


def _spiral() -> AIMessage:
    return AIMessage(content="", response_metadata={"finish_reason": "length"})


@pytest.fixture(autouse=True)
def _a_run(monkeypatch):
    thinking.forget_the_replies_that_were_all_reasoning()
    monkeypatch.setattr(thinking, "_this_run_and_visit", lambda: ("a-run", "visit-1"))
    monkeypatch.setattr(thinking, "least_reasoning_effort", lambda model: "none")
    yield
    thinking.forget_the_replies_that_were_all_reasoning()


def _sent(messages: list, model=None) -> _Request:
    seen: dict[str, _Request] = {}

    def handler(request: _Request) -> Any:
        seen["request"] = request
        return SimpleNamespace(result=[])

    middleware = settled_answer.build_settled_answer_middleware(_Answer, "acceptance_author", step_limit=40)
    middleware.wrap_model_call(_Request(messages, model or _model()), handler)
    return seen["request"]


def _thinking_is_off(request: _Request) -> bool:
    extra = (request.model_settings or {}).get("extra_body") or {}
    return (extra.get("chat_template_kwargs") or {}).get("enable_thinking") is False


_ASKED = [HumanMessage(content="Write the acceptance suite.")]


def test_the_first_spiral_keeps_the_tools_and_switches_thinking_off() -> None:
    sent = _sent([*_ASKED, _spiral()])

    assert [tool.name for tool in sent.tools] == ["write_artifact"]
    assert _thinking_is_off(sent)
    told = str(sent.messages[-1]["content"])
    assert "Thinking is switched off" in told and "withheld" not in told


def test_a_second_spiral_in_the_same_visit_withholds_them() -> None:
    sent = _sent([*_ASKED, _spiral(), HumanMessage(content="next"), _spiral()])

    assert sent.tools == []
    assert "tools are withheld" in str(sent.messages[-1]["content"])


def test_where_thinking_cannot_be_switched_off_the_tools_are_withheld(monkeypatch) -> None:
    monkeypatch.setattr(thinking, "answering_without_reasoning", lambda model: {})
    sent = _sent([*_ASKED, _spiral()])

    assert sent.tools == []
    assert "tools are withheld" in str(sent.messages[-1]["content"])


def test_the_notice_names_no_product_and_no_control() -> None:
    import re

    text = settled_answer._REASONED_PAST_THE_BUDGET_THINKING_OFF_NOTICE.lower()
    for word in ("task", "to-do", "todo", "button", "click", "checkbox", "page", "test"):
        assert not re.search(rf"\b{word}\b", text), word
