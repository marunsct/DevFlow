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


def test_a_stage_under_its_budget_with_no_answer_is_left_alone() -> None:
    """The safety property for the new stop: a budget is not a deadline.

    A stage that has not answered and has not spent its budget is still
    working, and stopping it would cut short every slow-but-healthy stage.
    """
    repeated = _call("run_terminal_command", {"command": "npm test"})
    messages = [
        AIMessage(content="looking", tool_calls=[dict(repeated, id="c0")], id="first"),
        ToolMessage(content="tests failed", tool_call_id="c0"),
    ]
    messages += [_ai("running the tests again", [repeated]) for _ in range(10)]

    middleware = build_settled_answer_middleware(Verdict, "s", 40)
    assert middleware.after_model({"messages": messages}, None) is None


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


def test_a_turn_with_no_pending_call_and_no_answer_ends_on_its_own() -> None:
    """Prose with no answer in it is the model thinking out loud or asking a
    question. Nothing here has anything to say about it.
    """
    assert _after({"messages": [_ai("I will check the tests next")]}) is None


def test_an_answer_returned_as_a_message_with_no_tool_call_ends_the_stage() -> None:
    """run-519a9d8a's `specialist_testing_1` emitted its complete, valid
    response as a message and stopped calling tools - twenty times in a row.

    The answer was already there. This middleware returned None at a guard that
    assumed a turn with no pending call needs no decision, so nothing ended the
    stage and the model was asked again for something it had already given.
    """
    update = _after({"messages": [_ai(ANSWER)]})

    assert update is not None
    assert update["jump_to"] == "end"
    settled = update["messages"][0]
    assert not settled.tool_calls
    assert settled.content == ANSWER


def test_a_wrapped_answer_returned_as_a_message_ends_the_stage() -> None:
    """The same turn, with the answer under a `SpecialistOutput` key - the
    shape run-519a9d8a actually emitted. `unwrapped` handles the key once the
    message reaches `_answer_in`.
    """
    wrapped = '{"SpecialistOutput": {"status": "changes_required", "reason": "t"}}'
    update = _after({"messages": [_ai(wrapped)]})

    assert update is not None
    assert update["jump_to"] == "end"


def test_an_answer_in_a_markdown_fence_ends_the_stage() -> None:
    """The model that wrote its answer as prose with a fenced ```json block
    instead of bare JSON. `_first_json_object` already extracts the fence; the
    answer is valid, so the stage is done.
    """
    fenced = "Here is my verdict:\n\n```json\n" + ANSWER + "\n```\n"
    update = _after({"messages": [_ai(fenced)]})

    assert update is not None
    assert update["jump_to"] == "end"


def test_prose_with_no_valid_answer_and_no_tool_call_is_left_alone() -> None:
    """A schema failure is not an answer. The model is sent the validation
    errors by `wrap_model_call` and given another turn, as before.
    """
    update = _after({"messages": [_ai('{"status": "changes_required"}')]})

    assert update is None


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


# --- the run-0deeb8bf shape: a refused write is not a change ---------------


REFUSED = (
    '{"error": "Refusing to write \'final_response.json\': this content is your '
    "structured response, not an artifact. It reaches the workflow through the "
    "response schema, which is the only way it is read - a copy on disk is read "
    "by nothing and changes nothing. Nothing was written. Return your structured "
    'response now instead."}'
)


def test_a_refused_write_repeated_is_a_circle() -> None:
    """The shape that killed three runs.

    The model writes a complete, valid answer as message content and, in the
    same turn, tries to save that answer to a file. The tool refuses - a
    structured response reaches the workflow through the schema and a copy on
    disk is read by nothing - so the filesystem does not move, and the model
    does the identical thing again. Counting the refusal as a change wiped the
    record of what had already been asked, so the repeat never looked like one.
    """
    write = _call("write_artifact", {"relative_path": "final_response.json"})
    state = {
        "messages": [
            AIMessage(content=ANSWER, tool_calls=[dict(write, id="c0")], id="m0"),
            ToolMessage(content=REFUSED, tool_call_id="c0"),
            _ai(ANSWER, [write]),
        ]
    }

    update = _after(state)

    assert update is not None and update["jump_to"] == "end"


