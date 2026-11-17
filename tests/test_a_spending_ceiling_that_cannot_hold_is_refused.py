"""A run is refused under a spending ceiling its models' prices could not enforce.

The ceiling counts only the calls it can price. Over a hosted model with no
known rate every call goes unpriced, the total stays at zero, and the setting
reads as a hard cap that would never fire.
"""

from __future__ import annotations

from types import SimpleNamespace

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


class _Runs:
    """The run store's rows for one run (no database here): `load` and the status compare-and-set."""

    def __init__(self, status: str) -> None:
        self.record = SimpleNamespace(run_id="run-1", status=status, error="", repo_root="")

    def load(self, run_id):
        return self.record

    def compare_and_set_status(self, run_id, expected, new, **kwargs):
        if self.record.status != expected:
            return False
        self.record.status = new
        return True


@pytest.mark.parametrize("status", ["created", "failed"], ids=["start", "resume"])
def test_start_and_resume_both_check_before_dispatching(monkeypatch, status) -> None:
    import asyncio

    from app.server import redis_client

    monkeypatch.setattr(redis_client, "get_async_redis_client", lambda: SimpleNamespace(get=_nothing_recorded))
    monkeypatch.setenv("MAX_RUN_COST_USD", "5")
    monkeypatch.setattr(runtime_settings, "effective_environment",
                        lambda: {"LLM_PROVIDER": "openai", "OPENAI_MODEL": "some-unlisted-model"})
    runner = object.__new__(WorkflowRunner)
    runner.run_store = _Runs(status)
    queued = []
    monkeypatch.setattr(WorkflowRunner, "_dispatch", lambda self, run_id, **kwargs: queued.append(run_id))
    go = (runner.start_run("run-1", SimpleNamespace(), SimpleNamespace(root_path="/w")) if status == "created"
          else runner.resume_run("run-1"))

    with pytest.raises(RunConflict, match="some-unlisted-model"):
        asyncio.run(go)

    assert (runner.run_store.record.status, queued) == (status, [])


async def _nothing_recorded(key):
    return None
