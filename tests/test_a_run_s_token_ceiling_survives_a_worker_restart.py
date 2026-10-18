"""A run's token and cost ceilings bound the run, not the worker segment (plan item AK).

`_RUN_COSTS` is in one process's memory, so a deploy or an orphan recovery
restarted the total at zero: a run that had spent 60% of `MAX_RUN_TOKENS`
before a restart could spend 100% again after it. The transcript is the
shared copy; a handler built in a fresh process takes what the run spent
before that moment from it, once.
"""
from __future__ import annotations

import pytest

from app.observability import cost_tracker, transcript
from app.observability.cost_tracker import CostTrackingCallbackHandler, forget_run, run_cost
from app.server import runner


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TRANSCRIPTS_ENABLED", "true")
    forget_run("run-ak")
    yield
    forget_run("run-ak")


class _Reply:
    llm_output = {"token_usage": {"prompt_tokens": 400, "completion_tokens": 100, "total_tokens": 500}}
    generations: list = []


def _spend_before_the_restart(calls):
    for _ in range(calls):
        transcript.record(
            "run-ak", "build", "model_response",
            usage={"input_tokens": 400, "output_tokens": 100, "total_tokens": 500},
        )


def test_the_ceiling_counts_what_was_spent_before_the_restart(monkeypatch):
    monkeypatch.setenv("MAX_RUN_TOKENS", "1000")
    _spend_before_the_restart(1)  # 500 tokens: 50%, in a process that is gone

    handler = CostTrackingCallbackHandler("run-ak", provider="local", model="m")
    assert run_cost("run-ak").total_tokens == 500
    assert runner._budget_exceeded("run-ak")[0] is False

    handler.on_llm_end(_Reply())  # 500 more in this process: past the ceiling
    exceeded, total = runner._budget_exceeded("run-ak")

    assert exceeded is True
    assert total.total_tokens == 1000


def test_a_second_handler_in_the_same_process_does_not_count_it_twice():
    _spend_before_the_restart(2)

    CostTrackingCallbackHandler("run-ak", provider="local", model="m")
    CostTrackingCallbackHandler("run-ak", provider="local", model="m")

    assert run_cost("run-ak").total_tokens == 1000
    assert run_cost("run-ak").successful_requests == 2


def test_only_calls_before_the_handler_was_built_are_taken():
    _spend_before_the_restart(1)
    handler = CostTrackingCallbackHandler("run-ak", provider="local", model="m")
    _spend_before_the_restart(1)  # a call this process made: its handler counts it, not the seed

    handler.on_llm_end(_Reply())

    assert run_cost("run-ak").total_tokens == 1000


def test_a_finished_run_can_be_seeded_again_if_it_returns():
    _spend_before_the_restart(1)
    CostTrackingCallbackHandler("run-ak", provider="local", model="m")
    forget_run("run-ak")

    CostTrackingCallbackHandler("run-ak", provider="local", model="m")

    assert run_cost("run-ak").total_tokens == 500
    assert "run-ak" in cost_tracker._SEEDED
