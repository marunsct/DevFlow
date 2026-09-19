"""A stage the budget had to stop must not be nudged again.

`settled_answer` ends a stage that runs past its model-call budget without
producing a structured response. That hard stop works: the inner graph ends.

What burned the calls was the recovery that runs afterwards.
`_nudge_for_the_structured_response` re-invokes the same inner thread, which
re-enters at `__start__` and runs another `before_agent -> model ->
after_model` cycle before stopping again. So every approval gate costs a model
call, and the count climbs until the run's repeat guard kills the stage for
asking for the same thing five times in a row.

Measured on run-91a18470's `test_round_3`: eighteen `__start__` re-entries and
thirty-four `jump_to=end` hard stops on a single inner thread, the model-call
count rising with every gate, ending in

    The 'test_round_3' stage asked to write the same thing 5 times in a row

after fifty-nine attempts to write an answer the stage could not accept.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from app.agents.settled_answer import (
    BUDGET_STOP_MARKER,
    was_stopped_by_the_budget,
)
from app.graph.workflow import _run_gated_agent


class _BudgetStoppedAgent:
    """An agent whose thread `settled_answer` ended at the model-call budget.

    Returns no structured response and no interrupt, exactly as the failing
    stage did, and records every invoke so the test can count the nudges.
    """

    def __init__(self) -> None:
        self.invocations: list[dict] = []

    def invoke(self, request, config=None):
        self.invocations.append({"request": request, "config": config or {}})
        return {
            "messages": [
                AIMessage(
                    content="Constructing final JSON...",
                    additional_kwargs={BUDGET_STOP_MARKER: True},
                )
            ],
            "structured_response": None,
        }


def _gated(agent, state=None):
    return _run_gated_agent(
        state or {"stage": "specialist_testing", "repository": SimpleNamespace(root_path="/w")},
        {"configurable": {"thread_id": "thread-outer"}},
        stage_name="specialist_testing",
        agent=agent,
        initial_request={"messages": []},
        output_key="test_report",
        next_stage="milestone_review",
    )


def test_a_budget_stopped_stage_is_not_nudged():
    """The nudge is a model call on a thread already told it is out of room."""
    agent = _BudgetStoppedAgent()

    _gated(agent)

    # One invoke to run the stage, and no second one to ask it again.
    assert len(agent.invocations) == 1


def test_a_budget_stopped_stage_retries_on_a_fresh_conversation():
    """The retry is the remedy that was always meant to follow the stop.

    Clearing `pending_inner_thread_id` is what makes it a retry rather than a
    replay of the same failed conversation, so it must be gone from the update.
    """
    agent = _BudgetStoppedAgent()

    update = _gated(agent)

    assert update["pending_inner_thread_id"] is None
    assert update["stage"] == "specialist_dispatch"


def test_a_stage_that_merely_failed_is_still_nudged():
    """The budget stop is the exception. A plain missing answer still gets the
    reminder, which is the cheap recovery that ends most prose failures."""
    agent = _BudgetStoppedAgent()
    # No marker: this stage ended for some other reason.
    agent.invoke = lambda request, config=None: agent.invocations.append(  # type: ignore[method-assign]
        {"request": request, "config": config or {}}
    ) or {"messages": [AIMessage(content="I have finished.")], "structured_response": None}

    _gated(agent)

    assert len(agent.invocations) == 2, "the nudge should still run"


def test_the_marker_is_detected_on_the_trailing_message():
    result = {
        "messages": [
            AIMessage(content="earlier"),
            AIMessage(content="the last one", additional_kwargs={BUDGET_STOP_MARKER: True}),
        ]
    }

    assert was_stopped_by_the_budget(result)


def test_a_result_without_the_marker_is_not_a_budget_stop():
    assert not was_stopped_by_the_budget({"messages": [AIMessage(content="done")]})
    assert not was_stopped_by_the_budget({"messages": []})
    assert not was_stopped_by_the_budget({})


def test_the_marker_is_read_from_the_last_answer_only():
    """An old stop from an earlier attempt must not silence a later nudge."""
    result = {
        "messages": [
            AIMessage(content="old stop", additional_kwargs={BUDGET_STOP_MARKER: True}),
            AIMessage(content="a new attempt"),
        ]
    }

    assert not was_stopped_by_the_budget(result)


def test_non_message_results_are_safe():
    """`_run_gated_agent` is called with whatever the graph returned."""
    assert not was_stopped_by_the_budget(None)
    assert not was_stopped_by_the_budget("not a dict")
