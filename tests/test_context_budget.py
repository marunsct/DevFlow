"""Every context budget must stay inside the window it was derived from.

The bugs this exists to prevent all had the same shape: two numbers that had to
agree were kept in different files and drifted apart. A compaction trigger set
for a 262K model while a 115K model was loaded. A per-command output cap
multiplied by a protected tail into more context than the window held. A
document budget tuned for one model still in force under another.

None of those are visible by reading either number alone, which is why the tests
here assert *relationships* rather than values. A future retune that keeps the
relationships is fine and should not break anything; one that breaks them should
fail here rather than in the middle of an eight-hour run.
"""

from __future__ import annotations

import pytest

from app.agents.context_budget import (
    CHARS_PER_TOKEN,
    MIN_VIABLE_WINDOW,
    DEFAULT_CONTEXT_WINDOW,
    FRAMING_TOKENS,
    MIN_ARTIFACT_REPLY_TOKENS,
    MIN_TOOL_OUTPUT_BYTES,
    TAIL_FRACTION,
    ContextBudget,
    context_window,
)

#: Windows that real models actually have, plus the extremes either side.
#: Anything below `MIN_VIABLE_WINDOW` is clamped up to it - the framing plus a
#: minimum reply leaves no room for a request below that, whatever is configured.
WINDOWS = [8_000, 16_000, 32_000, 64_000, 100_000, 128_000, 131_072, 200_000, 262_144, 1_000_000]


@pytest.mark.parametrize("window", WINDOWS)
def test_the_protected_tail_and_a_reply_fit_in_the_window(window):
    """The failure that killed `specialist_backend_1`.

    Compaction keeps the most recent messages untouched, so the tail is context
    it is *defined* not to reduce. If that floor plus a reply does not fit, no
    compaction schedule can save the run - it will overflow whenever the tail
    fills, and the only symptom is a stage dying late.
    """
    budget = ContextBudget.from_window(window)

    assert budget.fits(), budget.describe()
    assert (
        budget.protected_tail_tokens + budget.max_output_tokens + FRAMING_TOKENS
        <= budget.window_tokens
    )


@pytest.mark.parametrize("window", WINDOWS)
def test_compaction_fires_before_the_ceiling(window):
    """A trigger at or above the ceiling fires only once it is already too late."""
    budget = ContextBudget.from_window(window)

    assert 0 < budget.trigger_tokens < budget.input_ceiling_tokens


@pytest.mark.parametrize("window", WINDOWS)
def test_one_document_cannot_fill_the_input_ceiling(window):
    """A document that fills the ceiling leaves no room for the work after it."""
    budget = ContextBudget.from_window(window)

    document_tokens = budget.document_budget_chars / CHARS_PER_TOKEN
    assert document_tokens < budget.input_ceiling_tokens * 0.5


@pytest.mark.parametrize("window", WINDOWS)
def test_the_tail_never_exceeds_its_share(window):
    budget = ContextBudget.from_window(window)

    share = budget.protected_tail_tokens / budget.input_ceiling_tokens
    assert share <= TAIL_FRACTION + 0.01, budget.describe()


@pytest.mark.parametrize("window", WINDOWS)
def test_a_reply_is_always_large_enough_to_write_an_artifact(window):
    """Cut off mid-document, a write_artifact call corrupts the file silently."""
    budget = ContextBudget.from_window(window)

    assert budget.max_output_tokens >= MIN_ARTIFACT_REPLY_TOKENS


def test_a_small_window_keeps_fewer_messages_rather_than_overflowing():
    """The output-cap floor binds on a small window; `keep` gives way, not the invariant."""
    small = ContextBudget.from_window(20_000)
    large = ContextBudget.from_window(262_144)

    assert small.keep_recent_messages < large.keep_recent_messages
    assert small.tool_output_bytes == MIN_TOOL_OUTPUT_BYTES
    assert small.fits()


def test_every_budget_grows_with_the_window():
    """The point of the exercise: one number carries all the others."""
    small = ContextBudget.from_window(64_000)
    large = ContextBudget.from_window(262_144)

    assert large.input_ceiling_tokens > small.input_ceiling_tokens
    assert large.document_budget_chars > small.document_budget_chars
    assert large.specification_budget_chars > small.specification_budget_chars
    assert large.tool_output_bytes > small.tool_output_bytes


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_the_window_defaults_to_something_conservative():
    assert context_window({}) == DEFAULT_CONTEXT_WINDOW


