"""MAX_RUN_TOKENS bounds every model token a run uses, priced or not (Initiative AH.1).

The dollar ceiling counts priced calls only, so a local model has no bound;
one run used 73 million tokens over twelve hours.
"""

from __future__ import annotations

import pytest

from app.observability.cost_tracker import CostTrackingCallbackHandler, forget_run
from app.server.runner import _budget_exceeded, _max_run_tokens

from tests.test_run_cost_ceiling import _usage


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("MAX_RUN_COST_USD", raising=False)
    yield
    forget_run("token-run")


def _unpriced(tokens: int) -> None:
    CostTrackingCallbackHandler("token-run", provider="openai", model="a-local-model").on_llm_end(_usage(tokens))


def test_an_unpriced_run_past_the_bound_is_paused(monkeypatch) -> None:
    monkeypatch.setenv("MAX_RUN_TOKENS", "1000000")
    _unpriced(1_200_000)

    over, spent = _budget_exceeded("token-run")
    assert over is True and spent.total_tokens == 1_200_000 and spent.usd == 0


def test_under_the_bound_or_without_one_it_continues(monkeypatch) -> None:
    _unpriced(1_200_000)
    assert _budget_exceeded("token-run")[0] is False
    monkeypatch.setenv("MAX_RUN_TOKENS", "5000000")
    assert _budget_exceeded("token-run")[0] is False


def test_a_malformed_bound_is_none(monkeypatch) -> None:
    monkeypatch.setenv("MAX_RUN_TOKENS", "5M")
    assert _max_run_tokens() == 0


def test_the_worker_is_given_the_setting() -> None:
    from pathlib import Path

    assert "MAX_RUN_TOKENS: ${MAX_RUN_TOKENS:-}" in (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text()
