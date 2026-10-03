"""A self-hosted model server and a hosted API get the requests each understands.

Every OpenAI-compatible address used to count as a llama.cpp server: the
chat-template switch on every call, and no client retry. Fine while every run
used a local model; wrong on the first hosted one, which is the obvious choice
for the judgement model. A judgement model on another provider also inherited
the default model's local address, and provider `openai` with no address called
`localhost:1234`.
"""

from __future__ import annotations

import pytest

from app.config import load_settings
from app.models.endpoints import default_address, is_self_hosted
from app.models.roles import judgement_environment


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:1234/v1",
        "http://127.0.0.1:8080/v1",
        "http://[::1]:8000/v1",
        "http://host.docker.internal:1234/v1",
        "http://192.168.1.20:1234/v1",
        "http://10.0.0.5:8000/v1",
        "http://172.17.0.1:11434/v1",
        "http://100.101.102.103:1234/v1",
        "http://llama:8080/v1",
        "http://gpu-box.local:1234/v1",
        "http://studio.lan:1234/v1",
        "http://workstation.tail1234.ts.net:1234/v1",
    ],
)
def test_a_server_on_this_machine_or_network_is_self_hosted(url: str) -> None:
    assert is_self_hosted(url, environment={})


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1",
        "https://openrouter.ai/api/v1",
        "https://api.deepseek.com/v1",
        "https://api.groq.com/openai/v1",
        "https://8.8.8.8/v1",
        "",
        "not a url",
    ],
)
def test_anything_else_is_a_hosted_api(url: str) -> None:
    assert not is_self_hosted(url, environment={})


def test_the_operator_can_say_which_it_is() -> None:
    assert is_self_hosted("https://models.example.com/v1", environment={"OPENAI_ENDPOINT_KIND": "self-hosted"})
    assert not is_self_hosted("http://localhost:1234/v1", environment={"OPENAI_ENDPOINT_KIND": "hosted"})


def test_a_provider_without_an_address_is_reached_at_its_own() -> None:
    assert load_settings({"LLM_PROVIDER": "openai"}).openai_base_url == "https://api.openai.com/v1"
    assert load_settings({"LLM_PROVIDER": "local"}).openai_base_url == "http://localhost:1234/v1"
    assert load_settings({"LLM_PROVIDER": "openai", "OPENAI_BASE_URL": "https://openrouter.ai/api/v1"}).openai_base_url == (
        "https://openrouter.ai/api/v1"
    )
    assert default_address("anthropic") == ""


DEFAULT = {"LLM_PROVIDER": "local", "OPENAI_BASE_URL": "http://host.docker.internal:1234/v1", "OPENAI_MODEL": "small"}


def test_a_judgement_model_on_another_provider_does_not_inherit_the_local_address() -> None:
    built = judgement_environment({**DEFAULT, "JUDGEMENT_MODEL": "big", "JUDGEMENT_PROVIDER": "openai"})
    assert "OPENAI_BASE_URL" not in built
    assert load_settings(built).openai_base_url == "https://api.openai.com/v1"


def test_a_judgement_model_on_the_same_server_or_its_own_address_keeps_it() -> None:
    same = judgement_environment({**DEFAULT, "JUDGEMENT_MODEL": "big"})
    assert same["OPENAI_BASE_URL"] == DEFAULT["OPENAI_BASE_URL"]
    same_provider = judgement_environment({**DEFAULT, "JUDGEMENT_MODEL": "big", "JUDGEMENT_PROVIDER": "local"})
    assert same_provider["OPENAI_BASE_URL"] == DEFAULT["OPENAI_BASE_URL"]
    own = judgement_environment({
        **DEFAULT, "JUDGEMENT_MODEL": "big", "JUDGEMENT_PROVIDER": "openai",
        "JUDGEMENT_BASE_URL": "https://openrouter.ai/api/v1",
    })
    assert own["OPENAI_BASE_URL"] == "https://openrouter.ai/api/v1"


def _client(url: str, monkeypatch):
    from app.models import build_default_chat_model

    monkeypatch.delenv("OPENAI_ENDPOINT_KIND", raising=False)
    return build_default_chat_model(load_settings({
        "LLM_PROVIDER": "openai", "OPENAI_BASE_URL": url, "OPENAI_API_KEY": "sk-test", "OPENAI_MODEL": "m",
        "MODEL_THINKING_MODE": "on", "MODEL_THINKING_EFFORT": "high",
    }))


def test_a_hosted_client_gets_retries_and_no_template_switch(monkeypatch) -> None:
    model = _client("https://openrouter.ai/api/v1", monkeypatch)
    assert model.max_retries == 3
    assert "chat_template_kwargs" not in (getattr(model, "extra_body", None) or {})
    assert getattr(model, "reasoning_effort", None) == "high"


def test_a_self_hosted_client_keeps_the_switch_and_its_own_retry(monkeypatch) -> None:
    model = _client("http://192.168.1.20:1234/v1", monkeypatch)
    assert model.max_retries == 0
    assert model.extra_body == {"chat_template_kwargs": {"enable_thinking": True}}


def test_the_answer_only_switch_sends_a_hosted_api_no_template_flag(monkeypatch) -> None:
    from app.agents import thinking

    monkeypatch.setattr(thinking, "least_reasoning_effort", lambda model: "low")
    hosted = thinking.answering_without_reasoning(_client("https://openrouter.ai/api/v1", monkeypatch))
    assert hosted == {"extra_body": {"reasoning_effort": "low"}}
    local = thinking.answering_without_reasoning(_client("http://localhost:1234/v1", monkeypatch))
    assert local["extra_body"]["chat_template_kwargs"] == {"enable_thinking": False}