def test_a_write_that_changed_nothing_is_not_a_change_either() -> None:
    """`"status": "unchanged"` means the file already held this content."""
    write = _call("write_artifact", {"relative_path": "a/script.js"})
    read = _call("read_file", {"file_path": "/a/script.js"})
    state = {
        "messages": [
            AIMessage(content="", tool_calls=[dict(read, id="c0")], id="m0"),
            ToolMessage(content="contents", tool_call_id="c0"),
            AIMessage(content="", tool_calls=[dict(write, id="c1")], id="m1"),
            ToolMessage(content='{"status": "unchanged", "path": "a/script.js"}', tool_call_id="c1"),
            _ai(ANSWER, [read]),
        ]
    }

    update = _after(state)

    assert update is not None and update["jump_to"] == "end"


def test_a_write_that_succeeded_still_clears_the_record() -> None:
    """The false positive this must not acquire."""
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
            ToolMessage(content='{"status": "written", "lines": 40}', tool_call_id="c1"),
            _ai(ANSWER, [read]),
        ]
    }

    assert _after(state) is None


def test_a_failed_command_still_counts_as_a_change() -> None:
    """A command that exits non-zero may still have moved the filesystem.

    `npm install` can fail after writing a lockfile and half a tree. Only the
    write tools promise that a refusal wrote nothing.
    """
    read = _call("read_file", {"file_path": "/a/package-lock.json"})
    state = {
        "messages": [
            AIMessage(content="", tool_calls=[dict(read, id="c0")], id="m0"),
            ToolMessage(content="path_not_found", tool_call_id="c0"),
            AIMessage(
                content="",
                tool_calls=[_call("run_terminal_command", {"command": ["npm", "install"]}, "c1")],
                id="m1",
            ),
            ToolMessage(content='{"error": "exit 1", "stderr": "ERESOLVE"}', tool_call_id="c1"),
            _ai(ANSWER, [read]),
        ]
    }

    assert _after(state) is None


def test_a_write_whose_result_is_missing_counts_as_a_change() -> None:
    """Unknown means "assume it did something" - the cheaper mistake."""
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
            _ai(ANSWER, [read]),
        ]
    }

    assert _after(state) is None


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
    """A model narrating its work has not attempted an answer, and being told
    its prose is not JSON would interrupt a stage that is still working.
    """
    from app.agents.settled_answer import _why_it_was_not_accepted

    assert _why_it_was_not_accepted(AIMessage(content="Let me look.", id="m"), Verdict) == ""


def test_a_markdown_answer_is_corrected_on_its_shape() -> None:
    """run-519a9d8a's `specialist_testing_1` wrote its answer as Markdown to
    `docs/structured_response.md` twenty times. The write is refused for a
    reason that never mentions the answer's shape, so the model had nothing to
    correct and wrote the document again.
    """
    from app.agents.settled_answer import _why_it_was_not_accepted

    markdown = (
        "---\n## Structured Response\n\n"
        "## changed_files - `todo-app/app.js`\n"
    )
    why = _why_it_was_not_accepted(AIMessage(content=markdown, id="m"), Verdict)

    assert "Markdown document" in why
    assert "RETURNED" in why
    assert "JSON object" in why
    # The content was fine; only its shape was wrong.
    assert "the work is done, only its shape is wrong" in why


def test_a_fenced_code_block_is_corrected_too() -> None:
    """The same answer wrapped in a ```json fence is still not returned, and
    the correction must say so rather than leaving the model to guess.
    """
    from app.agents.settled_answer import _why_it_was_not_accepted

    fenced = "Here it is:\n\n```\nstatus = changes_required\n```\n"
    why = _why_it_was_not_accepted(AIMessage(content=fenced, id="m"), Verdict)

    assert why != ""
    assert "JSON object" in why


