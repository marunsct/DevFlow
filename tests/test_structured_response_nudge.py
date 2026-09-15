"""Ask the conversation for the answer before throwing the conversation away.

A stage that answers in prose has done the work; it failed only at the last
step. The existing remedy - restart on a fresh conversation - treats it as if
the work were lost too.

Measured on run-61c5a5b6, `test_round_0`: four files read, two globs, a
paragraph of correct analysis of `app.js`, returned as prose. The restart at
event 131 re-read the same four files and re-ran the same globs. Twenty-seven
events and five approval gates to arrive back where it already was.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.graph.workflow import (
    _STRUCTURED_RESPONSE_NUDGE,
    _answer_written_into_the_conversation,
    _nudge_for_the_structured_response,
)


class FakeAgent:
    """Records what it was invoked with and returns canned results in order."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls: list[dict] = []

    def invoke(self, request, config=None):
        self.calls.append({"request": request, "config": config or {}})
        if not self.results:
            return {"messages": []}
        return self.results.pop(0)


class ExplodingAgent:
    def invoke(self, request, config=None):  # noqa: ARG002
        raise RuntimeError("the model is having a day")


def test_a_prose_answer_is_asked_for_again_in_the_same_conversation():
    answer = object()
    agent = FakeAgent({"structured_response": answer})

    result = _nudge_for_the_structured_response(agent, "run-1:test_round_0:abcd", None)

    assert result is not None
    assert result["structured_response"] is answer


def test_the_nudge_stays_on_the_thread_that_did_the_work():
    """The whole point: the exploration above it is what we are keeping."""
    agent = FakeAgent({"structured_response": object()})

    _nudge_for_the_structured_response(agent, "run-1:test_round_0:abcd", None)

    assert agent.calls[0]["config"]["configurable"]["thread_id"] == "run-1:test_round_0:abcd"


def test_the_nudge_tells_the_model_not_to_start_over():
    """A model told only "return the structured response" redoes the task first."""
    flat = " ".join(_STRUCTURED_RESPONSE_NUDGE.split())

    assert "Do not redo the work" in flat
    assert "do not call any more tools" in flat


def test_a_nudge_that_changes_nothing_falls_through_to_the_restart():
    agent = FakeAgent({"messages": [], "structured_response": None})

    assert _nudge_for_the_structured_response(agent, "t", None) is None


def test_a_pause_raised_by_the_nudge_is_handed_back():
    """If the model answers by calling a gated tool, that pause must be honoured,
    not swallowed as "the nudge did not work"."""
    paused = {"__interrupt__": [object()], "structured_response": None}
    agent = FakeAgent(paused)

    assert _nudge_for_the_structured_response(agent, "t", None) is paused


def test_a_failed_nudge_is_not_a_failed_run():
    """The restart it precedes is still available; it must not raise past here."""
    assert _nudge_for_the_structured_response(ExplodingAgent(), "t", None) is None


def test_the_restart_still_exists_behind_it():
    """The nudge is an attempt to do better, not a replacement for the fallback."""
    import inspect

    from app.graph.workflow import _run_gated_agent

    source = inspect.getsource(_run_gated_agent)

    assert "_nudge_for_the_structured_response" in source
    assert "structured_retries" in source


def test_the_nudge_happens_once_per_node_execution():
    """Straight-line code, so it cannot become the loop it is meant to prevent."""
    import inspect

    from app.graph.workflow import _run_gated_agent

    source = inspect.getsource(_run_gated_agent)

    assert source.count("_nudge_for_the_structured_response(") == 1


def test_a_successful_nudge_is_recorded(caplog):
    """A nudge that works leaves no warning, so without this the only
    measurable trace of the mechanism is the restarts it failed to prevent."""
    import logging

    agent = FakeAgent({"structured_response": object()})

    with caplog.at_level(logging.INFO, logger="app.graph.workflow"):
        _nudge_for_the_structured_response(agent, "run-1:test_round_0:abcd", None)

    assert any("after one reminder" in record.getMessage() for record in caplog.records)


# --- the answer was there all along ---------------------------------------


class _Out(BaseModel):
    changed_files: list[str]
    decisions: list[str]


def _ai(text: str):
    return SimpleNamespace(type="ai", content=text)


def test_an_answer_printed_as_a_message_is_recovered():
    """The failure is not a model that could not answer.

    Measured on run-2b5def74: `specialist_backend_0` emitted its complete
    response object as a chat message three times - 2,027 characters, each
    followed by a sentence of commentary - and the workflow discarded all three
    and failed the stage on attempt 3 of 3.
    """
    message = _ai(
        '{\n  "changed_files": ["app.js"],\n  "decisions": ["uses findIndex"]\n}\n\n'
        "All acceptance criteria are already met in the existing code."
    )

    recovered = _answer_written_into_the_conversation({"messages": [message]}, _Out)

    assert recovered is not None
    assert recovered.changed_files == ["app.js"]


