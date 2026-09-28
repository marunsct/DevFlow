"""A run with no human reviewer must never be parked waiting for one.

`_run_review_gate` opens a review session and pauses unconditionally - it never
asks whether that review is switched on. Two escalations routed straight to it:
a milestone review that exhausted its revisions, and a sprint that exhausted its
remediation attempts. Both are the right place to want a person; neither checked
whether there is one.

Reviews are opt-in, and the default `review_policy` is `{}`. Measured on
one run: it sat in `awaiting_user_review:sprint` with an empty policy -
not failed, not progressing, and holding a worker.
"""

from __future__ import annotations

from app.graph.workflow import SPRINT_REVIEW, _escalate_to_a_human


def test_a_run_with_no_reviewer_fails_with_the_reason() -> None:
    update = _escalate_to_a_human(
        {"review_policy": {}},
        error="Sprint exhausted its 3 remediation attempts with defects still open.",
        test_round=4,
    )

    assert update["stage"] == "failed"
    assert "remediation attempts" in update["error"]
    # The context still travels, so a resume has what it needs.
    assert update["test_round"] == 4


def test_a_run_that_asked_for_a_reviewer_still_waits_for_one() -> None:
    update = _escalate_to_a_human(
        {"review_policy": {SPRINT_REVIEW: True}},
        error="should not be used",
        test_round=4,
    )

    assert update["stage"] == "user_review_sprint"
    assert "error" not in update


def test_a_missing_policy_is_read_as_no_reviewer() -> None:
    """The default for a run that never sets one."""
    assert _escalate_to_a_human({}, error="stopped")["stage"] == "failed"


def test_neither_escalation_routes_there_unconditionally() -> None:
    """Both call sites must go through the check, not around it.

    Fixing the one that happened to hang is how this codebase has shipped the
    same bug repeatedly; the other had simply not been reached yet.
    """
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    # The invariant, not the census: the only place that may name the stage
    # directly is the helper itself, so every escalation goes through the
    # check that asks whether a human is watching.
    assert source.count('stage="user_review_sprint"') == 1

    # And every escalation really is a call to it. A fixed total was pinned
    # here and broke the moment a third escalation was added - the last sprint
    # checking the brief before a run may finish - which told us nothing about
    # whether the new one was correct. What matters is that none of them names
    # the stage themselves, which the assertion above covers, and that the
    # helper is called rather than reimplemented.
    definition = source.count("def _escalate_to_a_human(")
    calls = source.count("_escalate_to_a_human(") - definition

    assert definition == 1
    assert calls >= 3, f"expected every escalation to go through the helper, found {calls}"
