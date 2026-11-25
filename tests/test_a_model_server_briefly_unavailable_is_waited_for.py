"""A model server that is briefly unavailable is waited for, for a bounded time, not failed on.

Measured: a run failed outright on `OpenAIAPIError: model_unavailable`. The balancer in front of the two model
instances marked both unhealthy while the host swapped models, answered 503 `model_unavailable`, and both answered
again within about three minutes; the client's quick retries were spent in four seconds and the run ended.
"""
from __future__ import annotations

import httpx
import pytest
from langchain_core.messages import HumanMessage

from app import models
from app.models import outage

ANSWER = {"id": "x", "object": "chat.completion", "created": 0, "model": "m",
          "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]}


class _Clock:
    """The process's clock and sleep, at the edge: a sleep moves the clock on and is kept."""

    def __init__(self):
        self.now, self.slept = 0.0, []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    monkeypatch.delenv("MODEL_OUTAGE_WAIT_SECONDS", raising=False)
    made = _Clock()
    monkeypatch.setattr(models.time, "monotonic", made.monotonic)
    monkeypatch.setattr(models.time, "sleep", made.sleep)
    from app.observability.log_context import for_the_run

    with for_the_run("run-a"):
        yield made


def _balancer(unavailable_for: float, clock: _Clock, asked: list):
    """The balancer as measured: 503 with the bare text `model_unavailable` until its instances are back."""
    def serve(request: httpx.Request) -> httpx.Response:
        asked.append(clock.now)
        if clock.now < unavailable_for:
            return httpx.Response(503, text="model_unavailable")
        return httpx.Response(200, json=ANSWER)

    return serve


def _a_model(serve, max_retries=0):
    return models.CompatibleChatOpenAI(model="m", base_url="http://balancer:8888/v1", api_key="k",
                                       max_retries=max_retries,
                                       http_client=httpx.Client(transport=httpx.MockTransport(serve)))


def test_a_balancer_back_within_three_minutes_answers_the_call(clock):
    asked: list = []

    reply = _a_model(_balancer(180.0, clock, asked)).invoke([HumanMessage(content="go")])

    assert reply.content == "ok"
    assert clock.now >= 180.0 and max(clock.slept) <= outage.LONGEST_PAUSE


def test_a_client_with_retries_of_its_own_waits_too(clock):
    asked: list = []

    reply = _a_model(_balancer(120.0, clock, asked), max_retries=2).invoke([HumanMessage(content="go")])

    assert reply.content == "ok"


def test_an_outage_longer_than_the_setting_fails_the_call_as_before(clock, monkeypatch):
    monkeypatch.setenv("MODEL_OUTAGE_WAIT_SECONDS", "120")
    asked: list = []

    with pytest.raises(Exception, match="model_unavailable"):
        _a_model(_balancer(10_000.0, clock, asked)).invoke([HumanMessage(content="go")])

    assert 120.0 <= clock.now <= 120.0 + outage.LONGEST_PAUSE


def test_a_check_made_outside_a_run_is_answered_at_once(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    made = _Clock()
    monkeypatch.setattr(models.time, "monotonic", made.monotonic)
    monkeypatch.setattr(models.time, "sleep", made.sleep)

    with pytest.raises(Exception, match="model_unavailable"):
        _a_model(_balancer(180.0, made, [])).invoke([HumanMessage(content="go")])

    assert made.now < 60.0


def test_a_refused_request_is_not_waited_for(clock):
    asked: list = []

    def refuses(request):
        asked.append(clock.now)
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    with pytest.raises(Exception):
        _a_model(refuses).invoke([HumanMessage(content="go")])

    assert len(asked) == 1 and clock.slept == []


@pytest.mark.parametrize("error, elapsed, expected", [
    (httpx.ConnectError("[Errno 111] Connection refused"), 0.1, True),
    (RuntimeError("no routable endpoints for model qwen"), 0.1, True),
    (type("APITimeoutError", (Exception,), {})("Request timed out."), 1800.0, False),
    (type("Status", (Exception,), {"status_code": 502})("Bad gateway"), 1200.0, False),
    (type("Status", (Exception,), {"status_code": 502})("Bad gateway"), 0.2, True),
    (type("Status", (Exception,), {"status_code": 500})("Internal server error"), 0.2, False),
])
def test_what_counts_as_the_server_not_being_there(error, elapsed, expected):
    assert outage.is_an_outage(error, elapsed) is expected
