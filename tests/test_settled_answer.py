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
    _asks_only_for_what_cannot_have_changed,
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

    assert not _asks_only_for_what_cannot_have_changed(pending, [seen])


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


def test_a_read_after_a_write_is_progress_not_a_circle() -> None:
    """The false positive that would be worse than the spin.

    A specialist that writes a file and reads it back issues a byte-identical
    request and gets different content. Counting that as a repeat would cut a
    working stage off mid-task the moment it had written a report object, which
    is a worse failure than the sixty turns this middleware exists to save.
    """
    read = _call("read_file", {"file_path": "/a/script.js"})
    state = {
        "messages": [
            AIMessage(content="", tool_calls=[dict(read, id="c0")], id="m0"),
            ToolMessage(content="old contents", tool_call_id="c0"),
            AIMessage(
                content="",
                tool_calls=[_call("write_artifact", {"relative_path": "a/script.js"}, "c1")],
                id="m1",
            ),
            ToolMessage(content="written", tool_call_id="c1"),
            _ai(ANSWER, [read]),
        ]
    }

    assert _after(state) is None


def test_a_repeat_after_the_write_is_still_a_circle() -> None:
    """The write only clears what came before it."""
    read = _call("read_file", {"file_path": "/a/script.js"})
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[_call("write_artifact", {"relative_path": "a/script.js"}, "c0")],
                id="m0",
            ),
            ToolMessage(content="written", tool_call_id="c0"),
            AIMessage(content="", tool_calls=[dict(read, id="c1")], id="m1"),
            ToolMessage(content="new contents", tool_call_id="c1"),
            _ai(ANSWER, [read]),
        ]
    }

    update = _after(state)

    assert update is not None and update["jump_to"] == "end"


def test_a_failure_inside_the_check_leaves_the_loop_alone() -> None:
    """It runs after every model call of every gated stage.

    An exception here would end the stage, which is a worse failure than the
    spin this exists to prevent. A schema that raises on validation stands in
    for anything unexpected in the state.
    """

    class Exploding:
        @staticmethod
        def model_validate(payload):  # noqa: ANN001, ANN205
            raise RuntimeError("boom")

    repeated = _call("read_file", {"file_path": "/a/script.js"})
    state = {
        "messages": [
            AIMessage(content="", tool_calls=[dict(repeated, id="c0")], id="m0"),
            ToolMessage(content="...", tool_call_id="c0"),
            _ai(ANSWER, [repeated]),
        ]
    }

    # `_answer_in` already swallows a validation failure, so the stage simply
    # is not stopped - and nothing propagates either way.
    assert _after(state, schema=Exploding) is None


# --- an answer that is nearly right --------------------------------------


def test_a_near_miss_is_told_which_fields_are_wrong() -> None:
    """The twenty-one minutes that prompted this.

    run-5c7d7d8d's `principal_architect` spent 21 minutes and fifteen answers
    emitting `"product_scope": {"covers": [...], "defers": [...]}` against a
    schema declaring `product_scope: str`. Pydantic says exactly what is wrong.
    The model never saw it: an answer written into the conversation goes
    through no validation at all, and only the structured-output channel
    validates.
    """
    from app.agents.settled_answer import _why_it_was_not_accepted

    wrong = AIMessage(
        content='{"status": {"covers": ["a"]}, "reason": "r"}', id="m"
    )

    why = _why_it_was_not_accepted(wrong, Verdict)

    assert "not a valid response for this stage" in why
    assert "status" in why
    assert "valid string" in why
    # It must forbid the two things a model does next: start over, or explain.
    assert "Do not start the work over" in why


def test_a_valid_answer_gets_no_correction() -> None:
    from app.agents.settled_answer import _why_it_was_not_accepted

    assert _why_it_was_not_accepted(AIMessage(content=ANSWER, id="m"), Verdict) == ""


def test_prose_with_no_json_gets_no_correction() -> None:
    """A model narrating its work has not attempted an answer."""
    from app.agents.settled_answer import _why_it_was_not_accepted

    assert _why_it_was_not_accepted(AIMessage(content="Let me look.", id="m"), Verdict) == ""


def test_the_correction_reaches_the_request_without_touching_history() -> None:
    """Appending to history after an assistant message with pending tool calls
    would break their pairing, which is why this rides on the request."""
    captured = {}

    class _Request:
        def __init__(self, messages):
            self.messages = messages

        def override(self, **changes):
            captured["messages"] = changes.get("messages", self.messages)
            return _Request(captured["messages"])

    request = _Request(
        [
            HumanMessage(content="do it"),
            AIMessage(content='{"status": {"covers": []}, "reason": "r"}', id="m"),
        ]
    )
    before = list(request.messages)

    build_settled_answer_middleware(Verdict, "principal_architect").wrap_model_call(
        request, lambda r: "handled"
    )

    assert request.messages == before
    assert "not a valid response" in str(captured["messages"][-1])


