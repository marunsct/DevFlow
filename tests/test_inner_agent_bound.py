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

import pytest

from app.graph.workflow import (
    INNER_AGENT_RECURSION_LIMIT,
    _run_gated_agent,
    _spun_without_finishing,
)


def test_the_inner_agent_has_a_ceiling():
    assert 0 < INNER_AGENT_RECURSION_LIMIT < 100


def test_the_first_invoke_carries_it():
    source = inspect.getsource(_run_gated_agent)

    assert '"recursion_limit": INNER_AGENT_RECURSION_LIMIT' in source


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
