"""A reasoning budget is measured by where the reasoning stops, on a question that reasons past it (LF.1588).

Measured on one llama.cpp server after the budget was first diagnosed: the small puzzle cost the model 155 output
tokens as served (effort low 118, minimal 167, none 218, template effort minimal 127, template effort none 191,
template thinking off 164), so the effort switches were "not measurable" - and that also skipped the budget check,
though the model's stage replies reason 30,000 tokens and more. At a budget of 64 the reply was 95 tokens (64 of
reasoning, the server's 22-token words for an ended reasoning, the answer) and answered wrong, which the old check
read as "not enforced": a bound and the answer under it were one judgement. At a budget of 0 the reply was 728
tokens, more than unbounded, and wrong - llama.cpp's sampler ends a thinking block at once at 0, so those tokens
were not thinking-block reasoning.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

from app.agents import thinking
from app.models import CompatibleChatOpenAI, diagnostics

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ADDRESS = "http://model-server:2001/v1"
MODEL = "a-reasoning-model.gguf"
ENOUGH = "I have reasoned enough about this. I will give my answer now, from what I have worked out above."
#: The small puzzle's output tokens each way, as measured on the model.
MEASURED = {"as served": 155, "effort low": 118, "effort minimal": 167, "effort none": 218,
            "template effort minimal": 127, "template effort none": 191, "template thinking off": 164}


@pytest.fixture(autouse=True)
def _what_a_diagnosis_applies_is_this_test_s(monkeypatch, tmp_path):
    """`diagnostics.apply` keeps what it learnt per server for the process: each test starts with none of it."""
    from app import models
    from app.models import named_answer, reasoning_budget

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("REASONING_BUDGET", "on")
    monkeypatch.setattr(models, "_NAMED_CHOICE_BECOMES_REQUIRED", set())
    monkeypatch.setattr(models, "_NO_FORCED_TOOL_WHILE_THINKING", set())
    monkeypatch.setattr(named_answer, "HONOURED", set())
    monkeypatch.setattr(reasoning_budget, "ENFORCED", set())
    monkeypatch.setattr(reasoning_budget, "OFF_BUDGETS", {})


def _way(payload) -> str:
    extra = payload.get("extra_body") or {}
    template = extra.get("chat_template_kwargs") or {}
    if "reasoning_effort" in template:
        return f"template effort {template['reasoning_effort']}"
    if template.get("enable_thinking") is False:
        return "template thinking off"
    if payload.get("reasoning_effort"):
        return f"effort {payload['reasoning_effort']}"
    return "as served"


class _Server:
    """A llama.cpp-like server. The small puzzle costs `puzzle` tokens each way (`MEASURED` by default) and is
    answered right. The budget question reasons `reasons` tokens unbounded and is answered right with at least
    `needs` of them; where the server `enforces` a budget, the reasoning ends there with the request's words for it.
    A zero budget's reply is `zero` (tokens written into the answer, right or not) where given."""

    def __init__(self, *, reasons: int, needs: int, enforces: bool = True, puzzle: dict | None = None,
                 zero: tuple[int, bool] | None = None):
        self.reasons, self.needs, self.enforces = reasons, needs, enforces
        self.puzzle = MEASURED if puzzle is None else puzzle
        self.zero = zero
        self.budgets: list[int | None] = []

    def create(self, **payload):
        tools = payload.get("tools") or []
        if tools:
            return _tool_reply([t["function"]["name"] for t in tools], payload.get("tool_choice"))
        if "from 1 to 50" not in payload["messages"][-1]["content"]:
            tokens = self.puzzle.get(_way(payload), self.puzzle["as served"])
            return _reply("x" * 4 * (tokens - 2), "18", tokens)
        extra = payload.get("extra_body") or {}
        budget = extra.get("reasoning_budget_tokens")
        self.budgets.append(budget)
        assert payload["max_tokens"] == 2_048
        if budget is None or not self.enforces or budget >= self.reasons:
            return _reply("x" * 4 * self.reasons, "330", self.reasons + 2)
        message = extra.get("reasoning_budget_message", "")
        if budget == 0 and self.zero is not None:
            written, right = self.zero
            return _reply(message, ("x" * 4 * written) + ("330" if right else "12"), written + 24)
        return _reply("x" * 4 * budget + message, "330" if budget >= self.needs else "312", budget + 24)


def _reply(reasoning: str, content: str, tokens: int) -> dict:
    return {"choices": [{"finish_reason": "stop", "message": {"content": content, "reasoning_content": reasoning}}],
            "usage": {"completion_tokens": tokens}}


def _tool_reply(names: list[str], choice) -> dict:
    def call(name, arguments):
        return {"choices": [{"finish_reason": "tool_calls", "message": {"content": "", "tool_calls": [
            {"function": {"name": name, "arguments": json.dumps(arguments)}}]}}], "usage": {"completion_tokens": 9}}

    if "SpecialistOutput" in names:
        return call("SpecialistOutput", {"changed_files": ["app/routes.py"]})
    if "write_artifact" in names and len(names) == 2:
        return call("write_artifact", {"relative_path": "notes.txt", "content": "This is a final."})
    if "glob" in names:
        return call("read_file", {"file_path": "app/main.py"})
    return call("get_weather", {"city": "Paris"})