def test_an_empty_message_gets_no_correction() -> None:
    from app.agents.settled_answer import _why_it_was_not_accepted

    assert _why_it_was_not_accepted(AIMessage(content="", id="m"), Verdict) == ""


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

    assert "of the 60 model calls" in warning
    # It must say what is lost, or "hurry up" is just noise, and what it says
    # must be true of the stage reading it. See
    # `test_the_warning_describes_what_actually_happens`.
    assert "Return your structured response now" in warning


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

    assert "model calls this stage is allowed" in str(messages[-1])
    assert "does not satisfy its schema" not in caplog.text
    assert "something.unrelated" not in caplog.text
    assert "close to its model-call budget" in caplog.text


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
    assert "close to its model-call budget" not in caplog.text


def test_the_warning_arrives_with_room_left_to_act() -> None:
    """Early enough to be actable, late enough not to be noise.

    This has been got wrong twice in opposite directions. First the warning
    counted AI messages against a superstep ceiling, so seventy per cent of the
    budget was already past it and the warning fired at the very end or never -
    run-05c46508's `specialist_testing_2` died at the ceiling with `close to
    its step ceiling` appearing zero times in the log. Then it read
    `langgraph_step`, which keeps climbing across approval resumes while the
    ceiling is re-armed, so it fired from a healthy stage's eleventh call
    onward.

    Both are the same mistake: measuring the stage in a unit that is not the
    one running out.
    """
    from app.agents.settled_answer import BUDGET_WARNING_FRACTION, _running_out_of_room

    budget = 40
    at_threshold = int(budget * BUDGET_WARNING_FRACTION)

    assert _running_out_of_room(
        [AIMessage(content=f"s{i}", id=f"m{i}") for i in range(at_threshold - 1)], budget
    ) == ""
    warning = _running_out_of_room(
        [AIMessage(content=f"s{i}", id=f"m{i}") for i in range(at_threshold)], budget
    )
    assert warning != ""
    # Room left to act on it, which is the whole point of warning rather than
    # stopping.
    assert budget - at_threshold >= 10


def test_the_budget_is_counted_in_model_calls(monkeypatch) -> None:
    """Not in supersteps, and not from `langgraph_step`.

    `recursion_limit` bounds supersteps per *invoke*, and with auto-approve
    every gated tool interrupts and resumes through a fresh invoke - so that
    ceiling is re-armed each time while `langgraph_step` keeps climbing from
    the checkpoint. Reading it made the warning describe a ceiling the stage
    was not approaching.
    """
    import langgraph.config

    from app.agents.settled_answer import _model_calls_used

    monkeypatch.setattr(
        langgraph.config, "get_config", lambda: {"metadata": {"langgraph_step": 55}}
    )
    messages = [AIMessage(content=f"{i}", id=f"m{i}") for i in range(7)]
    messages.append(HumanMessage(content="not a model call"))

    assert _model_calls_used(messages) == 7


def test_a_healthy_stage_is_never_nagged(monkeypatch) -> None:
    """The cost of the old unit, measured on run-d3965815.

    `specialist_ui_ux_0` was warned at 42, 46, 50, 54, 58 and 62 "of the 60
    steps this stage is allowed", passed the ceiling it was being warned
    about, and finished normally. Six of its seventeen calls carried a message
    telling it to stop exploring and answer with what it had. The measured
    ninetieth percentile across two runs is 16 to 27 calls.
    """
    from app.agents.settled_answer import MODEL_CALLS_PER_STAGE, _running_out_of_room

    for calls in (11, 17, 27):
        messages = [AIMessage(content=f"{i}", id=f"m{i}") for i in range(calls)]
        assert _running_out_of_room(messages, MODEL_CALLS_PER_STAGE) == "", calls


def test_a_stage_that_is_circling_still_hears_about_it() -> None:
    from app.agents.settled_answer import MODEL_CALLS_PER_STAGE, _running_out_of_room

    messages = [AIMessage(content=f"{i}", id=f"m{i}") for i in range(31)]

    warning = _running_out_of_room(messages, MODEL_CALLS_PER_STAGE)

    assert "31 of the 40 model calls" in warning


# --- the answer the model put in a file -----------------------------------


