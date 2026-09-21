"""Per-run cost accounting, and the ceiling that pauses a run at its spend.

Items 3 and 8 of `docs/harness-hardening-plan-part3.md`. Both existed as ideas
before this file did: the handler was fully written and attached to nothing, and
the ceiling did not exist at all, so a harness wired to spend real money had no
bound on what it could spend.

The acceptance tests the plan asks for are the first two classes here - a run
reports its own cost, and a local model reports none. The rest cover the ways
this kind of accounting reports a number that is not true, which is the failure
mode that matters more than being slightly off: a wrong cost that looks
authoritative is worse than no cost at all.
"""

from __future__ import annotations

import pytest

from app.observability.cost_tracker import (
    PRICES,
    CostTrackingCallbackHandler,
    Price,
    forget_run,
    price_for,
    run_cost,
)


def _response(prompt: int, completion: int, model: str | None = None):
    """An `LLMResult`-shaped object carrying usage the non-streamed way."""

    class _R:
        llm_output = {
            "token_usage": {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": prompt + completion,
            },
            **({"model_name": model} if model else {}),
        }
        generations: list = []

    return _R()


def _streamed_response(prompt: int, completion: int):
    """A streamed `LLMResult`: `llm_output` is None, usage is on the message.

    This shape is the reason the handler reads two places. A handler that reads
    only `llm_output` reports zero tokens for an entire run once the models
    begin streaming, which is what this one did before.
    """

    class _Message:
        usage_metadata = {
            "input_tokens": prompt,
            "output_tokens": completion,
            "total_tokens": prompt + completion,
        }

    class _Generation:
        message = _Message()

    class _R:
        llm_output = None
        generations = [[_Generation()]]

    return _R()


@pytest.fixture(autouse=True)
def _clean_registry():
    """Each test gets an empty registry; totals are module state."""
    yield
    for run_id in ("run-a", "run-b", "run-local", "run-unknown", "run-mixed"):
        forget_run(run_id)


class TestARunReportsItsOwnCost:
    """Plan item 3's first acceptance test."""

    def test_a_priced_model_accumulates_dollars(self):
        handler = CostTrackingCallbackHandler("run-a", provider="openai", model="gpt-4o-mini")
        handler.on_llm_end(_response(1_000_000, 1_000_000))

        total = run_cost("run-a")
        assert total.total_tokens == 2_000_000
        assert total.successful_requests == 1
        # gpt-4o-mini: $0.15 in, $0.60 out per million.
        assert total.usd == pytest.approx(0.75)
        assert total.fully_priced

    def test_two_runs_do_not_share_a_total(self):
        """The defect that made the old handler unable to answer the question.

        It accumulated into instance attributes with no run id, so "what did
        this run cost" had no answer on a worker running more than one.
        """
        a = CostTrackingCallbackHandler("run-a", provider="openai", model="gpt-4o-mini")
        b = CostTrackingCallbackHandler("run-b", provider="openai", model="gpt-4o-mini")
        a.on_llm_end(_response(1_000_000, 0))
        b.on_llm_end(_response(3_000_000, 0))

        assert run_cost("run-a").usd == pytest.approx(0.15)
        assert run_cost("run-b").usd == pytest.approx(0.45)

    def test_a_streamed_response_is_counted(self):
        handler = CostTrackingCallbackHandler("run-a", provider="openai", model="gpt-4o-mini")
        handler.on_llm_end(_streamed_response(1_000_000, 1_000_000))
        assert run_cost("run-a").usd == pytest.approx(0.75)

    def test_a_finished_run_is_forgotten(self):
        """Without this the registry grows for the life of the worker."""
        handler = CostTrackingCallbackHandler("run-a", provider="openai", model="gpt-4o-mini")
        handler.on_llm_end(_response(1_000, 1_000))
        assert run_cost("run-a").successful_requests == 1

        forget_run("run-a")
        assert run_cost("run-a").successful_requests == 0