def test_trailing_prose_does_not_defeat_it():
    """`json.loads` fails with "Extra data" on an answer that is fully present."""
    import json as _json

    text = '{"changed_files": [], "decisions": ["x"]}\n\nAnd here is why.'
    with pytest.raises(ValueError):
        _json.loads(text)

    assert _answer_written_into_the_conversation({"messages": [_ai(text)]}, _Out)


def test_a_fenced_block_is_recovered():
    message = _ai('Here it is:\n```json\n{"changed_files":[],"decisions":["x"]}\n```\ndone')

    assert _answer_written_into_the_conversation({"messages": [message]}, _Out)


def test_nested_objects_do_not_truncate_the_match():
    """A brace counter that stopped at the first `}` would take half the answer."""
    message = _ai('{"changed_files": [], "decisions": ["a"], "extra": {"nested": {"deep": 1}}} tail')

    assert _answer_written_into_the_conversation({"messages": [message]}, _Out)


def test_a_brace_inside_a_string_is_not_a_brace():
    message = _ai('{"changed_files": ["a{b.js"], "decisions": ["}"]} tail')

    recovered = _answer_written_into_the_conversation({"messages": [message]}, _Out)

    assert recovered and recovered.changed_files == ["a{b.js"]


def test_json_that_is_not_the_answer_is_ignored():
    """Validated against the stage's own schema, so this recognises an answer
    rather than guessing at one."""
    assert _answer_written_into_the_conversation(
        {"messages": [_ai('{"unrelated": 1} trailing')]}, _Out
    ) is None


def test_prose_with_no_object_is_ignored():
    assert _answer_written_into_the_conversation(
        {"messages": [_ai("I have finished the task.")]}, _Out
    ) is None


def test_a_stage_with_no_schema_recovers_nothing():
    """There is nothing to validate against, so there is no way to be sure."""
    message = _ai('{"changed_files": [], "decisions": []}')

    assert _answer_written_into_the_conversation({"messages": [message]}, None) is None


def test_the_latest_answer_wins():
    """A stage that answered twice means the second one."""
    first = _ai('{"changed_files": ["old.js"], "decisions": []}')
    second = _ai('{"changed_files": ["new.js"], "decisions": []}')

    recovered = _answer_written_into_the_conversation({"messages": [first, second]}, _Out)

    assert recovered.changed_files == ["new.js"]


def test_recovery_is_tried_before_any_model_call():
    """It costs nothing; the nudge costs a turn and the restart costs a stage."""
    import inspect

    from app.graph.workflow import _run_gated_agent

    source = inspect.getsource(_run_gated_agent)

    assert source.index("_answer_written_into_the_conversation") < source.index(
        "_nudge_for_the_structured_response"
    )


def test_the_schema_travels_with_the_agent():
    """The compiled graph does not expose it, and threading it through the
    fifteen places that build an agent is how fourteen of fifteen get it."""
    import inspect

    from app.agents.role_agent import create_role_agent

    assert "agent.workflow_response_format = response_format" in inspect.getsource(
        create_role_agent
    )


# --- the nudge that says what was wrong ----------------------------------


def test_the_nudge_names_the_fields_when_the_answer_is_a_near_miss() -> None:
    """Two different failures wear the same face.

    A model that wrote a CORRECT answer as prose needs only to be told the
    channel. A model whose answer is nearly right needs to know which field is
    wrong, and "return it through the schema" produces the same near miss
    again.

    Measured on run-2c523383's `principal_architect`: the request-side
    correction fixed it mid-conversation - the turn after it fired,
    `product_scope` came back as the string the schema asks for. That turn made
    no tool call, so the stage ended, the generic nudge ran, and the restart
    threw the conversation away; the fresh one opened with the same object
    shape as before.
    """
    from langchain_core.messages import AIMessage
    from pydantic import BaseModel

    from app.graph.workflow import _nudge_text

    class Spec(BaseModel):
        product_scope: str

    near_miss = {
        "messages": [AIMessage(content='{"product_scope": {"covers": ["a"]}}')]
    }

    text = _nudge_text(near_miss, Spec)

    assert "product_scope" in text
    assert "valid string" in text


def test_a_prose_answer_still_gets_the_plain_reminder() -> None:
    """Nothing to diagnose: the model simply used the wrong channel."""
    from langchain_core.messages import AIMessage
    from pydantic import BaseModel

    from app.graph.workflow import _STRUCTURED_RESPONSE_NUDGE, _nudge_text

    class Spec(BaseModel):
        product_scope: str

    prose = {"messages": [AIMessage(content="I have finished the specification.")]}

    assert _nudge_text(prose, Spec) == _STRUCTURED_RESPONSE_NUDGE


def test_no_schema_or_no_result_falls_back_to_the_plain_reminder() -> None:
    from app.graph.workflow import _STRUCTURED_RESPONSE_NUDGE, _nudge_text

    assert _nudge_text(None, None) == _STRUCTURED_RESPONSE_NUDGE
    assert _nudge_text({"messages": []}, None) == _STRUCTURED_RESPONSE_NUDGE
