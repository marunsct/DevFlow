"""A stage that spins gets the same fresh conversations as one that returns empty.

Both mean "the stage produced no answer". They were handled differently for no
defensible reason: a stage that RETURNED without a structured response got
three fresh conversations, and a stage that SPUN until the recursion limit got
none - it failed the whole run on its first attempt.

One run died that way in `specialist_ui_ux_2` after 14 identical `grep`
calls, with three restarts unused, while the error it raised said in as many
words that "a resume re-runs it on a fresh conversation".
"""

from __future__ import annotations

import pytest

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


class _NoAnswer:
    """A role agent that never returns its answer: it spins to its ceiling, or it returns without one."""

    workflow_response_format = None

    def __init__(self, spins: bool) -> None:
        self.spins = spins

    def invoke(self, request, config=None):  # noqa: ARG002
        from langgraph.errors import GraphRecursionError

        if self.spins:
            raise GraphRecursionError("Recursion limit of 60 reached without hitting a stop condition")
        return {"messages": [], "structured_response": None}

    def get_state(self, config):  # noqa: ARG002
        from types import SimpleNamespace

        return SimpleNamespace(values={"messages": []}, next=())


def _spins(*args, **kwargs):
    from langgraph.errors import GraphRecursionError

    raise GraphRecursionError("Recursion limit of 60 reached without hitting a stop condition")


@pytest.mark.parametrize(("spins", "resumed"), [(True, False), (True, True), (False, False)],
                         ids=["spun", "spun-after-an-approval", "returned-without-an-answer"])
def test_both_failure_paths_restart_on_a_fresh_conversation(tmp_path, monkeypatch, spins, resumed) -> None:
    """The spin path failed the run outright before this existed; reaching one
    of two call sites is the mistake this codebase has made four times."""
    from types import SimpleNamespace

    from app.graph.workflow import _run_gated_agent

    monkeypatch.setattr("app.graph.workflow.resume_with_decision", _spins)
    after_an_approval = {"pending_decision": {"type": "approve"},
                         "pending_inner_thread_id": "outer:specialist_ui_ux_2:1"} if resumed else {}

    update = _run_gated_agent(
        {"stage": "specialist_ui_ux_2", "repository": SimpleNamespace(root_path=str(tmp_path)), **after_an_approval},
        {"configurable": {"thread_id": "outer"}},
        stage_name="specialist_ui_ux_2", agent=_NoAnswer(spins),
        initial_request={"messages": [{"role": "user", "content": "build"}]},
        output_key="out", next_stage="test_and_triage",
    )

    assert update["stage"] != "failed"
    assert update["structured_retries"]["specialist_ui_ux_2"] == 1