def test_a_malformed_window_does_not_stop_every_agent_from_starting():
    assert context_window({"MODEL_CONTEXT_WINDOW": "one hundred thousand"}) == DEFAULT_CONTEXT_WINDOW


def test_a_window_too_small_to_run_anything_is_raised():
    """Below the framing plus a minimum reply there is no room for a request."""
    assert context_window({"MODEL_CONTEXT_WINDOW": "100"}) == MIN_VIABLE_WINDOW
    # Clamped when a budget is built directly too, not only when read from env.
    assert ContextBudget.from_window(100).window_tokens == MIN_VIABLE_WINDOW


def test_an_explicit_override_wins_over_the_derivation():
    budget = ContextBudget.resolve({"MODEL_CONTEXT_WINDOW": "100000", "CTX_MAX_TOKENS": "12345"})

    assert budget.input_ceiling_tokens == 12_345


def test_an_override_still_cannot_break_the_floors():
    """A deliberate exception is not a licence to corrupt an artifact."""
    budget = ContextBudget.resolve(
        {"MODEL_MAX_OUTPUT_TOKENS": "10", "SANDBOX_MAX_OUTPUT": "5"}
    )

    assert budget.max_output_tokens >= MIN_ARTIFACT_REPLY_TOKENS
    assert budget.tool_output_bytes >= MIN_TOOL_OUTPUT_BYTES


def test_describe_reports_a_budget_that_does_not_fit():
    """An operator who breaks the invariant by hand should be told."""
    broken = ContextBudget.resolve(
        {"MODEL_CONTEXT_WINDOW": "32000", "CTX_KEEP_MESSAGES": "40", "SANDBOX_MAX_OUTPUT": "65536"}
    )

    assert not broken.fits()
    assert "WARNING" in broken.describe()


# ---------------------------------------------------------------------------
# The consumers must all follow the same window
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("window", [64_000, 262_144])
def test_every_consumer_follows_the_configured_window(window, monkeypatch):
    """The whole point: one setting moves all of them, with no second edit."""
    for name in (
        "CTX_MAX_TOKENS", "CTX_KEEP_MESSAGES", "MODEL_MAX_OUTPUT_TOKENS",
        "SANDBOX_MAX_OUTPUT", "CTX_SPECIFICATION_BUDGET",
        "CTX_ARCHITECT_DOCUMENT_BUDGET", "CTX_REVISION_DOCUMENT_BUDGET",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", str(window))

    from app.agents.context_policy import ContextPolicy
    from app.agents.text_budget import specification_budget
    from app.models import _max_output_tokens
    from app.tools.sandbox import _max_output_size

    budget = ContextBudget.resolve()

    assert ContextPolicy.from_environment().max_context_tokens == budget.input_ceiling_tokens
    assert ContextPolicy.from_environment().keep_recent_messages == budget.keep_recent_messages
    assert _max_output_tokens() == budget.max_output_tokens
    assert _max_output_size() == budget.tool_output_bytes
    assert specification_budget() == budget.specification_budget_chars


def test_the_agent_truncation_helpers_follow_the_window(monkeypatch):
    """Four agents carried their own copy of an 80,000-character default."""
    monkeypatch.delenv("CTX_ARCHITECT_DOCUMENT_BUDGET", raising=False)
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "64000")

    from app.agents.product_manager import _truncate as pm_truncate
    from app.agents.stack_selector import _truncate as stack_truncate
    from app.agents.technical_lead import _truncate as lead_truncate
    from app.agents.tools_models import _truncate_for_llm

    budget = ContextBudget.resolve().document_budget_chars
    huge = "x" * 10_000_000
    for truncate in (pm_truncate, stack_truncate, lead_truncate, _truncate_for_llm):
        # The marker it inserts is the only thing above the budget.
        assert len(truncate(huge)) < budget + 500, truncate.__module__


# ---------------------------------------------------------------------------
# Compaction schedule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("window", [32_000, 100_000, 262_144])
def test_arguments_are_trimmed_before_summarising(window):
    """The cheap relief must be tried before the one that costs a model call."""
    budget = ContextBudget.from_window(window)

    assert budget.truncate_args_trigger_tokens < budget.trigger_tokens
    assert budget.truncate_args_trigger_tokens > 0


