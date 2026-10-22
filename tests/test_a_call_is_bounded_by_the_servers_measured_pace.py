"""A call may take only what the server's measured pace says a real reply needs.

The configured request timeout has to allow for the slowest model a deployment
might run. On a fast server that let one wedged call hold a run for many times
what any real reply needed: every reply came at 54-188 tokens a second, the
25,000-token cap needed about five minutes, and one call sat open for sixteen.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from app import models
from app.models import (
    MIN_REQUEST_TIMEOUT_SECONDS,
    CompatibleChatOpenAI,
    paced_timeout,
    record_pace,
)

SERVER = ("http://localhost:1/v1", "m")


@pytest.fixture(autouse=True)
def no_measurements(monkeypatch):
    monkeypatch.setattr(models, "_PACE", {})


def test_an_unmeasured_server_keeps_the_configured_limit() -> None:
    assert paced_timeout(SERVER, 25_000, 1800.0) is None
    record_pace(SERVER, 8_000, 100.0)
    assert paced_timeout(SERVER, 25_000, 1800.0) is None


def test_a_measured_server_bounds_the_call_by_its_slowest_pace() -> None:
    record_pace(SERVER, 8_000, 100.0)  # 80 tokens a second
    record_pace(SERVER, 5_000, 100.0)  # 50 tokens a second

    assert paced_timeout(SERVER, 25_000, 1800.0) == pytest.approx(2 * 25_000 / 50)


def test_the_bound_never_falls_below_the_floor_or_rises_above_the_setting() -> None:
    record_pace(SERVER, 20_000, 10.0)
    record_pace(SERVER, 20_000, 10.0)
    assert paced_timeout(SERVER, 2_000, 1800.0) == MIN_REQUEST_TIMEOUT_SECONDS

    record_pace(SERVER, 1_000, 100.0)
    record_pace(SERVER, 1_000, 100.0)
    assert paced_timeout(SERVER, 25_000, 1800.0) == 1800.0


def test_a_short_reply_does_not_count_as_a_measurement() -> None:
    record_pace(SERVER, 50, 5.0)
    record_pace(SERVER, 900, 30.0)
    assert paced_timeout(SERVER, 25_000, 1800.0) is None


def test_each_server_is_measured_on_its_own() -> None:
    record_pace(SERVER, 8_000, 100.0)
    record_pace(SERVER, 8_000, 100.0)
    assert paced_timeout(("http://elsewhere/v1", "m"), 25_000, 1800.0) is None


def test_the_request_carries_the_bound_once_the_server_is_measured(monkeypatch) -> None:
    model = CompatibleChatOpenAI(
        model="m", api_key="k", base_url=SERVER[0], max_retries=0, max_tokens=25_000, timeout=1800.0
    )
    timeouts: list = []

    def generate(self, messages, stop=None, run_manager=None, **kwargs):
        timeouts.append(self._get_request_payload(messages).get("timeout"))
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage("done"))],
            llm_output={"token_usage": {"completion_tokens": 8_000}},
        )

    clock = iter([0.0, 100.0, 200.0, 300.0, 400.0, 500.0])
    monkeypatch.setattr(models.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(ChatOpenAI, "_generate", generate)

    for _ in range(3):
        model._generate([HumanMessage("plan")])

    assert timeouts == [None, None, pytest.approx(2 * 25_000 / 80)]
    assert "timeout" not in model._get_request_payload([HumanMessage("x")])


def test_a_call_cut_off_by_the_bound_is_asked_for_again_at_half(monkeypatch) -> None:
    record_pace(SERVER, 8_000, 100.0)
    record_pace(SERVER, 8_000, 100.0)
    monkeypatch.setattr(models.time, "sleep", lambda seconds: None)
    model = CompatibleChatOpenAI(
        model="m", api_key="k", base_url=SERVER[0], max_retries=0, max_tokens=25_000, timeout=1800.0
    )

    class APITimeoutError(Exception):
        pass

    sent: list = []

    def generate(self, messages, stop=None, run_manager=None, **kwargs):
        payload = self._get_request_payload(messages)
        sent.append((payload.get("max_completion_tokens") or payload.get("max_tokens"), payload.get("timeout")))
        if len(sent) == 1:
            raise APITimeoutError()
        return ChatResult(generations=[ChatGeneration(message=AIMessage("done"))])

    clock = iter([0.0, 625.0, 625.0, 700.0])
    monkeypatch.setattr(models.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(ChatOpenAI, "_generate", generate)

    assert model._generate([HumanMessage("plan")]).generations[0].message.content == "done"
    assert sent == [(25_000, pytest.approx(625.0)), (12_500, pytest.approx(312.5))]