def test_an_answer_in_a_pending_write_ends_the_stage() -> None:
    """Some models never put the structured response anywhere but a file.

    They call `write_artifact` with the complete, valid answer as `content`,
    the tool refuses - a structured response reaches the workflow through the
    schema, and a copy on disk is read by nothing - and they call it again.
    `settled_answer` could not help, because it looks in the message content
    and these turns have none: a tool call and no text at all.

    Three runs died here - run-0deeb8bf on `final_response.json`, run-130deeef
    on `final_output.json`, run-01f03ed9 on `docs/summary.json`, each stopped
    by the run-level repeat guard after five identical requests. run-01f03ed9
    had already completed four milestones.
    """
    import json as _json

    from app.agents.specialists import SpecialistOutput

    answer = {"changed_files": ["app.js"], "decisions": [], "tests": ["t"], "verification": []}
    write = _call("write_artifact", {"relative_path": "docs/summary.json",
                                     "content": _json.dumps(answer, indent=2)})
    state = {"messages": [HumanMessage(content="run the tests"), _ai("", [write])]}

    update = build_settled_answer_middleware(SpecialistOutput, "test_round_0").after_model(
        state, None
    )

    assert update is not None and update["jump_to"] == "end"
    assert "changed_files" in update["messages"][0].content
    assert not update["messages"][0].tool_calls, "the pending call must be dropped"


def test_an_edit_carrying_the_answer_counts_too() -> None:
    import json as _json

    from app.agents.specialists import SpecialistOutput

    answer = {"changed_files": [], "decisions": ["d"], "tests": [], "verification": []}
    edit = _call("edit_artifact", {"relative_path": "docs/x.json", "find": "{}",
                                   "replace": _json.dumps(answer)})
    state = {"messages": [_ai("", [edit])]}

    update = build_settled_answer_middleware(SpecialistOutput, "s").after_model(state, None)

    assert update is not None and update["jump_to"] == "end"


def test_an_ordinary_artifact_does_not_end_the_stage() -> None:
    """A file that is not this stage's response model is just a file."""
    from app.agents.specialists import SpecialistOutput

    write = _call("write_artifact", {"relative_path": "app/package.json",
                                     "content": '{"name": "app", "version": "1.0.0"}'})
    state = {"messages": [_ai("", [write])]}

    assert build_settled_answer_middleware(SpecialistOutput, "s").after_model(state, None) is None


def test_a_write_with_no_json_at_all_is_ignored() -> None:
    from app.agents.specialists import SpecialistOutput

    write = _call("write_artifact", {"relative_path": "app/README.md", "content": "# Hi\n"})
    state = {"messages": [_ai("", [write])]}

    assert build_settled_answer_middleware(SpecialistOutput, "s").after_model(state, None) is None


def test_a_stage_with_no_schema_is_unaffected() -> None:
    write = _call("write_artifact", {"relative_path": "docs/x.json", "content": '{"a": 1}'})
    state = {"messages": [_ai("", [write])]}

    assert build_settled_answer_middleware(None, "s").after_model(state, None) is None


# --- a truncated object is an unfinished answer, not a wrong one ----------


def test_a_missing_bracket_is_repaired_into_the_answer() -> None:
    """run-91a18470 wrote this object fifty-nine times and was refused each time.

    The `defects` array is missing its closing `]`, so the object fails one
    character from the end. Everything the schema requires is present; only the
    punctuation is unfinished.
    """
    from app.agents.specialists import SpecialistOutput

    truncated = (
        '{"changed_files": ["app.js"], "decisions": ["d"], "tests": ["t"], '
        '"verification": [], "documentation": [], "risks": [], "blockers": [], '
        '"defects": [{"description": "d", "severity": "medium", "owner": "test", '
        '"reproduction_steps": "r", "expected_behavior": "e", '
        '"actual_behavior": "a", "affected_files": ["app.js"]} }'
    )
    write = _call("write_artifact", {"relative_path": "docs/s.json", "content": truncated})

    update = build_settled_answer_middleware(SpecialistOutput, "s").after_model(
        {"messages": [_ai("", [write])]}, None
    )

    assert update is not None and update["jump_to"] == "end"


def test_repair_closes_in_the_right_order() -> None:
    """An array and an object open need `]}` not `]}` counted blindly."""
    from app.agents.settled_answer import _repair_json

    # `[` then `{` open; the object's `}` is present, the array's `]` is not.
    assert _repair_json('{"a": [1, 2}') == '{"a": [1, 2]}'


