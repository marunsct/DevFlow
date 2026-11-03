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
