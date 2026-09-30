"""The auxiliary framework lookup cannot hold a stage up.

`app.plugins.middleware` asks the run's model which frameworks the stack
document names, in front of an agent's model call. Its client had no reply
ceiling, no timeout and the server's default reasoning. On one run a reasoning
model reasoned over that request for more than 60,000 tokens, and the
specification stage waited behind it for 20 minutes.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.plugins import middleware as plugin_middleware


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import models

    monkeypatch.setattr(models, "_runtime_settings", lambda: SimpleNamespace(
        model_name="m", openai_api_key="k", openai_base_url="http://local:1234/v1",
    ))


class TestTheClient:
    def test_its_reply_and_its_wait_are_capped(self, configured: None) -> None:
        model = plugin_middleware._extraction_model()

        assert model.max_tokens == plugin_middleware._AUXILIARY_REPLY_TOKENS
        assert model.request_timeout == plugin_middleware._AUXILIARY_TIMEOUT_SECONDS
        assert model.max_retries == 1

    def test_it_asks_for_no_reasoning_both_ways(self, configured: None) -> None:
        extra = plugin_middleware._extraction_model().extra_body

        assert extra["reasoning_effort"] == "none"
        assert extra["chat_template_kwargs"]["enable_thinking"] is False


class _Refused(Exception):
    status_code = 400


class _Model:
    def __init__(self, extra_body: dict | None, refuse_effort: bool) -> None:
        self.extra_body = extra_body
        self.refuse_effort = refuse_effort
        self.sent: list[dict | None] = []

    def invoke(self, messages: list[Any]) -> str:
        self.sent.append(self.extra_body)
        if self.refuse_effort and "reasoning_effort" in (self.extra_body or {}):
            raise _Refused("unknown field")
        return "ok"

    def model_copy(self, update: dict) -> "_Model":
        copy = _Model(update.get("extra_body", self.extra_body), self.refuse_effort)
        copy.sent = self.sent
        return copy


class TestAsking:
    def test_a_server_that_refuses_the_effort_field_is_asked_without_it(self) -> None:
        model = _Model({"reasoning_effort": "none", "chat_template_kwargs": {"enable_thinking": False}}, True)

        assert plugin_middleware._ask(model, []) == "ok"
        assert model.sent[1] == {"chat_template_kwargs": {"enable_thinking": False}}

    def test_any_other_failure_is_raised(self) -> None:
        class _Down(_Model):
            def invoke(self, messages: list[Any]) -> str:
                raise ConnectionError("down")

        with pytest.raises(ConnectionError):
            plugin_middleware._ask(_Down({"reasoning_effort": "none"}, False), [])

    def test_a_model_without_settings_is_asked_once(self) -> None:
        model = _Model(None, False)

        assert plugin_middleware._ask(model, []) == "ok" and len(model.sent) == 1
