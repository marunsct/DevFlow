"""Where the model's server enforces a reasoning budget, a reply always has room to answer (IK.3-IK.5, `REASONING_BUDGET`).

Measured on one llama.cpp server: an architect reply reasoned 32,000 tokens to its cap (7 minutes) and was salvaged
in a second request (3 minutes) for a 10,000-token answer; a helper capped at 2,048 tokens spent 1,833 of them
reasoning, every "thinking off" field the harness sends being one the model's template does not read; and the
settings offered low, medium and high while the template reads minimal (0.1) too.
"""
from __future__ import annotations

import json

import pytest
from langchain_core.messages import HumanMessage

from app.agents import thinking
from app.models import CompatibleChatOpenAI, diagnostics, sampling_modes, server_profile

SELF_HOSTED = "http://model-server:2001/v1"
HOSTED = "https://api.openai.com/v1"
MODEL = "a-reasoning-model.gguf"
ENOUGH = "I have reasoned enough about this. I will give my answer now, from what I have worked out above."


@pytest.fixture(autouse=True)
def _what_a_diagnosis_applies_is_this_test_s(monkeypatch):
    """`diagnostics.apply` keeps what it learnt per server for the process: each test starts with none of it."""
    import importlib

    from app import models
    from app.models import named_answer

    monkeypatch.setattr(models, "_NAMED_CHOICE_BECOMES_REQUIRED", set())
    monkeypatch.setattr(models, "_NO_FORCED_TOOL_WHILE_THINKING", set())
    monkeypatch.setattr(named_answer, "HONOURED", set())
    try:
        reasoning_budget = importlib.import_module("app.models.reasoning_budget")
    except ImportError:  # the code before the budget existed
        return
    monkeypatch.setattr(reasoning_budget, "ENFORCED", set())
    monkeypatch.setattr(reasoning_budget, "OFF_BUDGETS", {})


def _client(base: str = SELF_HOSTED, cap: int = 32_000) -> CompatibleChatOpenAI:
    return CompatibleChatOpenAI(model=MODEL, base_url=base, api_key="k", max_retries=0, max_tokens=cap,
                                reasoning_effort="medium", extra_body={"chat_template_kwargs": {"enable_thinking": True}})


class _Server:
    """A model server answering the diagnosis's reasoning and budget questions: 900 tokens as served, held to a
    budget where it enforces one; a zero budget answers right or wrong; the template's thinking switch read or not."""

    def __init__(self, *, budget: bool, zero_answers: bool, template_switch: bool):
        self.budget, self.zero_answers, self.template_switch = budget, zero_answers, template_switch

    def create(self, **payload):
        extra = payload.get("extra_body") or {}
        asked = payload["messages"][-1]["content"]
        right = "330" if "from 1 to 50" in asked else "1902" if "from 1 to 200" in asked else "18"
        # The longer budget question reasons past the moderate budget, so a reply held to it shows it usable (DX.4).
        tokens = 1_900 if "from 1 to 200" in asked else 900
        answer, reasoning = right, "x" * 4 * tokens
        if self.budget and "reasoning_budget_tokens" in extra:
            budget = extra["reasoning_budget_tokens"]
            # As llama.cpp's budget sampler: the reasoning ends at the budget with the request's words for it.
            tokens, reasoning = budget + 20, "x" * 4 * budget + extra.get("reasoning_budget_message", "")
            answer = right if budget or self.zero_answers else "27"
        elif self.template_switch and (extra.get("chat_template_kwargs") or {}).get("enable_thinking") is False:
            tokens = 30
        return {"choices": [{"finish_reason": "stop", "message": {"content": answer, "reasoning_content": reasoning}}],
                "usage": {"completion_tokens": tokens}}


def _diagnosed(client, *, budget: bool = True, zero_answers: bool = True, template_switch: bool = False) -> None:
    """`client`'s server diagnosed as `_Server` answers, and the diagnosis applied."""
    from types import SimpleNamespace

    server = _Server(budget=budget, zero_answers=zero_answers, template_switch=template_switch)
    model = SimpleNamespace(model_name=MODEL, openai_api_base=client.openai_api_base,
                            root_client=SimpleNamespace(chat=SimpleNamespace(completions=server)))
    diagnostics.apply(client, diagnostics.diagnose(model, MODEL))


def _payload(client) -> dict:
    return client._get_request_payload([HumanMessage(content="write the specification")])


@pytest.fixture
def budget_on(monkeypatch):
    monkeypatch.setenv("REASONING_BUDGET", "on")


def test_a_stage_call_is_held_to_its_cap_less_the_room_its_answer_needs(budget_on):
    client = _client()
    _diagnosed(client)

    extra = _payload(client)["extra_body"]

    assert extra["reasoning_budget_tokens"] == 20_000
    assert extra["reasoning_budget_message"] == ENOUGH


def test_a_hosted_api_is_sent_no_budget(budget_on):
    client = _client(HOSTED)
    _diagnosed(client)

    assert "reasoning_budget_tokens" not in (_payload(client).get("extra_body") or {})


def test_with_the_switch_off_no_budget_is_sent(monkeypatch):
    monkeypatch.setenv("REASONING_BUDGET", "off")
    client = _client()
    _diagnosed(client)

    assert "reasoning_budget_tokens" not in (_payload(client).get("extra_body") or {})


def test_a_server_that_does_not_enforce_a_budget_is_sent_none(budget_on):
    client = _client()
    _diagnosed(client, budget=False)

    assert "reasoning_budget_tokens" not in (_payload(client).get("extra_body") or {})


def test_thinking_off_for_a_model_with_no_switch_is_a_zero_budget_and_counts_as_off(budget_on):
    client = _client(cap=2_048)
    _diagnosed(client)

    payload = _payload(thinking.without_reasoning(client))

    assert payload["extra_body"]["reasoning_budget_tokens"] == 0
    assert sampling_modes.thinking_is_off(payload)


def test_a_zero_budget_that_did_not_answer_is_a_small_one(budget_on):
    client = _client(cap=2_048)
    _diagnosed(client, zero_answers=False)

    assert thinking.answering_without_reasoning(client)["extra_body"]["reasoning_budget_tokens"] == 256


def test_a_model_whose_template_switch_works_keeps_that_switch_alone(budget_on):
    client = _client(cap=2_048)
    _diagnosed(client, template_switch=True)

    assert "reasoning_budget_tokens" not in thinking.answering_without_reasoning(client)["extra_body"]


def test_minimal_effort_reaches_the_request_with_the_switch_on(budget_on):
    policy = thinking.ThinkingPolicy.resolve(mode="on", effort="minimal", max_output_tokens=32_000)

    assert policy.openai_arguments(local=True)["reasoning_effort"] == "minimal"


def test_minimal_effort_is_the_default_with_the_switch_off(monkeypatch):
    monkeypatch.setenv("REASONING_BUDGET", "off")

    assert thinking.normalise_effort("minimal") == "medium"


def test_a_level_the_server_s_template_lists_is_taken(budget_on, monkeypatch):
    props = json.loads(open("tests/captured/llama-cpp-props-one-slot-behind-a-balancer.json").read())
    monkeypatch.setattr(server_profile, "current", lambda: server_profile.from_props(props))

    assert thinking.normalise_effort("max") == "max"
    assert thinking.normalise_effort("xhigh") == "medium"
