"""The two reasoning-cost changes the owner approved on 2026-10-29, each behind its own switch.

Measured on one model over ten runs: the technical lead's replies reached 30,000-46,000 tokens, about five minutes
each; nearly every defect-fix call reasoned its whole 12,000-token reply, was salvaged, and thinking stayed on.
"""
from __future__ import annotations

import inspect

from langchain_core.messages import AIMessage, HumanMessage

import app.models as models
from app.agents import settled_answer
from app.models.reply_salvage import SALVAGED
from app.observability import provenance, transcript


def test_planning_and_review_stages_are_capped_and_the_architect_is_not(monkeypatch):
    monkeypatch.setenv("PLAN_REVIEW_REPLY_CAP", "on")
    for stage in ("technical_lead", "acceptance_review_2", "milestone_review", "advice_review_backend", "acceptance_dispute"):
        monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback, s=stage: s)
        assert models.plan_review_reply_cap(None) == models.PLAN_REVIEW_REPLY_TOKENS == 20_000
    assert models.plan_review_reply_cap(12_000) == 12_000
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: "principal_architect")
    assert models.plan_review_reply_cap(None) is None
    monkeypatch.setenv("PLAN_REVIEW_REPLY_CAP", "off")
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: "technical_lead")
    assert models.plan_review_reply_cap(None) is None


def test_the_call_asks_for_the_plan_review_cap():
    assert "cap = fix_stage_reply_cap(ceiling) or plan_review_reply_cap(ceiling)" in inspect.getsource(
        models.CompatibleChatOpenAI._generate_paced)


def _salvaged(text="calling a tool"):
    return AIMessage(content=text, response_metadata={SALVAGED: "reasoning", "finish_reason": "tool_calls"})


def test_a_fix_stage_s_salvaged_reply_turns_thinking_off_for_the_next(monkeypatch):
    monkeypatch.setenv("SALVAGED_REPLIES_TURN_THINKING_OFF", "on")
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: "defect_fix_1_1")
    after_one = [HumanMessage(content="fix it"), _salvaged()]
    assert settled_answer._thinking_is_off_here(after_one, "specialist_backend") is True
    two_then_plain = [HumanMessage(content="fix it"), _salvaged(), _salvaged(), AIMessage(content="ok")]
    assert settled_answer._thinking_is_off_here(two_then_plain, "specialist_backend") is True
    one_then_plain = [HumanMessage(content="fix it"), _salvaged(), AIMessage(content="ok")]
    assert settled_answer._thinking_is_off_here(one_then_plain, "specialist_backend") is False


def test_other_stages_and_the_switch_off_keep_thinking(monkeypatch):
    monkeypatch.setenv("SALVAGED_REPLIES_TURN_THINKING_OFF", "on")
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: "technical_lead")
    assert settled_answer._thinking_is_off_here([HumanMessage(content="plan"), _salvaged()], "lead") is False
    monkeypatch.setenv("SALVAGED_REPLIES_TURN_THINKING_OFF", "off")
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: "defect_fix_1_1")
    assert settled_answer._thinking_is_off_here([HumanMessage(content="fix"), _salvaged()], "backend") is False


def test_both_switches_are_registered():
    assert {"PLAN_REVIEW_REPLY_CAP", "SALVAGED_REPLIES_TURN_THINKING_OFF"} <= set(provenance.SWITCHES)


class _Request:
    def __init__(self, messages):
        self.messages, self.tools, self.model = messages, [], None

    def override(self, **changes):
        other = _Request(changes.get("messages", self.messages))
        other.tools = changes.get("tools", self.tools)
        return other


class _Response:
    def __init__(self, *messages):
        self.result = list(messages)


def test_salvaged_replies_are_counted_as_they_come_back_not_from_a_compacted_history(monkeypatch):
    """Measured on one run: a fix stage compacted its history to 0-3 messages, the salvaged count read from it never
    reached two, and six more 12,000-token replies reasoned to the cap after the rule had fired once."""
    from pydantic import BaseModel

    class Verdict(BaseModel):
        status: str = ""

    monkeypatch.setenv("SALVAGED_REPLIES_TURN_THINKING_OFF", "on")
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: "defect_fix_1_6")
    asked: list[tuple[int, bool]] = []
    real = settled_answer._without_reasoning_after_a_lost_reply

    def spy(request, stage_name, lost_before=0, salvaged_before=0, last_salvaged=False):
        asked.append((salvaged_before, last_salvaged))
        return real(request, stage_name, lost_before, salvaged_before, last_salvaged)

    monkeypatch.setattr(settled_answer, "_without_reasoning_after_a_lost_reply", spy)
    middleware = settled_answer.build_settled_answer_middleware(Verdict, "specialist_backend", 40)
    compacted = [HumanMessage(content="fix it")]  # the history as compaction leaves it: no reply in it
    replies = [_Response(_salvaged()), _Response(AIMessage(content="read")), _Response(_salvaged()),
               _Response(AIMessage(content="edit"))]
    for response in replies:
        middleware.wrap_model_call(_Request(list(compacted)), lambda request, _r=response: _r)
    middleware.wrap_model_call(_Request(list(compacted)), lambda request: _Response(AIMessage(content="done")))

    assert asked == [(0, False), (1, True), (1, False), (2, True), (2, False)]
    off = [settled_answer._thinking_is_off_here(compacted, "specialist_backend", 0, *seen) for seen in asked]
    assert off == [False, True, False, True, True]  # two salvaged in the stage keep it off from then on