def _model(server):
    return SimpleNamespace(model_name=MODEL, openai_api_base=ADDRESS,
                           root_client=SimpleNamespace(chat=SimpleNamespace(completions=server)))


def _stage_budget(diagnosis) -> int | None:
    """The reasoning budget a stage call capped at 32,000 tokens is sent once `diagnosis` is applied."""
    client = CompatibleChatOpenAI(model=MODEL, base_url=ADDRESS, api_key="k", max_retries=0, max_tokens=32_000)
    diagnostics.apply(client, diagnosis)
    payload = client._get_request_payload([HumanMessage(content="write the specification")])
    return (payload.get("extra_body") or {}).get("reasoning_budget_tokens")


def test_a_budget_the_reasoning_stopped_at_is_enforced_though_the_effort_switches_are_not_measurable():
    diagnosis = diagnostics.diagnose(_model(_Server(reasons=900, needs=300)), MODEL)

    assert not diagnosis.settings.reasoning_measurable
    assert diagnosis.settings.reasoning_budget
    assert _stage_budget(diagnosis) == 20_000


def test_a_reply_held_to_64_tokens_that_answered_wrong_still_shows_the_budget_enforced():
    """The measured 95-token reply at 64: reasoning ended there, wrong answer; a reply cut at 1,280 answers right."""
    server = _Server(reasons=1_900, needs=1_000, puzzle={**MEASURED, "as served": 900})

    diagnosis = diagnostics.diagnose(_model(server), MODEL)

    assert diagnosis.reasoning_budget_probe["budget 64"]["answered"] is False
    assert diagnosis.settings.reasoning_budget and diagnosis.settings.reasoning_budget_usable
    assert server.budgets == [None, 64, 0, 1_280]


def test_a_budget_whose_moderate_reply_answers_wrong_is_kept_enforced_and_sends_no_stage_budget():
    server = _Server(reasons=1_900, needs=1_500, puzzle={**MEASURED, "as served": 900})

    diagnosis = diagnostics.diagnose(_model(server), MODEL)

    assert diagnosis.settings.reasoning_budget and not diagnosis.settings.reasoning_budget_usable
    assert _stage_budget(diagnosis) is None
    assert any("answered wrong" in line for line in diagnosis.settings.advice)


def test_a_zero_budget_that_costs_more_than_reasoning_freely_is_not_thinking_off():
    """The measured 728-token zero-budget reply against 155 unbounded: the tokens went into the answer."""
    diagnosis = diagnostics.diagnose(_model(_Server(reasons=153, needs=100, zero=(704, True))), MODEL)
    client = CompatibleChatOpenAI(model=MODEL, base_url=ADDRESS, api_key="k", max_retries=0, max_tokens=2_048)
    diagnostics.apply(client, diagnosis)

    assert not diagnosis.settings.zero_budget_answers
    assert thinking.answering_without_reasoning(client)["extra_body"]["reasoning_budget_tokens"] == 256
    assert any("moved" in line and "728" in line for line in diagnosis.settings.advice)


def test_a_question_that_reasons_under_the_bound_leaves_the_budget_not_measurable_not_unenforced():
    server = _Server(reasons=120, needs=50, enforces=False, puzzle={**MEASURED, "as served": 900})

    diagnosis = diagnostics.diagnose(_model(server), MODEL)

    assert not diagnosis.settings.reasoning_budget
    assert any("budget not measurable" in line for line in diagnosis.settings.advice)
    assert not any("budget is not enforced" in line for line in diagnosis.settings.advice)


def test_a_server_that_lets_the_reasoning_run_past_the_bound_is_asked_no_moderate_budget():
    server = _Server(reasons=1_900, needs=1_000, enforces=False)

    diagnosis = diagnostics.diagnose(_model(server), MODEL)

    assert not diagnosis.settings.reasoning_budget
    assert any("budget is not enforced" in line for line in diagnosis.settings.advice)
    assert server.budgets == [None, 64]


def test_a_budget_kept_before_usable_was_measured_still_holds_a_stage_call(tmp_path):
    """A record kept by the harness before LF.1588 has no `reasoning_budget_usable`: its budget answered at 64."""
    from app.models.registry import merge_into_fitness

    merge_into_fitness(MODEL, {"diagnostics": {"model": MODEL, "measured_at": "2026-11-26T19:11:34+00:00",
                                               "checks": [], "reasoning_tokens": {"as served": 900},
                                               "settings": {"reasoning_budget": True}}})

    assert _stage_budget(diagnostics.recorded(MODEL)) == 20_000


def test_the_budget_question_uses_none_of_the_banned_words():
    assert not BANNED.search(diagnostics._LONG_QUESTION)
