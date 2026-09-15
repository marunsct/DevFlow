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

import pytest

from app.graph.workflow import (
    _STRUCTURED_RESPONSE_NUDGE,
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
