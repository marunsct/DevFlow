"""At the end of the budget, answering is the only move the model has left.

Measured on run-6b511391. The last request `specialist_testing_1` ever made
carried "You have made about 39 of the 40 model calls this stage is allowed ...
Return your structured response now", and the model replied with an
`edit_artifact` call. It did that on three consecutive fresh conversations and
the run failed with nothing to show for 13.5 million tokens.

Across the twelve stored transcripts that correction was sent on 276 calls. 13
returned the answer; 263 went back to work. Asking is not a mechanism. Taking
the tools away is, and the same move settled the architecture reviewer that
kept writing a document it had been told not to write - see `role_agent`.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from app.agents.settled_answer import (
    CALLS_RESERVED_FOR_THE_ANSWER,
    MODEL_CALLS_PER_STAGE,
    TOOLS_WITHHELD_NOTICE,
    build_settled_answer_middleware,
)


class Verdict(BaseModel):
    status: str
    reason: str


ANSWER = '{"status": "changes_required", "reason": "tests copy the code"}'

TOOLS = ["read_file", "edit_artifact", "run_terminal_command"]


class _Request:
    """The parts of `ModelRequest` this middleware touches."""

    def __init__(self, messages, tools=None):
        self.messages = messages
        self.tools = list(TOOLS if tools is None else tools)
        self.captured: dict = {}

    def override(self, **changes):
        self.captured.update(changes)
        other = _Request(changes.get("messages", self.messages), changes.get("tools", self.tools))
        other.captured = self.captured
        return other


def _conversation(calls: int, last_content: str = "still working") -> list:
    """A stage that has made `calls` model calls, the last one prose."""
    messages: list = [HumanMessage(content="build the thing")]
    messages += [AIMessage(content="working", id=f"a{i}") for i in range(calls - 1)]
    messages.append(AIMessage(content=last_content, id="last"))
    return messages


def _call_the_middleware(messages, tools=None, limit=MODEL_CALLS_PER_STAGE):
    request = _Request(messages, tools)
    build_settled_answer_middleware(Verdict, "specialist_testing_1", limit).wrap_model_call(
        request, lambda r: r
    )
    return request.captured


def test_the_tools_are_withheld_on_the_last_calls() -> None:
    captured = _call_the_middleware(_conversation(MODEL_CALLS_PER_STAGE - 1))

    assert captured.get("tools") == []
    assert TOOLS_WITHHELD_NOTICE in str(captured["messages"][-1])


def test_the_reserve_is_more_than_one_call() -> None:
    """A model that has just lost its tools may spend a call saying so."""
    assert CALLS_RESERVED_FOR_THE_ANSWER >= 2

    first_of_the_reserve = MODEL_CALLS_PER_STAGE - CALLS_RESERVED_FOR_THE_ANSWER
    assert _call_the_middleware(_conversation(first_of_the_reserve)).get("tools") == []


def test_a_stage_with_room_left_keeps_every_tool() -> None:
    """The tempting version of this change strips tools at the warning
    threshold. 23 of the 28 stages ever warned went on to answer, some after
    forty further calls of real work, so 70% is the wrong place."""
    warned = int(MODEL_CALLS_PER_STAGE * 0.7) + 1
    captured = _call_the_middleware(_conversation(warned))

    assert "tools" not in captured
    assert "model calls this stage is allowed" in str(captured["messages"][-1])


def test_an_answer_already_written_leaves_the_tools_alone() -> None:
    """`_decide` ends that stage gracefully at the limit with the answer it
    has. There is nothing to force, so nothing is taken away."""
    messages = _conversation(MODEL_CALLS_PER_STAGE - 1, last_content=ANSWER)

    assert "tools" not in _call_the_middleware(messages)


def test_the_schema_errors_still_travel_with_the_notice() -> None:
    """The model is being asked to answer; it should know why its last attempt
    was refused."""
    messages = _conversation(MODEL_CALLS_PER_STAGE - 1, last_content='{"status": "ok"}')

    captured = _call_the_middleware(messages)
    correction = str(captured["messages"][-1])

    assert captured.get("tools") == []
    assert "reason" in correction
    assert TOOLS_WITHHELD_NOTICE in correction


def test_a_stage_with_no_budget_is_never_stripped() -> None:
    """`step_limit` defaults to 0 for callers that never set one."""
    assert "tools" not in _call_the_middleware(_conversation(80), limit=0)


def test_the_notice_says_what_was_done_not_what_is_wanted() -> None:
    """263 of the 276 warnings asked. This one reports."""
    assert "have been withheld" in TOOLS_WITHHELD_NOTICE
    assert "no file left to read" in TOOLS_WITHHELD_NOTICE


def test_the_real_graph_leaves_exactly_one_tool_bound() -> None:
    """The whole change rests on a detail of `create_agent`'s binding.

    `_get_bound_model` computes `final_tools = list(request.tools)` and then
    appends the structured-output tools, so a middleware that empties
    `request.tools` leaves the model bound to exactly one tool: the one that
    ends the stage. If that ever stops being true the model is handed no tools
    at all, which some servers refuse - so this drives a real agent rather
    than asserting on the override.
    """
    from langchain.agents import create_agent
    from langchain_core.callbacks import CallbackManagerForLLMRun
    from langchain_core.language_models import BaseChatModel
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.tools import tool

    bound: list[list[str]] = []

    @tool
    def peek(path: str) -> str:
        """Read a path."""
        return "the same twenty lines every time"

    class WorksUntilItCannot(BaseChatModel):
        """Reads a file whenever reading is possible - run-6b511391's model."""

        @property
        def _llm_type(self) -> str:
            return "works-until-it-cannot"

        def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ARG002
            bound.append(
                [t.name if hasattr(t, "name") else str(t.get("name")) for t in tools]
            )
            return self

        def _generate(
            self,
            messages,  # noqa: ANN001
            stop=None,  # noqa: ANN001
            run_manager: CallbackManagerForLLMRun | None = None,
            **kwargs,
        ) -> ChatResult:
            offered = bound[-1] if bound else []
            if "peek" in offered:
                call = {
                    "name": "peek",
                    "args": {"path": f"/a/{len(bound)}.mjs"},
                    "id": f"c{len(bound)}",
                    "type": "tool_call",
                }
            else:
                call = {
                    "name": offered[0],
                    "args": {"status": "changes_required", "reason": "out of room"},
                    "id": f"c{len(bound)}",
                    "type": "tool_call",
                }
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))]
            )

    limit = 6
    agent = create_agent(
        model=WorksUntilItCannot(),
        tools=[peek],
        response_format=Verdict,
        middleware=[build_settled_answer_middleware(Verdict, "specialist_testing_1", limit)],
    )

    result = agent.invoke(
        {"messages": [HumanMessage(content="test it")]},
        {"recursion_limit": 60},
    )

    stripped = [offered for offered in bound if "peek" not in offered]
    assert stripped, f"the tools were never withheld; bound each call: {bound}"
    assert all(len(offered) == 1 for offered in stripped), (
        f"expected one tool left - the answer - got {stripped}"
    )
    # And the stage ended through it, rather than running to the ceiling.
    assert len(bound) < limit + CALLS_RESERVED_FOR_THE_ANSWER, bound
    assert result.get("structured_response") is not None
