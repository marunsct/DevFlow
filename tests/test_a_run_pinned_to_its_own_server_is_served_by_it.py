"""A run pinned to a self-hosted server is served by that server, whatever hosted provider the settings name.

Measured on 2026-11-03: the settings named a hosted provider, and a run pinned to a local server kept that provider
with the local address, so its calls would have gone to the hosted API under its key, asking for the local model.
"""
from __future__ import annotations

import pytest

from app.models.model_pin import snapshot_for

LOCAL = "http://host.docker.internal:8888/v1"


@pytest.mark.parametrize("hosted", ["anthropic", "gemini"])
def test_a_pin_to_a_local_server_is_served_locally(hosted):
    pinned = snapshot_for({"LLM_PROVIDER": hosted, "OPENAI_BASE_URL": "", "OPENAI_MODEL": "a-hosted-model"},
                          LOCAL, "local-model")
    assert pinned["LLM_PROVIDER"] == "local"
    assert pinned["OPENAI_BASE_URL"] == LOCAL and pinned["OPENAI_MODEL"] == "local-model"


def test_a_pin_that_names_no_server_or_a_hosted_one_keeps_the_provider():
    base = {"LLM_PROVIDER": "anthropic", "OPENAI_BASE_URL": "", "OPENAI_MODEL": "a-hosted-model"}
    assert snapshot_for(base, None, "another-hosted-model")["LLM_PROVIDER"] == "anthropic"
    assert snapshot_for(base, "https://gateway.example/v1", None)["LLM_PROVIDER"] == "anthropic"


def test_a_local_provider_stays_local():
    assert snapshot_for({"LLM_PROVIDER": "local"}, LOCAL, None)["LLM_PROVIDER"] == "local"


def test_a_pin_to_another_server_takes_that_server_s_saved_limits_not_the_settings_model_s(monkeypatch):
    from app.models import model_pin

    saved = [{"openai_base_url": LOCAL, "model_name": "local-model", "model_context_window": 182000,
              "model_max_output_tokens": 35000}]
    monkeypatch.setattr("app.server.model_profiles.list_profiles", lambda target=None: saved)
    hosted = {"LLM_PROVIDER": "anthropic", "OPENAI_BASE_URL": "", "OPENAI_MODEL": "a-hosted-model",
              "MODEL_CONTEXT_WINDOW": "662144", "MODEL_MAX_OUTPUT_TOKENS": "50000"}
    pinned = model_pin.snapshot_for(hosted, LOCAL, "local-model")
    assert (pinned["MODEL_CONTEXT_WINDOW"], pinned["MODEL_MAX_OUTPUT_TOKENS"]) == ("182000", "35000")

    unknown = model_pin.snapshot_for(hosted, LOCAL, "a-model-never-saved")
    assert "MODEL_CONTEXT_WINDOW" not in unknown and "MODEL_MAX_OUTPUT_TOKENS" not in unknown


def test_a_pin_to_the_settings_own_model_keeps_its_limits(monkeypatch):
    from app.models import model_pin

    monkeypatch.setattr("app.server.model_profiles.list_profiles", lambda target=None: [])
    same = {"LLM_PROVIDER": "local", "OPENAI_BASE_URL": LOCAL, "OPENAI_MODEL": "m", "MODEL_CONTEXT_WINDOW": "182000"}
    assert model_pin.snapshot_for(same, LOCAL, "m")["MODEL_CONTEXT_WINDOW"] == "182000"
