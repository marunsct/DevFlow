"""Anthropic's address, headers, thinking form and refusals, each as its API takes them."""

from __future__ import annotations

import io
import urllib.error

from app.agents.thinking import ThinkingPolicy
from app.config import load_settings
from app.models import anthropic_client_arguments
from app.models.endpoint_probe import describe_model_endpoint
from app.models.frontier_check import _answers, _request


def test_a_typed_address_lists_models_with_anthropic_s_headers():
    request = _request("anthropic", "https://api.anthropic.com", "k", "wrk")
    assert request.full_url == "https://api.anthropic.com/v1/models"
    assert request.get_header("X-api-key") == "k"
    assert request.get_header("Anthropic-workspace-id") == "wrk"
    assert request.get_header("Authorization") is None


def test_the_client_takes_a_hosted_address_and_the_workspace():
    assert anthropic_client_arguments("https://gateway.example/v1", "wrk") == {
        "anthropic_api_url": "https://gateway.example",
        "default_headers": {"anthropic-workspace-id": "wrk"},
    }


def test_the_local_address_left_in_the_environment_is_not_used():
    assert anthropic_client_arguments("http://host.docker.internal:1234/v1", "") == {}


def test_the_workspace_is_read_from_the_settings():
    assert load_settings({"LLM_PROVIDER": "anthropic", "ANTHROPIC_WORKSPACE_ID": " wrk "}).anthropic_workspace_id == "wrk"


def test_a_current_model_is_never_sent_a_thinking_budget():
    policy = ThinkingPolicy.resolve(mode="on", effort="medium", max_output_tokens=40000)
    assert policy.anthropic_arguments("claude-haiku-5-5") == {"thinking": {"type": "adaptive"}}
    assert policy.anthropic_arguments("claude-opus-4-6") == {"thinking": {"type": "adaptive"}}
    assert policy.anthropic_arguments("claude-haiku-4-5-20251001")["thinking"]["type"] == "enabled"
    assert policy.anthropic_arguments("claude-opus-5") == {"thinking": {"type": "adaptive"}}


def _refused(code: int, message: str):
    def opener(request, timeout=0):
        raise urllib.error.HTTPError(request.full_url, code, "no", {}, io.BytesIO(
            ('{"error": {"message": "%s"}}' % message).encode()
        ))

    return opener


def test_the_provider_s_reason_is_passed_on(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _refused(400, "must include the workspace header"))
    assert "must include the workspace header" in _answers(_request("anthropic", "", "k"))


def test_a_refused_key_stops_a_run_before_it_starts(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _refused(400, "must include the workspace header"))
    status = describe_model_endpoint(load_settings({"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "k"}))
    assert not status.reachable
    assert "must include the workspace header" in status.detail
