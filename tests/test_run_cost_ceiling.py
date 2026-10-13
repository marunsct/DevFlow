"""The per-run spending ceiling: item 8 of Part III of the hardening plan (`docs/harness-improvement-plan.md`).

The plan's framing is the thing to preserve here. Every other resource in this
system is bounded - memory, CPU, PIDs, gates, supersteps, context - and token
spend was not, on a harness whose compose file wires real provider credentials
through to the worker.

The acceptance test is "a run pauses rather than continuing past the ceiling",
and the word that carries the weight is *pauses*. A run that reaches its ceiling
has not done anything wrong: its work is good and the operator may simply want
to raise the number. Failing it would throw that work away to enforce a budget,
which is the opposite of what a budget is for.
"""

from __future__ import annotations

import pytest

from app.observability.cost_tracker import CostTrackingCallbackHandler, forget_run, run_cost
from app.server.runner import (
    BUDGET_PAUSE_STATUS,
    CANCELLABLE_WHILE_PARKED,
    _budget_exceeded,
    _max_run_cost_usd,
)


def _spend(run_id: str, dollars: float) -> None:
    """Put a known dollar figure on a run's total via the real handler.

    Through the handler rather than by writing the registry directly, so the
    arithmetic under test is the arithmetic that runs in production.
    """
    handler = CostTrackingCallbackHandler(run_id, provider="openai", model="gpt-4o-mini")
    # gpt-4o-mini input is $0.15/Mtok, so this many prompt tokens is `dollars`.
    handler.on_llm_end(_usage(int(dollars / 0.15 * 1_000_000)))


def _usage(prompt_tokens: int):
    class _R:
        llm_output = {
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 0,
                "total_tokens": prompt_tokens,
            }
        }
        generations: list = []

    return _R()


@pytest.fixture(autouse=True)
def _clean():
    yield
    for run_id in ("ceiling-run", "free-run"):
        forget_run(run_id)


class TestTheCeilingIsOffByDefault:
    def test_no_setting_means_no_ceiling(self, monkeypatch):
        """A local deployment spends nothing; a ceiling firing on it is noise."""
        monkeypatch.delenv("MAX_RUN_COST_USD", raising=False)
        assert _max_run_cost_usd() == 0.0

        _spend("free-run", 500.0)
        over, _ = _budget_exceeded("free-run")
        assert over is False

    def test_zero_disables_it(self, monkeypatch):
        monkeypatch.setenv("MAX_RUN_COST_USD", "0")
        _spend("free-run", 500.0)
        assert _budget_exceeded("free-run")[0] is False

    def test_a_malformed_value_disables_it_rather_than_killing_the_run(self, monkeypatch):
        monkeypatch.setenv("MAX_RUN_COST_USD", "ten dollars")
        assert _max_run_cost_usd() == 0.0


class TestARunPausesRatherThanContinuing:
    """The plan's acceptance test."""

    def test_under_the_ceiling_the_run_continues(self, monkeypatch):
        monkeypatch.setenv("MAX_RUN_COST_USD", "10.00")
        _spend("ceiling-run", 9.0)
        assert _budget_exceeded("ceiling-run")[0] is False

    def test_at_the_ceiling_the_run_is_stopped(self, monkeypatch):
        """At, not past: reaching the ceiling is reaching it.

        The ceiling is taken from the total actually accumulated rather than
        written as a literal. A token count cannot express an arbitrary dollar
        figure exactly - `int(10.00 / 0.15 * 1e6)` truncates to $9.9999999 - so
        a literal here would be testing the helper's rounding rather than the
        boundary. This pins the real question: at exactly the ceiling, does it
        stop?
        """
        monkeypatch.setenv("MAX_RUN_COST_USD", "10.00")
        _spend("ceiling-run", 10.0)
        exactly_what_was_spent = run_cost("ceiling-run").usd
        monkeypatch.setenv("MAX_RUN_COST_USD", repr(exactly_what_was_spent))

        over, spent = _budget_exceeded("ceiling-run")
        assert over is True
        assert spent.usd == exactly_what_was_spent

    def test_a_hair_under_the_ceiling_does_not_stop(self, monkeypatch):
        """The other side of the same boundary."""
        _spend("ceiling-run", 10.0)
        spent_so_far = run_cost("ceiling-run").usd
        monkeypatch.setenv("MAX_RUN_COST_USD", repr(spent_so_far * 1.000001))
        assert _budget_exceeded("ceiling-run")[0] is False

    def test_the_total_returned_is_the_total_that_triggered_it(self, monkeypatch):
        """The operator must be shown the number the run actually stopped at.

        Reading the cost twice - once to decide, once to report - would let a
        call that landed in between change the figure, and the person would be
        deciding about a different run than the one that stopped.
        """
        monkeypatch.setenv("MAX_RUN_COST_USD", "1.00")
        _spend("ceiling-run", 2.50)
        over, spent = _budget_exceeded("ceiling-run")
        assert over is True
        assert spent.usd == pytest.approx(run_cost("ceiling-run").usd)

    def test_the_ceiling_is_read_fresh_so_raising_it_needs_no_restart(self, monkeypatch):
        """The decision on offer is "raise it and resume".

        Captured at import, raising the ceiling would require a worker restart,
        which turns a one-line answer into an outage.
        """
        monkeypatch.setenv("MAX_RUN_COST_USD", "1.00")
        _spend("ceiling-run", 2.00)
        assert _budget_exceeded("ceiling-run")[0] is True

        monkeypatch.setenv("MAX_RUN_COST_USD", "5.00")
        assert _budget_exceeded("ceiling-run")[0] is False


