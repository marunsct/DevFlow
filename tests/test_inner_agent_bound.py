"""A stage that loops inside itself is unreachable to every workflow guard.

The outer workflow has had a superstep ceiling since it was written. The agent
invoked inside a stage had none, so it ran on LangGraph's default.

That matters because every guard the workflow has - the structured-response
retry, the repeat guard, the approval ceiling - is checked when a stage *ends*.
A stage that never ends meets none of them. Measured on run-2192f23b: the
principal architect spent twenty-two minutes and 184 events printing the same
specification into the conversation and re-reading the same three documents,
with zero restarts recorded. The only ceiling it would have met is the Celery
task timeout, six hours away.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.graph.workflow import (
    INNER_AGENT_RECURSION_LIMIT,
    _answer_left_in_a_spinning_stage,
    _run_gated_agent,
    _spun_without_finishing,
)


def test_the_inner_agent_has_a_ceiling():
    assert 0 < INNER_AGENT_RECURSION_LIMIT < 100


def test_the_first_invoke_carries_it():
    """The spelling moved into `_inner_agent_config`; the requirement did not.

    The config is built by a helper now, so the limit arrives as a keyword
    rather than a dict key - the assertion follows the value, not the syntax.
    """
    source = inspect.getsource(_run_gated_agent)

    assert "recursion_limit=INNER_AGENT_RECURSION_LIMIT" in source


def test_the_resume_carries_it_too():
    """A stage that loops after an approval is as unreachable as one that loops
    before it."""
    source = inspect.getsource(_run_gated_agent)

    assert "recursion_limit=INNER_AGENT_RECURSION_LIMIT" in source


def test_resume_without_a_limit_still_works():
    """Keyword-only and optional, so every existing caller keeps working."""
    from app.agents.approval import resume_with_decision

    parameters = inspect.signature(resume_with_decision).parameters
    assert parameters["recursion_limit"].default is None


@pytest.mark.parametrize(
    "message",
    [
        "Recursion limit of 60 reached without hitting a stop condition",
        "GraphRecursionError: recursion limit exceeded",
    ],
)
def test_a_spinning_stage_is_explained(message: str):
    """`GraphRecursionError` reads as a LangGraph internal. The condition has a
    plain description: the stage went round in a circle."""
    explained = _spun_without_finishing("principal_architect", RuntimeError(message))

    assert explained is not None
    assert "principal_architect" in explained
    assert "loop inside the stage itself" in explained


def test_the_explanation_says_what_to_do():
    explained = _spun_without_finishing("x", RuntimeError("recursion limit reached"))

    assert "artifacts the stage wrote are on disk" in explained
    assert "resume re-runs it on a fresh conversation" in explained


@pytest.mark.parametrize(
    "message",
    ["connection reset by peer", "This model's maximum context length is 131072 tokens"],
)
def test_an_unrelated_error_is_not_mistaken_for_a_loop(message: str):
    assert _spun_without_finishing("x", RuntimeError(message)) is None


def test_a_loop_fails_the_run_rather_than_raising():
    """The operator gets the explanation, not a stack trace."""
    source = inspect.getsource(_run_gated_agent)

    assert "_spun_without_finishing(stage_name, exc)" in source
    assert source.count("_spun_without_finishing(stage_name, exc)") == 2, (
        "both the first invoke and the resume must be covered"
    )


# --- the answer a spinning stage kept writing down ------------------------


class _Out(BaseModel):
    product_scope: str


def _ai(text: str):
    return SimpleNamespace(type="ai", content=text)


class _Spun:
    """An agent whose conversation holds the answer it never returned."""

    def __init__(self, messages):
        self._messages = messages

    def get_state(self, config):  # noqa: ARG002
        return SimpleNamespace(values={"messages": self._messages})


def test_the_answer_is_read_back_off_the_checkpoint():
    """A structured-output agent runs until the model calls the response tool.
    A model that writes the answer as text never satisfies that, so the loop
    continues and only the ceiling ends it - while the answer sits in the
    conversation the whole time.

    Measured on run-2192f23b: forty minutes, 266 events, every cycle containing
    a complete specification object printed as a chat message.
    """
    agent = _Spun([
        _ai("Let me read the intake."),
        _ai('{"product_scope": "a single-page to-do list"}\n\nNow re-reading.'),
    ])

    recovered = _answer_left_in_a_spinning_stage(agent, "t", _Out)

    assert recovered is not None
    assert recovered.product_scope == "a single-page to-do list"


def test_an_unreadable_checkpoint_is_not_worse_than_no_read():
    class Broken:
        def get_state(self, config):  # noqa: ARG002
            raise RuntimeError("no checkpoint here")

    assert _answer_left_in_a_spinning_stage(Broken(), "t", _Out) is None


def test_nothing_is_recovered_without_a_schema():
    """There is nothing to validate against, so there is no way to be sure."""
    agent = _Spun([_ai('{"product_scope": "x"}')])

    assert _answer_left_in_a_spinning_stage(agent, "t", None) is None


def test_prose_with_no_answer_recovers_nothing():
    agent = _Spun([_ai("I will now write the specification.")])

    assert _answer_left_in_a_spinning_stage(agent, "t", _Out) is None


def test_recovery_is_tried_before_the_stage_is_failed():
    """Failing a stage that spent forty minutes writing the answer down, over
    the channel it arrived on, is the waste this exists to stop."""
    source = inspect.getsource(_run_gated_agent)

    assert source.index("_answer_left_in_a_spinning_stage") < source.index(
        'return _handing_on(stage="failed", error=spun)'
    )
    assert source.count("_answer_left_in_a_spinning_stage(") == 2, (
        "both the first invoke and the resume must be covered"
    )