def test_the_real_shape_from_run_5c7d7d8d_is_diagnosed() -> None:
    """The exact payload, against the exact schema."""
    from app.agents.principal_architect import TechnicalSpecificationOutput
    from app.agents.settled_answer import _why_it_was_not_accepted

    emitted = AIMessage(
        content=(
            '{"product_scope": {"covers": ["A responsive single-page web '
            'application."], "defers": ["Multi-user sync."]}, '
            '"component_boundaries": []}'
        ),
        id="m",
    )

    why = _why_it_was_not_accepted(emitted, TechnicalSpecificationOutput)

    assert "product_scope" in why
    assert "valid string" in why


def test_the_failing_field_names_are_available_for_the_log() -> None:
    """Diagnosing what you cannot see is finding 47 again.

    On run-44e9fc83 the log said `principal_architect` "sent an answer that
    does not satisfy its schema" four times and nothing about which part. The
    event stream showed `product_scope` being corrected from an object to a
    string and the stage failing anyway, with no way to see what else was
    wrong.
    """
    from app.agents.settled_answer import _LAST_FAILING_FIELDS, _why_it_was_not_accepted

    class Spec(BaseModel):
        product_scope: str
        component_boundaries: list[str]

    wrong = AIMessage(
        content='{"product_scope": "fine", "component_boundaries": "not a list"}', id="m"
    )

    _why_it_was_not_accepted(wrong, Spec)

    assert _LAST_FAILING_FIELDS == ["component_boundaries"]


def test_failing_fields_reads_a_pydantic_error() -> None:
    from pydantic import ValidationError

    from app.agents.settled_answer import failing_fields

    class Spec(BaseModel):
        a: str
        b: int

    try:
        Spec.model_validate({"a": [], "b": "x"})
    except ValidationError as exc:
        assert failing_fields(exc) == ["a", "b"]
    else:  # pragma: no cover
        raise AssertionError("expected a validation error")


def test_failing_fields_survives_a_non_pydantic_exception() -> None:
    from app.agents.settled_answer import failing_fields

    assert failing_fields(RuntimeError("boom")) == []


def test_an_answer_written_several_turns_ago_still_counts() -> None:
    """run-d6369866's `scrum_master` wrote a valid sprint plan at 15:23:30 and
    then spent eleven and a half minutes writing prose about creating files it
    has no tools to create. By the time it was circling, the last message held
    no answer, and reading only the last message made this check blind to it.
    """
    repeated = _call("glob", {"pattern": "**/*"})
    state = {
        "messages": [
            HumanMessage(content="plan the sprints"),
            AIMessage(content=ANSWER, id="answered"),
            AIMessage(content="", tool_calls=[dict(repeated, id="c0")], id="m1"),
            ToolMessage(content="a listing", tool_call_id="c0"),
            AIMessage(content="Let me try creating the directory.", id="m2"),
            _ai("I'll use the write approach:", [repeated]),
        ]
    }

    update = _after(state)

    assert update is not None
    assert update["jump_to"] == "end"


def test_an_answer_older_than_the_lookback_is_not_used() -> None:
    """A stage that answered at the very start and has worked since has moved
    on; stopping on that answer would discard the work."""
    from app.agents.settled_answer import ANSWER_LOOKBACK_MESSAGES

    repeated = _call("glob", {"pattern": "**/*"})
    filler = [AIMessage(content="working", id=f"f{i}") for i in range(ANSWER_LOOKBACK_MESSAGES + 5)]
    state = {
        "messages": [
            AIMessage(content=ANSWER, id="answered"),
            *filler,
            AIMessage(content="", tool_calls=[dict(repeated, id="c0")], id="m1"),
            ToolMessage(content="a listing", tool_call_id="c0"),
            _ai("still going", [repeated]),
        ]
    }

    assert _after(state) is None


# --- running out of steps -------------------------------------------------


def test_a_stage_nearing_its_ceiling_is_told_to_finish() -> None:
    """Measured on run-37476645: `specialist_testing_2` spent all three of its
    attempts in an edit-run-edit-run loop on a failing suite, using 170 tool
    calls, and never returned its answer. `specialist_ui_ux_0` used 175.

    The limit's own docstring says "60 is roughly twice the longest healthy
    stage observed across fourteen runs, so a working stage never meets it".
    That was measured against a different model and is no longer true.
    """
    from app.agents.settled_answer import _running_out_of_room

    nearly = [AIMessage(content=f"step {i}", id=f"m{i}") for i in range(45)]

    warning = _running_out_of_room(nearly, 60)

    assert "of the 60 steps" in warning
    assert "return your structured response now" in warning
    # It must say what is lost, or "hurry up" is just noise.
    assert "losing everything you have read" in warning


