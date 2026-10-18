"""A reply lost to reasoning does not end the stage: the model is asked again, with thinking off.

Measured on one run: the sprint planner reasoned through its whole 25,000-token
reply and wrote nothing. A reply with no tool call ended the stage, and the
graph's one nudge asked again with thinking switched off for that reply - it
read three files. With thinking back on, the next reply was lost the same way,
the stage ended again with its nudge spent, thinking was never switched off
for the rest of the visit as the owner asked, and the run failed at 54 minutes.

Now the stage goes straight back to the model after a lost reply, and the call
that asks switches thinking off - for one reply after a first loss, for the
rest of the visit after a second.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents import settled_answer, thinking


class _Plan(BaseModel):
    summary: str


class _Request:
    def __init__(self, messages: list, model: Any):
        self.messages = messages
        self.model = model
        self.tools = [SimpleNamespace(name="read_file")]
        self.model_settings: dict = {}

    def override(self, **changes: Any) -> "_Request":
        copy = _Request(changes.get("messages", self.messages), changes.get("model", self.model))
        copy.tools = changes.get("tools", self.tools)
        copy.model_settings = changes.get("model_settings", self.model_settings)
        return copy


def _model(base_url: str | None = "http://model-server:1234/v1"):
    from app.models import CompatibleChatOpenAI

    return CompatibleChatOpenAI(base_url=base_url, api_key="k", model="m", max_tokens=10)


def _lost() -> AIMessage:
    return AIMessage(content="", response_metadata={"finish_reason": "length"})


@pytest.fixture(autouse=True)
def _a_server_that_can_switch_thinking_off(monkeypatch):
    monkeypatch.setattr(thinking, "least_reasoning_effort", lambda model: "none")


def _after(messages: list, model: Any = None, step_limit: int = 40) -> dict | None:
    """What the stage does after its latest reply, as the agent loop runs it: a call, then the hook."""
    middleware = settled_answer.build_settled_answer_middleware(_Plan, "scrum_master", step_limit=step_limit)
    middleware.wrap_model_call(_Request(messages[:-1], model or _model()), lambda request: SimpleNamespace(result=[]))
    return middleware.after_model({"messages": messages})


_ASKED = [HumanMessage(content="Plan the sprints.")]
_WORKED = [
    AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"file_path": "a.md"}, "id": "c1"}]),
    ToolMessage(content="...", tool_call_id="c1"),
]


def test_a_first_lost_reply_goes_back_to_the_model():
    assert _after([*_ASKED, _lost()]) == {"jump_to": "model"}


def test_a_second_lost_reply_goes_back_to_the_model_too():
    """The run's failure: thinking was back on, the second reply was lost, and the stage ended."""
    assert _after([*_ASKED, _lost(), *_WORKED, _lost()]) == {"jump_to": "model"}


def test_the_call_after_a_second_lost_reply_has_thinking_off_for_the_rest_of_the_visit():
    seen: dict = {}
    middleware = settled_answer.build_settled_answer_middleware(_Plan, "scrum_master", step_limit=40)
    middleware.wrap_model_call(
        _Request([*_ASKED, _lost(), *_WORKED, _lost()], _model()),
        lambda request: seen.setdefault("request", request),
    )

    extra = (seen["request"].model_settings or {}).get("extra_body") or {}
    assert (extra.get("chat_template_kwargs") or {}).get("enable_thinking") is False
    assert "for the rest of this stage" in str(seen["request"].messages[-1])


def test_where_thinking_cannot_be_switched_off_the_stage_ends_as_before():
    """Asking again would lose the reply the same way."""
    assert _after([*_ASKED, _lost()], model=_model(base_url=None)) is None


def test_past_its_model_call_budget_the_stage_ends():
    calls = [*_ASKED, *_WORKED * 3, _lost()]

    decision = _after(calls, step_limit=3)

    assert decision is not None and decision.get("jump_to") == "end"


def test_a_reply_cut_off_while_writing_is_not_a_lost_one():
    """Text that ran out of room is not reasoning that did: it is not asked again."""
    cut = AIMessage(content="Sprint 1: the walking skeleton ...", response_metadata={"finish_reason": "length"})

    assert (_after([*_ASKED, cut]) or {}).get("jump_to") != "model"


def test_the_hook_may_jump_back_to_the_model():
    middleware = settled_answer.build_settled_answer_middleware(_Plan, "scrum_master", step_limit=40)
    allowed = getattr(type(middleware).after_model, "__can_jump_to__", None)

    assert allowed is not None and "model" in allowed


def test_a_second_lost_reply_keeps_thinking_off_though_compaction_took_the_first_from_history():
    """A lead lost five 20,000-token replies in one visit: compaction took each
    lost reply out of the history, so the count never reached two and thinking
    came back on after every one."""
    middleware = settled_answer.build_settled_answer_middleware(_Plan, "technical_lead", step_limit=40)
    first, second = _lost(), _lost()
    first.id, second.id = "lost-1", "lost-2"
    middleware.wrap_model_call(_Request([*_ASKED, first], _model()), lambda request: SimpleNamespace(result=[]))
    middleware.wrap_model_call(_Request([*_ASKED, *_WORKED, second], _model()), lambda request: SimpleNamespace(result=[]))

    seen: dict = {}
    # Compacted: neither lost reply is in the history any more.
    middleware.wrap_model_call(
        _Request([*_ASKED, *_WORKED, *_WORKED], _model()), lambda request: seen.setdefault("request", request)
    )

    extra = (seen["request"].model_settings or {}).get("extra_body") or {}
    assert (extra.get("chat_template_kwargs") or {}).get("enable_thinking") is False


def test_lost_replies_count_across_the_visits_of_one_stage(monkeypatch):
    """A retry starts a new conversation and middleware; one run lost two or more
    20,000-token replies per defect because the count started again each visit."""
    monkeypatch.setattr(settled_answer, "_the_stage_across_visits", lambda: ("run-x", "defect_fix_2_2"))
    monkeypatch.setattr(settled_answer, "_LOST_ACROSS_VISITS", {})
    first, second = _lost(), _lost()
    first.id, second.id = "visit-1-lost", "visit-2-lost"

    one = settled_answer.build_settled_answer_middleware(_Plan, "specialist_backend", step_limit=40)
    one.wrap_model_call(_Request([*_ASKED, first], _model()), lambda request: SimpleNamespace(result=[]))
    two = settled_answer.build_settled_answer_middleware(_Plan, "specialist_backend", step_limit=40)
    two.wrap_model_call(_Request([*_ASKED, second], _model()), lambda request: SimpleNamespace(result=[]))

    seen: dict = {}
    two.wrap_model_call(_Request([*_ASKED, *_WORKED], _model()), lambda request: seen.setdefault("request", request))
    extra = (seen["request"].model_settings or {}).get("extra_body") or {}
    assert (extra.get("chat_template_kwargs") or {}).get("enable_thinking") is False
