"""A run is refused under a spending ceiling its models' prices could not enforce.

The ceiling counts only the calls it can price. Over a hosted model with no
known rate every call goes unpriced, the total stays at zero, and the setting
reads as a hard cap that would never fire.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.server import runtime_settings
from app.server.runner import RunConflict, WorkflowRunner


def _check(monkeypatch, ceiling: str, **environment: str) -> None:
    monkeypatch.setenv("MAX_RUN_COST_USD", ceiling)
    monkeypatch.setattr(runtime_settings, "effective_environment", lambda: environment)
    WorkflowRunner._require_a_ceiling_that_can_hold(object())


def test_a_hosted_model_with_no_price_under_a_ceiling_is_refused(monkeypatch) -> None:
    with pytest.raises(RunConflict, match="some-unlisted-model.*MODEL_PRICES_JSON"):
        _check(monkeypatch, "5", LLM_PROVIDER="openai", OPENAI_MODEL="some-unlisted-model")


def test_an_unpriced_judgement_model_is_refused_too(monkeypatch) -> None:
    with pytest.raises(RunConflict, match="another-unlisted-model"):
        _check(
            monkeypatch, "5", LLM_PROVIDER="local", OPENAI_MODEL="anything",
            JUDGEMENT_MODEL="another-unlisted-model", JUDGEMENT_PROVIDER="openai",
        )


def test_a_local_model_is_priced_at_nothing_and_starts(monkeypatch) -> None:
    _check(monkeypatch, "5", LLM_PROVIDER="local", OPENAI_MODEL="some-unlisted-model")


def test_without_a_ceiling_nothing_is_refused(monkeypatch) -> None:
    _check(monkeypatch, "", LLM_PROVIDER="openai", OPENAI_MODEL="some-unlisted-model")


def test_a_rate_given_in_the_settings_makes_it_priced(monkeypatch) -> None:
    monkeypatch.setenv(
        "MODEL_PRICES_JSON", '{"some-unlisted-model": {"input": 1.0, "output": 2.0}}'
    )
    _check(monkeypatch, "5", LLM_PROVIDER="openai", OPENAI_MODEL="some-unlisted-model")


def test_start_and_resume_both_check_before_dispatching() -> None:
    for method in (WorkflowRunner.start_run, WorkflowRunner.resume_run):
        source = inspect.getsource(method)
        assert source.index("_require_a_ceiling_that_can_hold") < source.index("_dispatch(")


def test_the_dashboard_says_when_the_spend_is_partial() -> None:
    """The run page draws its spend with `RunFigures`, whose words come from `lib/runSummary.ts`."""
    ui = Path(__file__).resolve().parents[1] / "langchain-ui/src"
    assert "<RunFigures run={run} />" in (ui / "pages/RunDashboard.tsx").read_text()
    words = (ui / "lib/runSummary.ts").read_text()
    assert "cost.fully_priced" in words and "unpriced_requests" in words and "not priced" in words
