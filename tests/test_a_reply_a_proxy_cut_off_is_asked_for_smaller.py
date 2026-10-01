"""After a proxy cuts a slow reply off, the next attempt asks for less.

One run's model server sat behind a proxy that allowed a reply twenty minutes.
The technical lead's did not finish in that, the client sent the identical
request again, and again - each one twenty minutes, each one cut off.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from app import models
from app.models import CompatibleChatOpenAI, after_a_failed_call


class _Status(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class APITimeoutError(Exception):
    """Named the way a client's timeout is."""


def test_a_slow_proxy_cut_off_halves_the_reply() -> None:
    assert after_a_failed_call(_Status(502), 1200.0, 20_000, 0) == (1.0, 10_000, 0)
    assert after_a_failed_call(APITimeoutError(), 1800.0, 20_000, 0) == (1.0, 10_000, 0)


def test_it_stops_when_half_would_be_no_answer() -> None:
    assert after_a_failed_call(_Status(502), 1200.0, 3_000, 0) is None


def test_a_failure_that_comes_back_at_once_is_retried_unchanged() -> None:
    wait, cap, count = after_a_failed_call(_Status(500), 0.2, 20_000, 0)

    assert cap is None and count == 1 and wait > 0
    assert after_a_failed_call(_Status(500), 0.2, 20_000, 3) is None


def test_a_refused_request_is_not_retried() -> None:
    assert after_a_failed_call(_Status(400), 0.1, 20_000, 0) is None
    assert after_a_failed_call(_Status(401), 0.1, 20_000, 0) is None


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(models.time, "sleep", lambda seconds: None)
    return CompatibleChatOpenAI(
        model="m", api_key="k", base_url="http://localhost:1/v1", max_retries=0, max_tokens=20_000
    )


def test_the_second_request_carries_the_smaller_cap(model, monkeypatch) -> None:
    caps: list = []
    clock = iter([0.0, 1200.0, 1200.0, 1201.0])
    monkeypatch.setattr(models.time, "monotonic", lambda: next(clock, 2000.0))

    def generate(self, messages, stop=None, run_manager=None, **kwargs):
        caps.append(self._get_request_payload(messages).get("max_completion_tokens")
                    or self._get_request_payload(messages).get("max_tokens"))
        if len(caps) == 1:
            raise _Status(502)
        return ChatResult(generations=[ChatGeneration(message=AIMessage("done"))])

    monkeypatch.setattr(ChatOpenAI, "_generate", generate)

    result = model._generate([HumanMessage("plan")])

    assert result.generations[0].message.content == "done"
    assert caps == [20_000, 10_000]
    assert model._get_request_payload([HumanMessage("x")]).get("max_completion_tokens", 20_000) == 20_000


def test_a_client_with_its_own_retries_is_left_alone(monkeypatch) -> None:
    calls = []

    def generate(self, messages, stop=None, run_manager=None, **kwargs):
        calls.append(1)
        raise _Status(502)

    monkeypatch.setattr(ChatOpenAI, "_generate", generate)
    hosted = CompatibleChatOpenAI(model="m", api_key="k", max_retries=3)

    with pytest.raises(_Status):
        hosted._generate([HumanMessage("x")])
    assert len(calls) == 1