def test_a_stage_with_room_is_not_nagged() -> None:
    from app.agents.settled_answer import _running_out_of_room

    assert _running_out_of_room([AIMessage(content="x", id="m")], 60) == ""
    assert _running_out_of_room([AIMessage(content=f"{i}", id=f"m{i}") for i in range(20)], 60) == ""


def test_no_limit_means_no_warning() -> None:
    """The middleware is built without a limit in some call sites."""
    from app.agents.settled_answer import _running_out_of_room

    assert _running_out_of_room([AIMessage(content=f"{i}", id=f"m{i}") for i in range(90)], 0) == ""


def test_a_schema_failure_still_takes_priority() -> None:
    """A near miss is the more useful thing to say: fixing it ends the stage."""
    captured = {}

    class _Request:
        def __init__(self, messages):
            self.messages = messages

        def override(self, **changes):
            captured["messages"] = changes.get("messages", self.messages)
            return _Request(captured["messages"])

    messages = [AIMessage(content=f"step {i}", id=f"m{i}") for i in range(50)]
    messages.append(AIMessage(content='{"status": {"bad": 1}, "reason": "r"}', id="last"))

    build_settled_answer_middleware(Verdict, "specialist_testing_2", 60).wrap_model_call(
        _Request(messages), lambda r: "handled"
    )

    assert "not a valid response" in str(captured["messages"][-1])


def _budget_request(ai_messages: int):
    from langchain_core.messages import AIMessage, HumanMessage

    class Request:
        def __init__(self, messages):
            self.messages = messages
            self.response_format = None

        def override(self, **changes):
            return Request(changes.get("messages", self.messages))

    return Request(
        [HumanMessage(content="do the work")]
        + [AIMessage(content=f"turn {i}") for i in range(ai_messages)]
    )


def _run(middleware, request):
    from types import SimpleNamespace

    captured = {}

    def handler(final):
        captured["messages"] = final.messages
        return SimpleNamespace(result=[])

    middleware.wrap_model_call(request, handler)
    return captured["messages"]


def test_a_budget_warning_is_not_logged_as_a_schema_failure(caplog) -> None:
    """Both corrections shared one log line, and it named the wrong thing.

    A budget warning was reported as "sent an answer that does not satisfy its
    schema", naming whatever fields `_LAST_FAILING_FIELDS` happened to hold
    from an earlier, unrelated diagnosis - possibly from another stage, since
    that list is module-level.

    The cost was not cosmetic: the two became indistinguishable in the log, so
    "did the budget warning fire?" could not be answered from the record, and
    the schema-failure count silently absorbed every warning.
    """
    import logging

    from pydantic import BaseModel, Field

    from app.agents import settled_answer
    from app.agents.settled_answer import build_settled_answer_middleware

    class Out(BaseModel):
        summary: str = Field(..., description="x")

    # Left over from some earlier stage's diagnosis, as it would be in a worker.
    settled_answer._LAST_FAILING_FIELDS[:] = ["something.unrelated"]

    middleware = build_settled_answer_middleware(Out, "specialist_testing", 60)
    with caplog.at_level(logging.INFO):
        messages = _run(middleware, _budget_request(50))

    assert "steps this stage is allowed" in str(messages[-1])
    assert "does not satisfy its schema" not in caplog.text
    assert "something.unrelated" not in caplog.text
    assert "close to its step ceiling" in caplog.text


def test_a_schema_failure_is_still_logged_as_one(caplog) -> None:
    import logging

    from langchain_core.messages import AIMessage, HumanMessage
    from pydantic import BaseModel, Field

    from app.agents.settled_answer import build_settled_answer_middleware

    class Out(BaseModel):
        summary: str = Field(..., description="x")

    class Request:
        def __init__(self, messages):
            self.messages = messages
            self.response_format = Out

        def override(self, **changes):
            return Request(changes.get("messages", self.messages))

    request = Request(
        [HumanMessage(content="go"), AIMessage(content='{"wrong_field": 1}')]
    )

    middleware = build_settled_answer_middleware(Out, "tools_models_architect", 60)
    with caplog.at_level(logging.INFO):
        _run(middleware, request)

    assert "does not satisfy its schema" in caplog.text
    assert "close to its step ceiling" not in caplog.text