def test_the_compaction_schedule_is_ordered():
    """Trim, then summarise, then the ceiling - in that order, with gaps."""
    budget = ContextBudget.from_window(100_000)

    assert (
        budget.truncate_args_trigger_tokens
        < budget.trigger_tokens
        < budget.input_ceiling_tokens
        < budget.window_tokens
    )


# --- an explicit reply ceiling ------------------------------------------
#
# The reply, the conversation and the framing share one window. An override
# applied *after* derivation raised the reply ceiling while leaving the input
# ceiling derived from the old one:
#
#     window 125,000  output 40,000  input 87,750  + framing 6,000 = 133,750
#
# which is 8,750 tokens more than the model has - the exact overflow this
# module exists to prevent. The ceiling is now chosen during derivation, so
# everything measured from it stays consistent.


def test_an_explicit_reply_ceiling_still_fits_the_window():
    from app.agents.context_budget import FRAMING_TOKENS, ContextBudget

    budget = ContextBudget.resolve(
        {"MODEL_CONTEXT_WINDOW": "125000", "MODEL_MAX_OUTPUT_TOKENS": "40000"}
    )

    assert budget.max_output_tokens == 40_000
    assert (
        budget.max_output_tokens + budget.input_ceiling_tokens + FRAMING_TOKENS
        <= budget.window_tokens
    )


def test_raising_the_reply_ceiling_shrinks_the_conversation():
    """The trade-off is the point: they come out of the same window."""
    from app.agents.context_budget import ContextBudget

    derived = ContextBudget.resolve({"MODEL_CONTEXT_WINDOW": "125000"})
    raised = ContextBudget.resolve(
        {"MODEL_CONTEXT_WINDOW": "125000", "MODEL_MAX_OUTPUT_TOKENS": "40000"}
    )

    assert raised.max_output_tokens > derived.max_output_tokens
    assert raised.input_ceiling_tokens < derived.input_ceiling_tokens
    assert raised.trigger_tokens < derived.trigger_tokens


def test_everything_derived_follows_the_new_ceiling():
    """Document and command-output budgets are measured from what is left."""
    from app.agents.context_budget import ContextBudget

    derived = ContextBudget.resolve({"MODEL_CONTEXT_WINDOW": "125000"})
    raised = ContextBudget.resolve(
        {"MODEL_CONTEXT_WINDOW": "125000", "MODEL_MAX_OUTPUT_TOKENS": "40000"}
    )

    assert raised.document_budget_chars < derived.document_budget_chars
    assert raised.tool_output_bytes < derived.tool_output_bytes


def test_a_reply_ceiling_that_would_eat_the_window_is_capped():
    """A conversation still has to exist for a reply to be a reply to it."""
    from app.agents.context_budget import (
        FRAMING_TOKENS,
        MIN_INPUT_CEILING_TOKENS,
        ContextBudget,
    )

    budget = ContextBudget.resolve(
        {"MODEL_CONTEXT_WINDOW": "125000", "MODEL_MAX_OUTPUT_TOKENS": "200000"}
    )

    assert budget.input_ceiling_tokens >= MIN_INPUT_CEILING_TOKENS
    assert (
        budget.max_output_tokens + budget.input_ceiling_tokens + FRAMING_TOKENS
        <= budget.window_tokens
    )


def test_a_reply_ceiling_below_the_floor_is_raised_to_it():
    from app.agents.context_budget import MIN_OUTPUT_TOKENS, ContextBudget

    budget = ContextBudget.resolve(
        {"MODEL_CONTEXT_WINDOW": "125000", "MODEL_MAX_OUTPUT_TOKENS": "10"}
    )

    assert budget.max_output_tokens == MIN_OUTPUT_TOKENS


def test_no_override_leaves_the_derivation_alone():
    from app.agents.context_budget import ContextBudget

    assert ContextBudget.resolve({"MODEL_CONTEXT_WINDOW": "125000"}).max_output_tokens == 31_250


def test_the_reply_ceiling_is_settable_at_runtime():
    from app.server.runtime_settings import SETTABLE_KEYS

    assert SETTABLE_KEYS["model_max_output_tokens"] == "MODEL_MAX_OUTPUT_TOKENS"