class TestALocalModelReportsNone:
    """Plan item 3's second acceptance test.

    The old handler charged GPT-4o-mini's rates to every call, including this
    deployment's default local model whose marginal cost is electricity. A
    fabricated dollar figure is not an approximation; it is a wrong number
    presented as a measurement.
    """

    def test_a_local_provider_costs_nothing(self):
        handler = CostTrackingCallbackHandler(
            "run-local", provider="local", model="openai/gpt-oss-20b"
        )
        handler.on_llm_end(_response(5_000_000, 5_000_000))

        total = run_cost("run-local")
        assert total.usd == 0.0
        assert total.total_tokens == 10_000_000, "tokens are still counted"

    def test_a_local_zero_is_a_measurement_not_a_gap(self):
        """$0.00 on a local model is confident, not unknown.

        The distinction is the whole point of `fully_priced`: a local run
        reporting nothing should not carry the same warning as a run whose
        model was missing from the table.
        """
        handler = CostTrackingCallbackHandler(
            "run-local", provider="local", model="openai/gpt-oss-20b"
        )
        handler.on_llm_end(_response(1_000, 1_000))

        total = run_cost("run-local")
        assert total.fully_priced
        assert total.unpriced_requests == 0
        assert total.priced_requests == 1


class TestAnUnknownModelIsNotGuessedAt:
    def test_an_unknown_paid_model_is_unpriced_rather_than_charged(self):
        handler = CostTrackingCallbackHandler(
            "run-unknown", provider="openai", model="some-model-shipped-next-year"
        )
        handler.on_llm_end(_response(1_000_000, 1_000_000))

        total = run_cost("run-unknown")
        assert total.usd == 0.0
        assert not total.fully_priced
        assert total.unpriced_requests == 1
        assert "some-model-shipped-next-year" in total.unpriced_models

    def test_a_partial_total_says_so_in_its_summary(self):
        """`usd` alone would read as "this run was free"."""
        handler = CostTrackingCallbackHandler("run-mixed", provider="openai", model="gpt-4o-mini")
        handler.on_llm_end(_response(1_000_000, 0))
        handler.on_llm_end(_response(1_000_000, 0, model="a-model-with-no-rate"))

        summary = run_cost("run-mixed").summary()
        assert summary["priced_requests"] == 1
        assert summary["unpriced_requests"] == 1
        assert summary["fully_priced"] is False
        assert summary["estimated_cost_usd"] == pytest.approx(0.15)
        assert "prices_as_of" in summary, "a price table with no date cannot be audited"

    def test_the_model_that_answered_is_the_one_priced(self):
        """A fallback route should price as the fallback, not as the primary."""
        handler = CostTrackingCallbackHandler("run-a", provider="openai", model="gpt-4o")
        handler.on_llm_end(_response(1_000_000, 0, model="gpt-4o-mini"))
        # gpt-4o would be $2.50; the model that actually answered is $0.15.
        assert run_cost("run-a").usd == pytest.approx(0.15)


class TestThePriceTable:
    def test_a_dated_model_id_prices_as_its_family(self):
        """Providers append date stamps; a new one must not fall through."""
        assert price_for("anthropic", "claude-haiku-4-5-20251001") == PRICES["claude-haiku-4-5"]

    def test_a_vendor_prefixed_id_is_matched(self):
        assert price_for("openai", "openai/gpt-4o-mini") == PRICES["gpt-4o-mini"]

    def test_the_longest_matching_key_wins(self):
        """Not dict order: `gpt-4.1-mini` must not price as `gpt-4.1`."""
        assert price_for("openai", "gpt-4.1-mini") == PRICES["gpt-4.1-mini"]

    def test_an_unknown_model_has_no_price(self):
        assert price_for("openai", "not-a-real-model") is None

    def test_every_local_provider_alias_is_free(self):
        for provider in ("local", "ollama", "vllm", "LM-Studio"):
            price = price_for(provider, "anything-at-all")
            assert price is not None and price.usd_for(10**6, 10**6) == 0.0

    def test_an_operator_can_correct_a_rate_without_a_release(self, monkeypatch):
        monkeypatch.setenv(
            "MODEL_PRICES_JSON", '{"gpt-4o-mini": {"input": 1.0, "output": 2.0}}'
        )
        assert price_for("openai", "gpt-4o-mini") == Price(1.0, 2.0)

    def test_a_malformed_override_is_ignored_rather_than_raised(self, monkeypatch):
        """A typo in a pricing override must not stop a run from starting."""
        monkeypatch.setenv("MODEL_PRICES_JSON", "{not json at all")
        assert price_for("openai", "gpt-4o-mini") == PRICES["gpt-4o-mini"]


