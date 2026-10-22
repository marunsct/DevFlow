"""Thinking is two settings because the providers make it two request fields.

Measured against this deployment's local `llama-server` (Qwen3.6):

    reasoning_effort: "high"                          -> 200, reasoning_content present
    chat_template_kwargs: {"enable_thinking": true}   -> 200, reasoning_content present
    chat_template_kwargs: {"enable_thinking": false}  -> 200, no reasoning_content

So the chat-template flag is the switch and `reasoning_effort` is the weight;
setting the weight alone leaves the template's own default in force. Anthropic
instead takes one object carrying both, and requires `max_tokens` to exceed the
thinking budget.

Thinking tokens are output tokens. The budget is therefore a share of the reply
ceiling rather than a separate allowance, which is what keeps a high setting
from producing a request the provider rejects.
"""

from __future__ import annotations

import pytest

from app.agents.thinking import (
    EFFORT_FRACTIONS,
    MIN_ANSWER_TOKENS,
    MIN_THINKING_TOKENS,
    ThinkingPolicy,
    normalise_effort,
    thinking_budget_tokens,
)


@pytest.mark.parametrize("given", ["low", "MEDIUM", " high ", "High"])
def test_a_recognised_effort_is_kept(given):
    assert normalise_effort(given) == given.strip().lower()


@pytest.mark.parametrize("given", ["", None, "maximum", "thorough", "5"])
def test_an_unrecognised_effort_falls_back(given):
    assert normalise_effort(given) == "medium"


def test_more_effort_buys_more_tokens():
    budgets = [thinking_budget_tokens(e, 40_000) for e in ("low", "medium", "high")]

    assert budgets == sorted(budgets)
    assert len(set(budgets)) == 3


def test_the_answer_always_keeps_room():
    """A budget that consumed the whole ceiling would leave nothing to reply with."""
    for effort in EFFORT_FRACTIONS:
        budget = thinking_budget_tokens(effort, 8_000)
        assert budget <= 8_000 - MIN_ANSWER_TOKENS


def test_a_ceiling_too_small_to_divide_yields_no_budget():
    assert thinking_budget_tokens("high", MIN_THINKING_TOKENS + MIN_ANSWER_TOKENS - 1) == 0


def test_thinking_is_disabled_when_it_cannot_fit():
    """A zero budget would be a request the provider rejects."""
    policy = ThinkingPolicy.resolve(mode="on", effort="high", max_output_tokens=1_000)

    assert not policy.enabled
    assert policy.budget_tokens == 0
    assert policy.openai_arguments(local=False) == {}


def test_a_local_server_gets_the_chat_template_switch():
    """`reasoning_effort` alone leaves llama.cpp's template default in force."""
    policy = ThinkingPolicy.resolve(mode='on', effort="high", max_output_tokens=31_250)

    arguments = policy.openai_arguments(local=True)

    assert arguments["reasoning_effort"] == "high"
    assert arguments["extra_body"] == {"chat_template_kwargs": {"enable_thinking": True}}


def test_disabling_thinking_tells_a_local_server_explicitly():
    """'off' is a real instruction, not the absence of 'on'."""
    policy = ThinkingPolicy.resolve(mode="off", effort="high", max_output_tokens=31_250)

    assert policy.openai_arguments(local=True) == {
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}
    }


def test_the_default_mode_sends_nothing_at_all():
    """The regression this feature shipped with, pinned.

    One run was the first run after a two-state `enabled: bool` defaulting
    to False shipped. The client began sending `enable_thinking: False`,
    turning off reasoning the server had been launched with. The product
    manager returned its summary as prose instead of the structured response
    and the next stage died on `KeyError: 'product_intake'`.
    """
    policy = ThinkingPolicy.resolve(mode="default", effort="high", max_output_tokens=31_250)

    assert policy.openai_arguments(local=True) == {}
    assert policy.openai_arguments(local=False) == {}
    assert policy.anthropic_arguments() == {}
    assert not policy.enabled


