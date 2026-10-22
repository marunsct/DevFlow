"""A run that fails must say something, whatever route it failed by.

Every deliberate route to the failure node carries an `error`. One route cannot:
`_owning_node` answers `"failed"` for a stage no node owns, which is what stops
an unrecognised stage raising `KeyError` inside LangGraph and taking the run
down with it. It is a router - it has no state to write a reason to.

So the run reached `failed_node`, which returned `{"stage": "failed"}`, and the
runner recorded `record.error = state.get("error")`: a row saying `failed` and
nothing else.

`one run` is one. Seventy-three minutes of work, approvals answered every
thirty seconds by the monitor, then `failed` at 11:53:56 with a null error, no
event explaining it and no log line. Diagnosing it meant ruling out the causes
it was not - and the stage name it had kept, `awaiting_approval:test_round_2`,
actively suggested a cause that was not the cause.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.graph import workflow as workflow_module
from app.graph.workflow import _entry_router, _owning_node


class TestTheGraphAlwaysGivesAReason:
    """Driven through the compiled graph, not by calling the closure.

    `failed_node` is defined inside `build_workflow_graph`, and reaching into a
    compiled graph's node table to pull the function out tests an assembly
    detail. Invoking the graph with an unrecognised stage exercises the actual
    path: the entry router decides, the node runs, the state comes back.
    """

    def _graph(self) -> Any:
        from langgraph.checkpoint.memory import MemorySaver

        from app.graph.checkpointing import build_serializer
        from app.graph.workflow import build_workflow_graph

        return build_workflow_graph(
            model="fake-model", checkpointer=MemorySaver(serde=build_serializer())
        )

    def _invoke(self, state: dict, thread: str) -> dict:
        return self._graph().invoke(state, {"configurable": {"thread_id": thread}})

    def test_a_stage_no_node_owns_routes_to_failure(self):
        """The behaviour that must stay: routed, not raised."""
        assert _owning_node("a_stage_that_does_not_exist") == "failed"
        assert _entry_router({"stage": "a_stage_that_does_not_exist"}) == "failed"

    def test_failing_by_that_route_records_a_reason_naming_the_stage(self):
        """What was missing: the reason.

        The node can name the stage because nothing has overwritten it yet - the
        router decided where to go and the state still carries the value it
        decided on.
        """
        final = self._invoke({"stage": "a_stage_that_does_not_exist"}, "unowned-stage")

        assert final["stage"] == "failed"
        assert "a_stage_that_does_not_exist" in final["error"]
        assert "no node owns" in final["error"]

    def test_an_error_that_is_already_set_is_not_replaced(self):
        """Every deliberate failure names its own reason and keeps it."""
        final = self._invoke(
            {"stage": "failed", "error": "the specification was rejected six times"},
            "kept-reason",
        )

        assert final["error"] == "the specification was rejected six times"

    def test_a_blank_error_counts_as_no_error(self):
        """`""` and `"   "` are what a stage sets when it means to say nothing."""
        final = self._invoke({"stage": "orphan_stage", "error": "   "}, "blank-reason")

        assert "orphan_stage" in final["error"]


class TestTheRunnerNeverStoresAFailureWithNothingInIt:
    """The second line of defence, at the point the row is written.

    The graph fix covers the graph. This covers any other path that reaches the
    same line - including a state that arrives without the key at all, which is
    how the null got into the database.
    """

    @pytest.mark.parametrize("state, expected_empty", [
        ({}, False),
        ({"error": None}, False),
        ({"error": ""}, False),
        ({"error": "a real reason"}, False),
    ])
    def test_a_failed_row_always_carries_a_reason(self, state, expected_empty):
        recorded = state.get("error") or (
            "The run failed and no reason reached the run record. Its last "
            "stage and its transcript are what remain to go on."
        )

        assert bool(recorded) is not expected_empty
        assert recorded.strip()

    def test_the_source_line_is_the_one_being_described(self):
        """Ties this test to the code, so a rewrite there is caught here.

        Asserting on a copy of an expression proves nothing about the original.
        This checks the runner really does guard that assignment, which is what
        the parametrised case above is standing in for.
        """
        import inspect

        from app.server import runner

        source = inspect.getsource(runner)

        assert 'record.error = state.get("error") or (' in source, (
            "the runner assigns record.error without a fallback again"
        )
        assert "no reason reached the run record" in source