class TestAnUnpricedCallDoesNotTriggerTheCeiling:
    def test_unknown_models_do_not_accumulate_towards_the_bound(self, monkeypatch):
        """A ceiling that fires on an invented number stops good work for a
        reason that is not true. Unpriced is unknown, not expensive."""
        monkeypatch.setenv("MAX_RUN_COST_USD", "0.01")
        handler = CostTrackingCallbackHandler(
            "ceiling-run", provider="openai", model="a-model-with-no-published-rate"
        )
        handler.on_llm_end(_usage(50_000_000))

        over, spent = _budget_exceeded("ceiling-run")
        assert over is False
        assert spent.unpriced_requests == 1
        assert not spent.fully_priced, "the operator can still see the total is partial"


class TestTheParkedRunHasAWayOut:
    def test_a_budget_paused_run_can_be_cancelled(self):
        """It is parked with no worker, so nothing else will see the flag.

        Leaving it out of this set is the §1-B mistake the codebase keeps
        naming - a rule defined over part of the set it governs - and it would
        strand the run in a state with no exit at all.
        """
        assert BUDGET_PAUSE_STATUS in CANCELLABLE_WHILE_PARKED

    def test_it_is_not_a_failure(self):
        """A pause, not a failure: nothing went wrong and the work is good."""
        assert BUDGET_PAUSE_STATUS != "failed"
        assert BUDGET_PAUSE_STATUS.startswith("waiting_for_")

    def test_the_resume_endpoint_accepts_it(self):
        """Refusing here would leave the only pause in the system with no way
        out but cancel, which is the work thrown away that the pause exists to
        prevent."""
        import inspect

        from app.server import runs as runs_module

        from app.server.runner import BUDGET_PAUSE_STATUS, RESUMABLE_STATUSES

        assert BUDGET_PAUSE_STATUS in RESUMABLE_STATUSES
        assert "resumable = RESUMABLE_STATUSES" in inspect.getsource(runs_module)

    def test_the_runner_resumes_it_by_the_same_path_as_a_failed_run(self):
        import inspect

        from app.server.runner import WorkflowRunner

        from app.server.runner import BUDGET_PAUSE_STATUS, RESUMABLE_STATUSES

        assert BUDGET_PAUSE_STATUS in RESUMABLE_STATUSES
        assert "in RESUMABLE_STATUSES" in inspect.getsource(WorkflowRunner.resume_run)


class TestTheCostIsVisibleToAnOperator:
    """Item 3's acceptance test is "a run reports its own cost".

    Accumulating it is half the job; a number nobody can read is not a report.
    Before this, the total was reachable only from inside the worker, so the
    only time an operator saw a figure was when a budget pause fired.
    """

    def test_the_status_model_accepts_the_paused_status(self):
        """A status the response model rejects breaks *reading* the run.

        The run itself is fine and the page that would explain why it stopped is
        what fails, with a `ValidationError`. This is the `approval_denied`
        defect shape, on the status field.
        """
        import typing

        from app.server.models import RunStatusResponse

        allowed = typing.get_args(
            RunStatusResponse.model_fields["status"].annotation
        )
        assert BUDGET_PAUSE_STATUS in allowed

    def test_a_run_that_has_spent_nothing_reports_no_summary(self):
        """Absent, not zero: `$0.00` on an untracked run is a false measurement."""
        from app.server.runs import _cost_summary

        assert _cost_summary("a-run-this-process-never-saw") is None

    def test_a_run_with_calls_reports_its_own_figures(self):
        from app.server.runs import _cost_summary

        _spend("ceiling-run", 0.30)
        summary = _cost_summary("ceiling-run")
        assert summary is not None
        assert summary.estimated_cost_usd == pytest.approx(0.30, rel=1e-3)
        assert summary.successful_requests == 1
        assert summary.fully_priced is True

    def test_a_partial_total_is_flagged_on_the_wire(self):
        """The field that stops `$0.00` being read as "free"."""
        from app.server.runs import _cost_summary

        handler = CostTrackingCallbackHandler(
            "ceiling-run", provider="openai", model="a-model-with-no-published-rate"
        )
        handler.on_llm_end(_usage(1_000))

        summary = _cost_summary("ceiling-run")
        assert summary is not None
        assert summary.fully_priced is False
        assert summary.unpriced_requests == 1
        assert "a-model-with-no-published-rate" in summary.unpriced_models