@pytest.mark.parametrize(
    ("given", "expected"),
    [(True, "on"), (False, "default"), ("true", "on"), ("false", "off"),
     ("on", "on"), ("off", "off"), ("", "default"), (None, "default"), ("nonsense", "default")],
)
def test_a_stored_value_of_any_shape_maps_to_a_mode(given, expected):
    from app.agents.thinking import normalise_mode

    assert normalise_mode(given) == expected


def test_a_ceiling_too_small_falls_back_to_the_server_default():
    """Not to 'off' - that would disable reasoning the deployment relies on."""
    policy = ThinkingPolicy.resolve(mode="on", effort="high", max_output_tokens=1_000)

    assert policy.mode == "default"
    assert policy.openai_arguments(local=True) == {}


def test_a_hosted_openai_endpoint_gets_no_chat_template_kwargs():
    """It neither needs the llama.cpp switch nor accepts it."""
    policy = ThinkingPolicy.resolve(mode='on', effort="low", max_output_tokens=31_250)

    assert policy.openai_arguments(local=False) == {"reasoning_effort": "low"}


def test_anthropic_gets_a_token_budget_not_an_effort_word():
    policy = ThinkingPolicy.resolve(mode='on', effort="medium", max_output_tokens=31_250)

    arguments = policy.anthropic_arguments()

    assert arguments["thinking"]["type"] == "enabled"
    assert arguments["thinking"]["budget_tokens"] == policy.budget_tokens
    assert arguments["thinking"]["budget_tokens"] < 31_250, "must leave room for the answer"


def test_anthropic_gets_nothing_when_disabled():
    assert ThinkingPolicy.resolve(
        mode='off', effort="high", max_output_tokens=31_250
    ).anthropic_arguments() == {}


def test_the_description_says_what_was_decided():
    on = ThinkingPolicy.resolve(mode='on', effort="high", max_output_tokens=31_250)
    off = ThinkingPolicy.resolve(mode='off', effort="high", max_output_tokens=31_250)

    assert "high effort" in on.describe()
    assert "off" in off.describe()


# --- settings plumbing ---------------------------------------------------


def test_the_settings_carry_thinking(monkeypatch):
    from app.config import load_settings

    settings = load_settings(
        {"MODEL_THINKING_MODE": "on", "MODEL_THINKING_EFFORT": "high"}
    )

    assert settings.thinking_mode == "on"
    assert settings.thinking_effort == "high"


def test_thinking_defaults_to_leaving_the_server_alone():
    """Adding a setting must not change how an existing deployment behaves."""
    from app.config import load_settings

    settings = load_settings({})

    assert settings.thinking_mode == "default"
    assert settings.thinking_effort == "medium"


def test_both_fields_are_settable_at_runtime():
    from app.server.runtime_settings import SETTABLE_KEYS

    assert SETTABLE_KEYS["thinking_mode"] == "MODEL_THINKING_MODE"
    assert SETTABLE_KEYS["thinking_effort"] == "MODEL_THINKING_EFFORT"


def test_the_api_rejects_an_effort_it_cannot_map():
    from pydantic import ValidationError

    from app.server.settings import SettingsUpdate

    with pytest.raises(ValidationError):
        SettingsUpdate(
            llm_provider="local",
            openai_base_url="http://localhost:1234/v1",
            model_name="m",
            thinking_effort="maximum",
        )


def test_the_local_client_is_built_with_the_switch():
    from app.config import load_settings
    from app.models import build_default_chat_model

    settings = load_settings(
        {
            "MODEL_THINKING_MODE": "on",
            "MODEL_THINKING_EFFORT": "high",
            "OPENAI_BASE_URL": "http://localhost:1234/v1",
        }
    )
    model = build_default_chat_model(settings)

    assert getattr(model, "reasoning_effort", None) == "high"
    assert getattr(model, "extra_body", None) == {
        "chat_template_kwargs": {"enable_thinking": True}
    }
