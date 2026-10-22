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
def _a_server_that_can_switch_thinking_off(monkeypatch):
    monkeypatch.setattr(thinking, "least_reasoning_effort", lambda model: "none")


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


def test_a_second_spiral_in_the_same_visit_keeps_the_tools_and_thinking_stays_off() -> None:
    sent = _sent([*_ASKED, _spiral(), HumanMessage(content="next"), _spiral()])

    assert [tool.name for tool in sent.tools] == ["write_artifact"]
    assert _thinking_is_off(sent)
    assert "rest of this stage" in str(sent.messages[-1]["content"])


def test_where_thinking_cannot_be_switched_off_the_tools_are_withheld(monkeypatch) -> None:
    monkeypatch.setattr(thinking, "answering_without_reasoning", lambda model: {})
    sent = _sent([*_ASKED, _spiral()])

    assert sent.tools == []
    assert "tools are withheld" in str(sent.messages[-1]["content"])


def test_the_notice_names_no_product_and_no_control() -> None:
    import re

    for notice in (
        settled_answer._REASONED_PAST_THE_BUDGET_THINKING_OFF_NOTICE,
        settled_answer._REASONED_PAST_THE_BUDGET_AGAIN_NOTICE,
    ):
        text = notice.lower()
        for word in ("task", "to-do", "todo", "button", "click", "checkbox", "page", "test"):
            assert not re.search(rf"\b{word}\b", text), word


def _after(*replies) -> list:
    """`replies` (lost or not), each a tool call answered, as a visit holds them."""
    from langchain_core.messages import ToolMessage

    messages = list(_ASKED)
    for n, reply in enumerate(replies):
        if reply == "lost":
            messages.append(_spiral())
        else:
            messages.append(AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"file_path": f"a{n}"}, "id": f"c{n}"}]))
            messages.append(ToolMessage(content="text", tool_call_id=f"c{n}"))
    return messages


def test_after_one_lost_reply_thinking_is_back_on_the_reply_after() -> None:
    """Off for the one reply that lands the next step; with it kept off for
    the rest of the visit, a stage repeated its own calls ten times as often."""
    later = _sent(_after("lost", "worked"))

    assert not _thinking_is_off(later)
    assert [tool.name for tool in later.tools] == ["write_artifact"]


def test_after_two_lost_replies_it_stays_off_for_the_rest_of_the_visit() -> None:
    """One run's defect fix had thinking back on straight after a loss, lost a
    second reply, and the run failed: a second loss keeps it off."""
    later = _sent(_after("lost", "worked", "lost", "worked", "worked"))

    assert _thinking_is_off(later)
    assert [tool.name for tool in later.tools] == ["write_artifact"]


def test_a_visit_that_lost_nothing_keeps_its_thinking() -> None:
    assert not _thinking_is_off(_sent(list(_ASKED)))


def test_the_notice_and_the_log_say_how_long_thinking_stays_off(caplog) -> None:
    """Each says for how long - an auditor reads the log for the behaviour."""
    import logging

    with caplog.at_level(logging.WARNING, logger=settled_answer.logger.name):
        first = _sent([*_ASKED, _spiral()])
    told = str(first.messages[-1]["content"])
    assert "for this reply" in told and "back on the reply after" in told
    assert any("for the next reply" in r.getMessage() for r in caplog.records)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=settled_answer.logger.name):
        second = _sent(_after("lost", "worked", "lost"))
    assert "rest of this stage" in str(second.messages[-1]["content"])
    assert any("rest of this visit" in r.getMessage() for r in caplog.records)
