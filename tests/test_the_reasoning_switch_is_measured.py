"""The call that must answer asks for the least reasoning this model honours.

Measured on one LM Studio server: a GLM model answered a probe in two tokens
with `reasoning_effort: "none"`, while `openai/gpt-oss-20b` treated "none" as
no instruction and reasoned 384-1,990 tokens on the same question, against
64-70 with "low". The switched-off call after a technical lead's 25,000-token
spiral sent "none" and reasoned another 12,372 tokens.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agents import thinking

#: The real probe, taken at import - before the suite's fixture replaces it.
_REAL_REASONING_SPENT = thinking._reasoning_spent


class _Model:
    def __init__(self, base: str = "http://model-server:1234/v1", name: str = "m") -> None:
        self.openai_api_base = base
        self.model_name = name
        self.extra_body = {"top_k": 20}


def _server(costs: dict[str, Any], asked: list[str] | None = None):
    """A probe whose reply to each effort costs `costs[effort]` tokens; an
    exception in place of a cost is raised instead."""

    def spent(model, effort):
        if asked is not None:
            asked.append(effort)
        cost = costs[effort]
        if isinstance(cost, BaseException):
            raise cost
        return cost

    return spent


class _Refused(Exception):
    status_code = 400


def test_a_model_that_ignores_none_is_sent_low(monkeypatch) -> None:
    monkeypatch.setattr(thinking, "_reasoning_spent", _server({"none": 512, "low": 70}))

    settings = thinking.answering_without_reasoning(_Model())

    assert settings["extra_body"]["reasoning_effort"] == "low"
    assert settings["extra_body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert settings["extra_body"]["top_k"] == 20


def test_a_model_that_honours_none_is_sent_none_after_one_question(monkeypatch) -> None:
    asked: list[str] = []
    monkeypatch.setattr(thinking, "_reasoning_spent", _server({"none": 2, "low": 70}, asked))

    assert thinking.least_reasoning_effort(_Model()) == "none"
    assert asked == ["none"]


def test_it_is_measured_once_per_model(monkeypatch) -> None:
    asked: list[str] = []
    monkeypatch.setattr(thinking, "_reasoning_spent", _server({"none": 512, "low": 70}, asked))

    for _ in range(3):
        thinking.least_reasoning_effort(_Model())
    thinking.least_reasoning_effort(_Model(name="another"))

    assert asked == ["none", "low", "none", "low"]


def test_a_refused_value_is_skipped(monkeypatch) -> None:
    monkeypatch.setattr(thinking, "_reasoning_spent", _server({"none": _Refused(), "low": 70}))

    assert thinking.least_reasoning_effort(_Model()) == "low"


def test_a_server_that_refuses_every_value_is_sent_none_of_them(monkeypatch) -> None:
    monkeypatch.setattr(thinking, "_reasoning_spent", _server({"none": _Refused(), "low": _Refused()}))

    settings = thinking.answering_without_reasoning(_Model())

    assert "reasoning_effort" not in settings["extra_body"]
    assert settings["extra_body"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_a_server_that_did_not_answer_is_measured_again_next_time(monkeypatch) -> None:
    asked: list[str] = []
    monkeypatch.setattr(thinking, "_reasoning_spent", _server({"none": ConnectionError("down"), "low": 70}, asked))

    assert thinking.least_reasoning_effort(_Model()) == "none"
    assert thinking.least_reasoning_effort(_Model()) == "none"
    assert asked == ["none", "none"]


def test_a_reply_without_usage_settles_on_none(monkeypatch) -> None:
    asked: list[str] = []
    monkeypatch.setattr(thinking, "_reasoning_spent", _server({"none": None, "low": 70}, asked))

    assert thinking.least_reasoning_effort(_Model()) == "none"
    assert thinking.least_reasoning_effort(_Model()) == "none"
    assert asked == ["none"]


def test_the_probe_asks_the_model_with_each_value() -> None:
    """The real `_reasoning_spent`, against a model that records what it was sent."""
    real = _REAL_REASONING_SPENT
    sent: list[dict] = []

    class _Recording(_Model):
        def invoke(self, messages, **settings):
            sent.append(settings)
            return type("Reply", (), {"usage_metadata": {"output_tokens": 41}})()

    assert real(_Recording(), "low") == 41
    assert sent[0]["extra_body"]["reasoning_effort"] == "low"
    assert sent[0]["extra_body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert sent[0]["max_tokens"] == thinking._PROBE_REPLY_TOKENS