def test_repair_drops_a_closer_that_matches_nothing() -> None:
    """The truncation usually loses a closer in the middle, not at the end.

    The array's `]` goes missing while the object's `}` is still emitted, so the
    text ends in a `}` that closes nothing. Keeping it would leave the repair a
    level too deep forever.
    """
    from app.agents.settled_answer import _repair_json

    assert _repair_json('{"a": [1, 2]}') is None, "already balanced"
    # The stray `}` is dropped and the array is closed; the space it sat next to
    # is kept, because rewriting the text around it is how bytes get moved.
    assert _repair_json('{"a": [1} ') == '{"a": [1 ]}'


def test_repair_ignores_brackets_inside_strings() -> None:
    """A `]` in a value must not close an array that is still open."""
    from app.agents.settled_answer import _repair_json

    assert _repair_json('{"a": "the ] char", "b": [1') == '{"a": "the ] char", "b": [1]}'


def test_repair_closes_an_unterminated_string() -> None:
    from app.agents.settled_answer import _repair_json

    assert _repair_json('{"a": "oops') == '{"a": "oops"}'


def test_repair_gives_up_on_prose() -> None:
    from app.agents.settled_answer import _repair_json

    assert _repair_json("I have finished.") is None


def test_repair_cannot_invent_an_answer() -> None:
    """Schema validation is the real test; a repair that breaks it is discarded."""
    from app.agents.settled_answer import _answer_in

    # Balanced and valid JSON, but not this schema's answer.
    assert _answer_in(_ai('{"unrelated": 1}'), Verdict) is None
    # Truncated past usefulness: no field survives.
    assert _answer_in(_ai('{"stat'), Verdict) is None


# --- the budget, which used to threaten something that did not happen -----


def _long_state(calls: int, answered: bool = True):
    """A stage `calls` model calls deep, with a pending non-repeating call."""
    pending = _call("run_terminal_command", {"command": ["node", "--test"]})
    messages = [HumanMessage(content="build it")]
    for index in range(calls - 1):
        messages.append(
            AIMessage(content=(ANSWER if answered and index == calls - 3 else ""), id=f"m{index}")
        )
    messages.append(_ai("", [pending]))
    return {"messages": messages}


def test_a_stage_at_its_budget_with_an_answer_is_ended() -> None:
    """run-08acb1ee's `specialist_ui_ux_0` was warned on twelve consecutive
    calls - 28, 29, 30 ... 39 - ignored every one, and ended on a
    `run_terminal_command` at 40.

    Until this, `MODEL_CALLS_PER_STAGE` was read only to decide when to nag.
    Nothing stopped a stage at it, so "when they run out the stage is stopped"
    was a sentence the model was asked to act on and that was not true.
    """
    from app.agents.settled_answer import MODEL_CALLS_PER_STAGE

    middleware = build_settled_answer_middleware(Verdict, "s", MODEL_CALLS_PER_STAGE)

    update = middleware.after_model(_long_state(MODEL_CALLS_PER_STAGE + 1), None)

    assert update is not None and update["jump_to"] == "end"


def test_a_stage_at_its_budget_with_no_answer_is_ended() -> None:
    """run-1a7a62c2's `specialist_testing` had no answer and no end.

    It was told it was out of budget 71 times and kept running `npm test` for
    an hour and a half. Ending is safe here for a different reason than the
    answered case: it does not discard a finished answer, because there is
    none. What it ends is the spending, and the stage is handed to the graph's
    own recovery, which retries it on a fresh conversation and fails the run
    only once that retry budget is spent.

    This used to assert the opposite - that a stage with no answer was left
    alone - which is exactly the hole the run fell through.
    """
    from app.agents.settled_answer import MODEL_CALLS_PER_STAGE

    middleware = build_settled_answer_middleware(Verdict, "s", MODEL_CALLS_PER_STAGE)

    update = middleware.after_model(
        _long_state(MODEL_CALLS_PER_STAGE + 1, answered=False), None
    )

    assert update is not None and update["jump_to"] == "end"


