"""A stage may reach its model-call budget before its superstep ceiling.

Two limits in two units, chosen independently, that disagreed.
`MODEL_CALLS_PER_STAGE` bounds model calls and is measured: across 71 stage
executions the largest stage that ever finished used 36, so 40 leaves margin.
`INNER_AGENT_RECURSION_LIMIT` bounds LangGraph supersteps, and a superstep is
not a model call - a react agent spends one node on the call and one on each
tool it invokes.

Measured across 88 stage executions in the stored runs: 2.41 supersteps per
model call at the median, 3.14 at the 90th percentile, 3.67 at the maximum. At
2.41, the old ceiling of 60 supersteps is about 25 model calls - well under the
40 the budget allows and under the 36 a healthy stage has actually used.

Run 9f14d645 died of it. Its `specialist_ui_ux_0` spun out three times at
roughly 32 calls an attempt, never once reaching its model-call budget, and
took the run with it.

The cost is not only the healthy stage. `MODEL_CALLS_PER_STAGE` ends a stage by
looking for an answer already written into the conversation and returning it;
the superstep ceiling ends it with a `GraphRecursionError` and a restart. The
tighter limit was stopping the better guard from ever acting.
"""

from __future__ import annotations

from app.agents.settled_answer import MODEL_CALLS_PER_STAGE
from app.graph.workflow import (
    INNER_AGENT_RECURSION_LIMIT,
    SUPERSTEPS_PER_MODEL_CALL,
)

#: The largest number of model calls any stage that finished has ever used,
#: from the measurement recorded on `MODEL_CALLS_PER_STAGE`.
LARGEST_HEALTHY_STAGE_IN_CALLS = 36

#: Measured across 88 stage executions: the 90th percentile.
MEASURED_SUPERSTEPS_PER_CALL_P90 = 3.14


def test_a_stage_can_use_its_whole_call_budget():
    """The ceiling must not bind before the budget it is supposed to outlast."""
    needed = MODEL_CALLS_PER_STAGE * MEASURED_SUPERSTEPS_PER_CALL_P90
    assert INNER_AGENT_RECURSION_LIMIT >= needed, (
        f"{INNER_AGENT_RECURSION_LIMIT} supersteps stops a "
        f"{MODEL_CALLS_PER_STAGE}-call stage at "
        f"{INNER_AGENT_RECURSION_LIMIT / MEASURED_SUPERSTEPS_PER_CALL_P90:.0f} calls"
    )


def test_the_largest_stage_that_ever_finished_would_survive():
    """Run 9f14d645's specialist died at roughly 32 calls; 36 have been needed."""
    needed = LARGEST_HEALTHY_STAGE_IN_CALLS * MEASURED_SUPERSTEPS_PER_CALL_P90
    assert INNER_AGENT_RECURSION_LIMIT >= needed


def test_the_ceiling_is_derived_and_not_a_second_copy():
    """Independent numbers drifted once and the drift killed a run."""
    assert INNER_AGENT_RECURSION_LIMIT == int(
        MODEL_CALLS_PER_STAGE * SUPERSTEPS_PER_MODEL_CALL
    )


def test_the_ratio_is_at_least_what_was_measured():
    assert SUPERSTEPS_PER_MODEL_CALL >= MEASURED_SUPERSTEPS_PER_CALL_P90


def test_it_still_bounds_a_spinning_stage():
    """Raised, not removed. A stage that loops for ever is still stopped."""
    assert INNER_AGENT_RECURSION_LIMIT < 1000


def test_the_call_budget_binds_first_so_the_better_guard_acts():
    """`MODEL_CALLS_PER_STAGE` can salvage an answer; the ceiling cannot.

    At the median ratio a stage reaches 40 calls in about 97 supersteps, so the
    budget is met first and `_decide` gets its chance to return an answer the
    stage has already written.
    """
    median_ratio = 2.41
    supersteps_at_budget = MODEL_CALLS_PER_STAGE * median_ratio
    assert supersteps_at_budget < INNER_AGENT_RECURSION_LIMIT


# --- which ceiling reaches a stage first ----------------------------------


def test_the_budget_guard_reaches_a_stage_before_the_ceiling_does() -> None:
    """The two bounds degrade differently, so the order matters.

    The model-call budget forces an answer and can salvage one. The superstep
    ceiling raises `GraphRecursionError`, and the stage restarts from an empty
    conversation with everything it learned discarded.

    At `SUPERSTEPS_PER_MODEL_CALL = 3.2` the ceiling was 128, which the
    worst-ratio stage on record reaches at 33 model calls - five before the
    guard withholds tools at 38 - so on those stages the guard never acted.
    Measured live on run-b6436e36: `defect_fix_1_1` hit the ceiling and
    restarted while the guard sat unreached.
    """
    from app.agents.settled_answer import (
        CALLS_RESERVED_FOR_THE_ANSWER,
        MODEL_CALLS_PER_STAGE,
    )
    from app.graph.workflow import (
        INNER_AGENT_RECURSION_LIMIT,
        WORST_MEASURED_SUPERSTEP_RATIO,
    )

    calls_before_the_ceiling = INNER_AGENT_RECURSION_LIMIT / WORST_MEASURED_SUPERSTEP_RATIO

    assert calls_before_the_ceiling > MODEL_CALLS_PER_STAGE, (
        f"the worst stage on record reaches the superstep ceiling at "
        f"{calls_before_the_ceiling:.0f} model calls, at or before the "
        f"{MODEL_CALLS_PER_STAGE}-call budget that can salvage its answer"
    )
    assert calls_before_the_ceiling > MODEL_CALLS_PER_STAGE - CALLS_RESERVED_FOR_THE_ANSWER


def test_the_ratio_covers_every_stage_measured() -> None:
    """The 90th percentile was a deliberate choice and is no longer the right
    one: it left one stage in ten bounded by the ceiling rather than the
    budget, back when the budget only nagged."""
    from app.graph.workflow import (
        SUPERSTEPS_PER_MODEL_CALL,
        WORST_MEASURED_SUPERSTEP_RATIO,
    )

    assert SUPERSTEPS_PER_MODEL_CALL > WORST_MEASURED_SUPERSTEP_RATIO


def test_the_ceiling_is_still_derived_not_restated() -> None:
    """A second copy of the number is how the two drifted apart before."""
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)

    assert (
        "INNER_AGENT_RECURSION_LIMIT = int(MODEL_CALLS_PER_STAGE * SUPERSTEPS_PER_MODEL_CALL)"
        in source
    )
