"""A stage circling the same calls with nothing new coming back ends, not spends.

The ladder of notes, refusals and withheld tools tells a stage that nothing
has changed; a weak model kept calling anyway - one live run's repeated-read
tally climbed while its tools were withheld one by one, and one sprint
planner's `changed_since_sprint` went from 3 to 27 calls in an evening. The
budget hard stop ends such a stage eventually, but only after the rest of its
model calls were spent on pointer-answer turns: budget-exhaustion warnings
ran 47 in a day, concentrated in the defect-fix stages.

The stop is deterministic now: when the conversation itself shows
`SAME_CALLS_BEFORE_ENDING_THE_STAGE` identical calls that returned nothing
new and no structured answer was ever written, the stage ends marked
no-progress, and the run's recovery retries on a fresh conversation instead
of nudging (Initiative L.5). Counted from the conversation, not the shared
stage tally, because that tally was measured counting the run, not the
stage.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents.settled_answer import (
    NO_PROGRESS_MARKER,
    SAME_CALLS_BEFORE_ENDING_THE_STAGE,
    build_settled_answer_middleware,
    was_stopped_by_the_budget,
    was_stopped_for_no_progress,
)
from app.agents.workspace_backend import READ_REFUSED_MARKER


class Plan(BaseModel):
    goal: str


def _read(i: int) -> AIMessage:
    return AIMessage(
        content="", id=f"a{i}",
        tool_calls=[{"name": "read_file", "args": {"path": "app.js"}, "id": f"c{i}"}],
    )


def _circling(n: int) -> list:
    """A conversation whose same read was refused n times, now asked again."""
    messages: list = [HumanMessage(content="do the work")]
    for i in range(n):
        messages.append(_read(i))
        messages.append(ToolMessage(
            content=f"[Refusing to read app.js again - {READ_REFUSED_MARKER}: the stage already holds these bytes.]",
            tool_call_id=f"c{i}",
        ))
    messages.append(_read(n))
    return messages


def test_a_stage_past_the_tally_with_no_answer_ends_with_no_progress() -> None:
    middleware = build_settled_answer_middleware(Plan, "defect_fix_0_0", 40)

    result = middleware.after_model({"messages": _circling(SAME_CALLS_BEFORE_ENDING_THE_STAGE)})

    assert result is not None and result.get("jump_to") == "end"
    assert was_stopped_for_no_progress({"messages": result["messages"]})
    # Recovery treats the stop like the budget one: no nudge, straight to a
    # fresh conversation.
    assert was_stopped_by_the_budget({"messages": result["messages"]})


def test_a_stage_under_the_tally_is_not_ended_for_it() -> None:
    middleware = build_settled_answer_middleware(Plan, "defect_fix_0_0", 40)

    result = middleware.after_model({"messages": _circling(SAME_CALLS_BEFORE_ENDING_THE_STAGE - 1)})

    assert not was_stopped_for_no_progress({"messages": (result or {}).get("messages") or []})


def test_a_stage_that_wrote_its_answer_is_not_ended_for_the_tally() -> None:
    """An answer exists: the stage is about to end on its own terms, and the
    tally's job - stopping the spend - no longer applies."""
    middleware = build_settled_answer_middleware(Plan, "defect_fix_0_0", 40)
    messages = _circling(SAME_CALLS_BEFORE_ENDING_THE_STAGE)
    messages.pop()
    messages.append(AIMessage(content='{"goal": "ship it"}', id="answer"))

    result = middleware.after_model({"messages": messages})

    assert not was_stopped_for_no_progress({"messages": (result or {}).get("messages") or []})


def test_identical_answers_from_the_query_guards_count_too() -> None:
    """Whichever guard describes the loop - the read refusal, the same-answer
    note on a listing or search - the stop is the same."""
    from app.agents.repeated_queries import SAME_ANSWER_MARKER

    messages: list = [HumanMessage(content="plan the sprint")]
    for i in range(SAME_CALLS_BEFORE_ENDING_THE_STAGE):
        messages.append(AIMessage(
            content="", id=f"a{i}",
            tool_calls=[{"name": "changed_since_sprint", "args": {"sprint": i + 1}, "id": f"c{i}"}],
        ))
        messages.append(ToolMessage(
            content=f"Sprint {i + 1} has not been accepted yet.[This `changed_since_sprint` "
                    f"{SAME_ANSWER_MARKER} the {i + 1} previous times you ran it in this stage.]",
            tool_call_id=f"c{i}",
        ))
    messages.append(AIMessage(
        content="", id="a99",
        tool_calls=[{"name": "changed_since_sprint", "args": {"sprint": 99}, "id": "c99"}],
    ))
    middleware = build_settled_answer_middleware(Plan, "scrum_master", 40)

    result = middleware.after_model({"messages": messages})

    assert result is not None and was_stopped_for_no_progress({"messages": result["messages"]})
    assert NO_PROGRESS_MARKER
