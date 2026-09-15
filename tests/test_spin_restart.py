"""A stage that spins gets the same fresh conversations as one that returns empty.

Both mean "the stage produced no answer". They were handled differently for no
defensible reason: a stage that RETURNED without a structured response got
three fresh conversations, and a stage that SPUN until the recursion limit got
none - it failed the whole run on its first attempt.

run-e9e7f48f died that way in `specialist_ui_ux_2` after 14 identical `grep`
calls, with three restarts unused, while the error it raised said in as many
words that "a resume re-runs it on a fresh conversation".
"""

from __future__ import annotations

from app.graph.workflow import _restart_on_a_fresh_conversation


def test_the_first_failure_restarts_rather_than_failing() -> None:
    update = _restart_on_a_fresh_conversation(
        {}, "specialist_ui_ux_2", "thread-1", "spun without returning an answer"
    )

    assert update is not None
    assert update["structured_retries"]["specialist_ui_ux_2"] == 1
    # Clearing this is what makes it a retry and not a replay of the failure.
    assert update["pending_inner_thread_id"] is None


def test_restarts_are_capped() -> None:
    from app.graph.workflow import _max_structured_retries

    spent = {"structured_retries": {"s": _max_structured_retries()}}

    assert _restart_on_a_fresh_conversation({}, "s", "t", "why") is not None
    assert _restart_on_a_fresh_conversation(spent, "s", "t", "why") is None


def test_the_stage_restarts_at_its_owning_node() -> None:
    """`specialist_ui_ux_0` is a stage, not a graph node."""
    update = _restart_on_a_fresh_conversation({}, "specialist_ui_ux_0", "t", "why")

    assert update is not None
    assert not update["stage"].startswith("specialist_ui_ux_0")


def test_both_failure_paths_use_it() -> None:
    """The spin path failed the run outright before this existed; reaching one
    of two call sites is the mistake this codebase has made four times."""
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow._run_gated_agent)

    assert source.count("_restart_on_a_fresh_conversation(") >= 2
    assert "spun without returning an answer" in source
    assert "produced no structured response" in source