def test_under_the_budget_repetition_is_still_required() -> None:
    """A stage that answered early and is still working must not be cut off."""
    from app.agents.settled_answer import MODEL_CALLS_PER_STAGE

    middleware = build_settled_answer_middleware(Verdict, "s", MODEL_CALLS_PER_STAGE)

    assert middleware.after_model(_long_state(MODEL_CALLS_PER_STAGE - 10), None) is None


def test_a_stage_with_no_budget_is_never_ended_this_way() -> None:
    middleware = build_settled_answer_middleware(Verdict, "s", 0)

    assert middleware.after_model(_long_state(200), None) is None


def test_the_warning_describes_what_actually_happens() -> None:
    """Two outcomes, and the warning has to name the one this stage is facing.

    `_decide` ends a stage at its limit *only if* an answer is already written.
    With none, nothing stops it there: it runs on to the graph's step ceiling,
    is stopped, and - with nothing to salvage - `_restart_on_a_fresh_
    conversation` starts it again from an empty conversation.

    An earlier version of this test asserted the graceful ending in both cases
    and that the restart was never mentioned. That was too broad: the restart
    does not happen for a stage that has an answer, and does happen for one
    that has not. Measured across runs 60-67, eleven stages reached the warning
    and made 61 further model calls between them, one running to 57 against a
    limit of 40 - having been told that 40 was where it ended.
    """
    from app.agents.settled_answer import _running_out_of_room

    spinning = [AIMessage(content=f"{i}", id=f"m{i}") for i in range(45)]

    # A schema to recognise an answer by, and no answer among the messages.
    warning = _running_out_of_room(spinning, 60, Verdict)

    assert "have NOT written a structured response" in warning
    assert "started again from an empty conversation" in warning
    assert "this stage ends with whatever answer you have already written" not in warning


def test_a_stage_that_has_an_answer_is_told_the_gentler_truth() -> None:
    """It really does end with that answer, so saying it would be restarted lies."""
    from app.agents.settled_answer import _running_out_of_room

    written = [
        *[AIMessage(content=f"{i}", id=f"m{i}") for i in range(45)],
        AIMessage(content=ANSWER, id="m-answer"),
    ]

    warning = _running_out_of_room(written, 60, Verdict)

    assert "already written an answer" in warning
    assert "started again from an empty conversation" not in warning


# --- the log has to name the fault, not the nearest fault ------------------


def test_a_prose_answer_is_not_reported_as_a_schema_failure():
    """Measured live on run-ed05e20e at 07:38:50.

        Stage specialist_testing sent an answer that does not satisfy its
        schema (unknown); returning the validation errors

    The stage had answered with no JSON object at all, which is a different
    fault with a different fix, and "(unknown)" was an empty field list left
    over from whatever diagnosed last. Each such call cost three and a half
    minutes on the model that was running, so a log that cannot say what to
    change is expensive.
    """
    from langchain_core.messages import AIMessage

    from app.agents import settled_answer

    why = settled_answer._why_it_was_not_accepted(
        AIMessage(content="## Changed files\n\n- app.js\n", id="m"), Verdict
    )

    assert why
    assert settled_answer._LAST_FAILURE_KIND == "no-json"
    assert settled_answer._LAST_FAILING_FIELDS == []


def test_a_schema_failure_still_names_its_fields():
    from langchain_core.messages import AIMessage

    from app.agents import settled_answer

    why = settled_answer._why_it_was_not_accepted(
        AIMessage(content='{"verdict": {"nested": true}}', id="m"), Verdict
    )

    assert why
    assert settled_answer._LAST_FAILURE_KIND == "schema"
    assert settled_answer._LAST_FAILING_FIELDS


def test_one_stages_diagnosis_does_not_describe_the_next():
    """A module-level diagnosis that survives its own call is a false report."""
    from langchain_core.messages import AIMessage

    from app.agents import settled_answer

    settled_answer._why_it_was_not_accepted(
        AIMessage(content='{"verdict": {"nested": true}}', id="m"), Verdict
    )
    assert settled_answer._LAST_FAILING_FIELDS

    settled_answer._why_it_was_not_accepted(AIMessage(content=ANSWER, id="m"), Verdict)

    assert settled_answer._LAST_FAILING_FIELDS == []
    assert settled_answer._LAST_FAILURE_KIND == ""
