"""Ending a stage that has answered and started going in a circle.

Measured on run-5d83e946: `milestone_review` emitted its complete verdict as
message content alongside a `read_file` call twenty-seven times, asking for the
same twenty lines of the same file every time, until the recursion limit
stopped it. See `app.agents.settled_answer` for the whole account.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents.settled_answer import (
    _asks_only_for_what_it_has_already_seen,
    _call_signature,
    build_settled_answer_middleware,
)


class Verdict(BaseModel):
    status: str
    reason: str


ANSWER = '{"status": "changes_required", "reason": "tests copy the code"}'


def _ai(content: str, calls: list[dict] | None = None) -> AIMessage:
    return AIMessage(content=content, tool_calls=calls or [], id="last")


def _call(name: str, args: dict, id_: str = "c1") -> dict:
    return {"name": name, "args": args, "id": id_, "type": "tool_call"}


def _after(state: dict, schema=Verdict):
    return build_settled_answer_middleware(schema, "milestone_review").after_model(state, None)


# --- the run-5d83e946 shape -----------------------------------------------


def test_an_answered_stage_repeating_a_read_is_ended() -> None:
    repeated = _call("read_file", {"file_path": "/a/script.test.mjs", "limit": 20, "offset": 20})
    state = {
        "messages": [
            HumanMessage(content="review the milestone"),
            AIMessage(content="looking", tool_calls=[dict(repeated, id="c0")], id="first"),
            ToolMessage(content="lines 21-40", tool_call_id="c0"),
            _ai(ANSWER, [repeated]),
        ]
    }

    update = _after(state)

    assert update is not None
    assert update["jump_to"] == "end"
    settled = update["messages"][0]
    # The pending call is dropped, or the thread ends holding a call with no
    # result - invalid history for the nudge, which re-invokes this thread.
    assert not settled.tool_calls
    # The answer stays where the normal return path already looks for it.
    assert settled.content == ANSWER
    assert settled.id == "last"


def test_a_stage_still_finding_things_out_is_left_alone() -> None:
    """The safety property: an answer plus a NEW request is progress.

    Without this the middleware would stop a model the first time it wrote a
    provisional verdict, which is a worse failure than the spin it fixes.
    """
    state = {
        "messages": [
            AIMessage(
                content="looking",
                tool_calls=[_call("read_file", {"file_path": "/a/script.js"}, "c0")],
                id="first",
            ),
            ToolMessage(content="...", tool_call_id="c0"),
            _ai(ANSWER, [_call("read_file", {"file_path": "/a/index.html"}, "c1")]),
        ]
    }

    assert _after(state) is None


def test_a_repeated_call_without_an_answer_is_left_alone() -> None:
    """Re-reading a file is ordinary. Only an answer makes stopping safe."""
    repeated = _call("read_file", {"file_path": "/a/script.js"})
    state = {
        "messages": [
            AIMessage(content="looking", tool_calls=[dict(repeated, id="c0")], id="first"),
            ToolMessage(content="...", tool_call_id="c0"),
            _ai("let me check that again", [repeated]),
        ]
    }

    assert _after(state) is None


def test_prose_that_merely_mentions_json_is_not_an_answer() -> None:
    repeated = _call("read_file", {"file_path": "/a/script.js"})
    state = {
        "messages": [
            AIMessage(content="looking", tool_calls=[dict(repeated, id="c0")], id="first"),
            ToolMessage(content="...", tool_call_id="c0"),
            _ai('I will return {"status": "ok"} once I have checked', [repeated]),
        ]
    }

    # `{"status": "ok"}` is missing `reason`, so it does not satisfy the schema.
    assert _after(state) is None


def test_a_turn_with_no_pending_call_ends_on_its_own() -> None:
    assert _after({"messages": [_ai(ANSWER)]}) is None


def test_a_stage_with_no_schema_has_nothing_to_be_finished_with() -> None:
    repeated = _call("read_file", {"file_path": "/a/script.js"})
    state = {
        "messages": [
            AIMessage(content="looking", tool_calls=[dict(repeated, id="c0")], id="first"),
            ToolMessage(content="...", tool_call_id="c0"),
            _ai(ANSWER, [repeated]),
        ]
    }

    assert _after(state, schema=None) is None


def test_an_empty_or_non_ai_tail_is_ignored() -> None:
    assert _after({"messages": []}) is None
    assert _after({"messages": [HumanMessage(content="hello")]}) is None


# --- the parts ------------------------------------------------------------


def test_identical_arguments_in_a_different_order_are_the_same_request() -> None:
    """Argument dicts are not ordered, and a spin must not hide behind that."""
    a = _call("read_file", {"file_path": "/a.js", "limit": 20})
    b = _call("read_file", {"limit": 20, "file_path": "/a.js"})

    assert _call_signature(a) == _call_signature(b)


def test_one_new_call_among_repeats_counts_as_progress() -> None:
    seen = AIMessage(content="", tool_calls=[_call("read_file", {"p": 1}, "c0")], id="a")
    pending = [_call("read_file", {"p": 1}, "c1"), _call("read_file", {"p": 2}, "c2")]

    assert not _asks_only_for_what_it_has_already_seen(pending, [seen])


# --- the graph has to honour the jump -------------------------------------


def test_the_agent_graph_actually_stops() -> None:
    """The hook returning `jump_to` proves nothing on its own.

    `can_jump_to` has to reach the compiled graph as a conditional edge, or the
    update is accepted and the loop carries on exactly as it did on
    run-5d83e946. This drives a real agent with a model that reproduces that
    run's behaviour - verdict as content, plus the same call every time - and
    counts the turns.
    """
    from langchain.agents import create_agent
    from langchain_core.callbacks import CallbackManagerForLLMRun
    from langchain_core.language_models import BaseChatModel
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.tools import tool

    ran: list[str] = []

    @tool
    def peek(path: str) -> str:
        """Read a path."""
        ran.append(path)
        return "the same twenty lines every time"

    class AlwaysTheSame(BaseChatModel):
        """Writes the finished verdict and asks for the same bytes again."""

        @property
        def _llm_type(self) -> str:
            return "always-the-same"

        def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ARG002
            return self

        def _generate(
            self,
            messages,  # noqa: ANN001
            stop=None,  # noqa: ANN001
            run_manager: CallbackManagerForLLMRun | None = None,
            **kwargs,
        ) -> ChatResult:
            message = AIMessage(
                content=ANSWER,
                tool_calls=[
                    _call("peek", {"path": "/a/script.test.mjs"}, f"c{len(ran)}")
                ],
            )
            return ChatResult(generations=[ChatGeneration(message=message)])

    agent = create_agent(
        model=AlwaysTheSame(),
        tools=[peek],
        middleware=[build_settled_answer_middleware(Verdict, "milestone_review")],
    )

    result = agent.invoke(
        {"messages": [HumanMessage(content="review it")]},
        {"recursion_limit": 25},
    )

    # Turn one makes the call for the first time - nothing repeated yet, so it
    # is left alone. Turn two repeats it with the answer already written, and
    # is stopped. Without the middleware this runs to the recursion limit.
    assert ran == ["/a/script.test.mjs"], f"expected one tool run, got {ran}"
    tail = result["messages"][-1]
    assert not getattr(tail, "tool_calls", None)
    assert ANSWER in str(tail.content)


def test_the_deep_agent_graph_also_stops() -> None:
    """The real path builds agents with `create_deep_agent`, not `create_agent`.

    It composes its own middleware around the caller's, so the conditional edge
    reaching the compiled graph is a separate claim from the one above. Asserted
    separately because a middleware that works in one and not the other would
    pass every test here and change nothing in production.
    """
    from deepagents import create_deep_agent
    from langchain_core.callbacks import CallbackManagerForLLMRun
    from langchain_core.language_models import BaseChatModel
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.tools import tool

    ran: list[str] = []

    @tool
    def peek(path: str) -> str:
        """Read a path."""
        ran.append(path)
        return "the same twenty lines every time"

    class AlwaysTheSame(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return "always-the-same"

        def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ARG002
            return self

        def with_structured_output(self, schema, **kwargs):  # noqa: ANN001, ARG002
            return self

        def _generate(
            self,
            messages,  # noqa: ANN001
            stop=None,  # noqa: ANN001
            run_manager: CallbackManagerForLLMRun | None = None,
            **kwargs,
        ) -> ChatResult:
            message = AIMessage(
                content=ANSWER,
                tool_calls=[_call("peek", {"path": "/a/script.test.mjs"}, f"c{len(ran)}")],
            )
            return ChatResult(generations=[ChatGeneration(message=message)])

    agent = create_deep_agent(
        model=AlwaysTheSame(),
        tools=[peek],
        system_prompt="review the milestone",
        response_format=Verdict,
        middleware=[build_settled_answer_middleware(Verdict, "milestone_review")],
    )

    result = agent.invoke(
        {"messages": [HumanMessage(content="review it")]},
        {"recursion_limit": 25},
    )

    assert ran == ["/a/script.test.mjs"], f"expected one tool run, got {ran}"
    assert not getattr(result["messages"][-1], "tool_calls", None)
