"""Every visit of a stage starts with thinking, whatever earlier visits lost.

The rule this file used to pin - a stage that lost a whole reply to reasoning
on two visits is asked without it from then on, for the rest of the run - was
dropped at the owner's request (2026-10-07). Measured on two runs: with it,
and with thinking kept off for the rest of a visit after one loss, 52% and 29%
of replies went without thinking, and 35% and 22% of the calls they made
repeated the call before exactly, against 3% and 0.4% with thinking on. A loss
now costs one reply without thinking, and two in one visit keep it off for
that visit only (`settled_answer.LOST_REPLIES_BEFORE_THINKING_STAYS_OFF`).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from app.agents import thinking


class _Answer(BaseModel):
    summary: str


class _Request:
    def __init__(self, messages: list, model: Any, tools: list | None = None, settings=None):
        self.messages = messages
        self.model = model
        self.tools = tools if tools is not None else [SimpleNamespace(name="read_file")]
        self.model_settings = settings or {}

    def override(self, **changes: Any) -> "_Request":
        return _Request(
            changes.get("messages", self.messages),
            changes.get("model", self.model),
            changes.get("tools", self.tools),
            changes.get("model_settings", self.model_settings),
        )


def _local_model():
    from app.models import CompatibleChatOpenAI

    return CompatibleChatOpenAI(
        base_url="http://model-server:8888/v1", api_key="k", model="m", max_tokens=10
    )


def _spiral() -> AIMessage:
    return AIMessage(content="", response_metadata={"finish_reason": "length"})


@pytest.fixture(autouse=True)
def _a_server_that_can_switch_thinking_off(monkeypatch):
    monkeypatch.setattr(thinking, "least_reasoning_effort", lambda model: "none")


def _sent(messages: list, stage: str = "a_reviewer") -> _Request:
    from app.agents.settled_answer import build_settled_answer_middleware

    seen: dict[str, _Request] = {}

    def handler(request: _Request) -> Any:
        seen["request"] = request
        return SimpleNamespace(result=[])

    middleware = build_settled_answer_middleware(_Answer, stage, step_limit=40)
    middleware.wrap_model_call(_Request(messages, _local_model()), handler)
    return seen["request"]


def _thinking_is_off(request: _Request) -> bool:
    extra = (request.model_settings or {}).get("extra_body") or {}
    return (extra.get("chat_template_kwargs") or {}).get("enable_thinking") is False


_FIRST_CALL = [HumanMessage(content="Review the specification.")]
_AFTER_A_SPIRAL = [*_FIRST_CALL, _spiral()]


def test_a_stage_that_has_not_spiralled_is_asked_as_configured() -> None:
    assert not _thinking_is_off(_sent(_FIRST_CALL))


def test_a_new_visit_after_visits_that_lost_replies_starts_with_thinking() -> None:
    for _ in range(3):
        _sent(_AFTER_A_SPIRAL)
        _sent([*_AFTER_A_SPIRAL, HumanMessage(content="next"), _spiral()])

    assert not _thinking_is_off(_sent(_FIRST_CALL))


def test_nothing_is_remembered_across_visits() -> None:
    for gone in ("note_a_reply_that_was_all_reasoning", "reasoning_keeps_running_out_for"):
        assert not hasattr(thinking, gone), gone
