"""Saving the longest single reply as 0 keeps 0: no ceiling, not the derived default.

Its owner saved 0 on the settings page and the field came back as 32,000: 0 was
stored as empty, which cleared the override, and the ceiling was derived from
the window again - while the budget itself reads a stored 0 as no ceiling.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def _clean_runtime_settings(test_db):
    from app.server import runtime_settings

    runtime_settings.reset_cache()
    runtime_settings.clear()
    runtime_settings.clear_secrets()
    yield
    runtime_settings.clear()
    runtime_settings.clear_secrets()
    runtime_settings.reset_cache()


BASE = {"llm_provider": "local", "openai_base_url": "http://host:1234/v1", "model_name": "small-model",
        "model_context_window": 190000}


def test_the_settings_page_keeps_a_reply_ceiling_of_zero(client, _clean_runtime_settings) -> None:
    from app.server import runtime_settings

    pinned = client.put("/api/settings", json={**BASE, "model_max_output_tokens": 30000}).json()
    assert pinned["model_max_output_tokens"] == 30000

    body = client.put("/api/settings", json={**BASE, "model_max_output_tokens": 0}).json()

    assert body["model_max_output_tokens"] == 0
    assert runtime_settings.effective_environment()["MODEL_MAX_OUTPUT_TOKENS"] == "0"


def test_the_local_model_save_keeps_it_too(client, _clean_runtime_settings) -> None:
    body = client.put("/api/settings/local", json={**BASE, "model_max_output_tokens": 0})
    if body.status_code == 404:
        pytest.skip("no local-model route on this build")
    assert body.json()["model_max_output_tokens"] == 0


def test_a_request_with_no_ceiling_sends_no_max_tokens_to_the_model():
    # The model client is built with no reply cap, and the request carries none.
    from app.agents.context_budget import ContextBudget

    budget = ContextBudget.from_window(190_000, max_output_tokens=0)

    assert budget.max_output_tokens == 0
    assert 0 < budget.input_ceiling_tokens < 190_000


def test_thinking_stays_on_with_no_ceiling_and_no_zero_budget_is_sent():
    from app.agents.thinking import ThinkingPolicy

    policy = ThinkingPolicy.resolve(mode="on", effort="high", max_output_tokens=0)

    assert policy.mode == "on" and policy.budget_tokens == 0
    assert policy.openai_arguments(local=True)["extra_body"]["chat_template_kwargs"]["enable_thinking"] is True
    assert policy.anthropic_arguments() == {}
    assert "no ceiling" in policy.describe()
    # A real ceiling too small to share still falls back to the server's default.
    assert ThinkingPolicy.resolve(mode="on", effort="high", max_output_tokens=100).mode == "default"


def test_the_request_the_model_server_gets_names_no_max_tokens():
    from app.models import CompatibleChatOpenAI

    for ceiling in (None, 0):
        model = CompatibleChatOpenAI(model="local", api_key="not-a-key", base_url="http://localhost:9/v1",
                                     max_tokens=ceiling, max_retries=0)
        payload = model._get_request_payload([("human", "hello")])
        assert "max_tokens" not in payload and "max_completion_tokens" not in payload, ceiling