class TestAccountingNeverCostsARunItsModelCall:
    def test_a_malformed_response_is_swallowed(self):
        handler = CostTrackingCallbackHandler("run-a", provider="openai", model="gpt-4o-mini")

        class _Broken:
            @property
            def llm_output(self):
                raise RuntimeError("no usage here")

        handler.on_llm_end(_Broken())  # must not raise
        assert run_cost("run-a").successful_requests == 0

    def test_a_response_with_no_usage_is_still_counted_as_a_call(self):
        """The call happened; only its size is unknown.

        `successful_requests` counts model calls, not model calls that reported
        their size, so this must not undercount. Its cost, though, is unknown
        rather than zero, so it lands as an unpriced request and keeps the total
        from reading as complete.
        """
        handler = CostTrackingCallbackHandler("run-a", provider="openai", model="gpt-4o-mini")

        class _NoUsage:
            llm_output = {}
            generations = []

        handler.on_llm_end(_NoUsage())
        total = run_cost("run-a")
        assert total.successful_requests == 1
        assert total.total_tokens == 0, "it must not invent numbers"


class TestTheCostSurvivesTheProcessBoundary:
    """`_RUN_COSTS` is per-process; the API is a different container.

    Found on 2026-09-21 watching a live run: the worker made the calls and
    `/api/runs/{id}` reported `cost: null`, because the API process has no entry
    for a run it did not execute. The accounting was correct and invisible,
    which is the same shape as the defect item 3 set out to fix.

    The transcript is the shared copy - both containers mount
    `DATA_DIR/transcripts/` - and every `model_response` line already carries
    its `usage`, so it is reduced rather than duplicated into a new store.
    """

    def test_a_transcript_is_reduced_to_a_total(self, tmp_path, monkeypatch):
        from app.observability import transcript as transcript_module
        from app.observability.cost_tracker import cost_from_transcript

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        monkeypatch.setenv("TRANSCRIPTS_ENABLED", "true")
        transcript_module.record(
            "run-x", "product_manager", "model_response",
            usage={"input_tokens": 1_000_000, "output_tokens": 0, "total_tokens": 1_000_000},
        )
        transcript_module.record(
            "run-x", "tools_models", "model_response",
            usage={"input_tokens": 1_000_000, "output_tokens": 0, "total_tokens": 1_000_000},
        )

        total = cost_from_transcript("run-x", "openai", "gpt-4o-mini")
        assert total is not None
        assert total.successful_requests == 2
        assert total.total_tokens == 2_000_000
        assert total.usd == pytest.approx(0.30)

    def test_no_transcript_reports_absent_not_zero(self, tmp_path, monkeypatch):
        from app.observability.cost_tracker import cost_from_transcript

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        assert cost_from_transcript("a-run-with-no-transcript", "openai", "gpt-4o-mini") is None

    def test_a_local_model_reduces_to_a_confident_zero(self, tmp_path, monkeypatch):
        from app.observability import transcript as transcript_module
        from app.observability.cost_tracker import cost_from_transcript

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        monkeypatch.setenv("TRANSCRIPTS_ENABLED", "true")
        transcript_module.record(
            "run-local-t", "product_manager", "model_response",
            usage={"input_tokens": 5_000, "output_tokens": 500, "total_tokens": 5_500},
        )

        total = cost_from_transcript("run-local-t", "local", "openai/gpt-oss-20b")
        assert total is not None
        assert total.usd == 0.0
        assert total.fully_priced, "a local zero is measured, not missing"
        assert total.total_tokens == 5_500

    def test_the_live_registry_wins_when_it_has_the_run(self, tmp_path, monkeypatch):
        """Precision order: the handler knows which model actually answered."""
        from app.server.runs import _cost_summary

        handler = CostTrackingCallbackHandler("run-b", provider="openai", model="gpt-4o-mini")
        handler.on_llm_end(_response(1_000_000, 0))

        monkeypatch.setenv("DATA_DIR", str(tmp_path))  # no transcript here
        summary = _cost_summary("run-b")
        assert summary is not None
        assert summary.estimated_cost_usd == pytest.approx(0.15)
