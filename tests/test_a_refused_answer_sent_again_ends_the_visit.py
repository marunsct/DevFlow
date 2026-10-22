"""A structured answer its schema keeps refusing ends the visit instead of going round.

Measured on one run: a fix stage found its defect already fixed and answered
with an empty object; the schema refused it ("every field of this answer is
empty"), and the stage sent the same empty object about fifty times, 51 calls
past its model-call budget. The refusal is a tool message after the reply, so
the budget stop - which only looked at a reply - never saw it.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents.settled_answer import (
    BUDGET_STOP_MARKER,
    SAME_REFUSED_ANSWERS_BEFORE_ENDING,
    build_settled_answer_middleware,
    was_stopped_by_the_budget,
)


class SpecialistAnswer(BaseModel):
    changed_files: list[str] = []


REFUSAL = "Error: Failed to parse structured output for tool 'SpecialistAnswer': every field of this answer is empty"


def _refused(times: int, args: dict | None = None, vary: bool = False) -> list[object]:
    messages: list[object] = [HumanMessage(content="Fix the defect.")]
    for n in range(times):
        sent = dict(args or {})
        if vary:
            sent["changed_files"] = [f"f{n}.js"]
        messages.append(AIMessage(content="", tool_calls=[{"name": "SpecialistAnswer", "args": sent, "id": f"a{n}"}]))
        messages.append(ToolMessage(content=REFUSAL, tool_call_id=f"a{n}", name="SpecialistAnswer"))
    return messages


def _after(messages, step_limit: int = 40):
    middleware = build_settled_answer_middleware(SpecialistAnswer, "defect_fix_1_0", step_limit=step_limit)
    return middleware.after_model({"messages": messages})


def test_the_same_refused_answer_three_times_running_ends_the_visit() -> None:
    ended = _after(_refused(SAME_REFUSED_ANSWERS_BEFORE_ENDING))

    assert ended is not None and ended["jump_to"] == "end"
    assert was_stopped_by_the_budget({"messages": [*_refused(1), *ended["messages"]]})
    assert ended["messages"][-1].additional_kwargs.get(BUDGET_STOP_MARKER)


def test_fewer_or_different_answers_go_on() -> None:
    assert _after(_refused(SAME_REFUSED_ANSWERS_BEFORE_ENDING - 1)) is None
    assert _after(_refused(SAME_REFUSED_ANSWERS_BEFORE_ENDING, vary=True)) is None


def test_past_its_budget_one_refused_answer_is_enough() -> None:
    ended = _after(_refused(2, vary=True), step_limit=2)

    assert ended is not None and ended["jump_to"] == "end"
