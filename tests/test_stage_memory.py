"""Per-stage counters that survive an approval pause.

Every repeat notice here counts something per stage, and every one of those
counters lived on a middleware or backend *instance*. Those instances do not
survive: with auto_approve each gated tool interrupts the graph, the workflow
node runs again from the top, and `create_specialist_agent` builds a new agent
- new middleware, new backend, empty counter.

run-454adf22 had 73 byte-identical repeated tool calls, 32% of its model calls:

    middleware query-repeat notes:      0
    middleware no-op write refusals:    0
    read withheld after five repeats:   0
    ledger command notices:             9

Nine, all from the execution ledger - the one mechanism that keeps its count in
a file. Everything in memory reported nothing, not because the checks were
wrong but because they counted to one over and over.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage

import app.agents.stage_memory as stage_memory
from app.agents.repeated_queries import build_repeated_query_middleware


@pytest.fixture(autouse=True)
def clean_memory():
    stage_memory.forget_everything()
    yield
    stage_memory.forget_everything()


@pytest.fixture()
def in_a_stage(monkeypatch):
    """Pretend to be inside a graph run, with a settable thread id."""
    import langgraph.config

    current = {"thread_id": "run-1:specialist_backend_0:abcd"}
    monkeypatch.setattr(
        langgraph.config, "get_config", lambda: {"configurable": dict(current)}
    )
    return current


def _call(middleware, name, args, content):
    request = SimpleNamespace(
        tool_call={"name": name, "args": args, "id": "c1"}, tool=None, state=None, runtime=None
    )
    return middleware.wrap_tool_call(
        request, lambda _r: ToolMessage(content=content, tool_call_id="c1")
    ).content


def test_a_count_survives_the_middleware_being_rebuilt(in_a_stage) -> None:
    """This is the whole bug: a fresh agent per approval resume."""
    args = {"path": "task-manager"}

    for _ in range(2):
        # A new middleware each time, exactly as a resume produces.
        _call(build_repeated_query_middleware(), "ls", args, "app.js")

    third = _call(build_repeated_query_middleware(), "ls", args, "app.js")

    assert "returned exactly what it returned" in third


def test_a_different_stage_counts_separately(in_a_stage) -> None:
    args = {"path": "task-manager"}
    for _ in range(3):
        _call(build_repeated_query_middleware(), "ls", args, "app.js")

    in_a_stage["thread_id"] = "run-1:specialist_testing_1:efgh"
    first_of_the_next_stage = _call(
        build_repeated_query_middleware(), "ls", args, "app.js"
    )

    assert "returned exactly what it returned" not in first_of_the_next_stage


def test_outside_a_graph_run_the_instance_keeps_its_own_count() -> None:
    """Which is what every test that builds a middleware directly relies on."""
    middleware = build_repeated_query_middleware()
    args = {"path": "p"}

    for _ in range(2):
        _call(middleware, "ls", args, "a.js")

    assert "returned exactly what it returned" in _call(middleware, "ls", args, "a.js")


def test_the_store_is_bounded(in_a_stage) -> None:
    """A worker process serves many runs and must not grow without limit."""
    for index in range(stage_memory.MAX_STAGES_REMEMBERED + 20):
        in_a_stage["thread_id"] = f"run-1:stage-{index}:x"
        stage_memory.store("repeated_queries", {})["k"] = index

    assert len(stage_memory._MEMORY) <= stage_memory.MAX_STAGES_REMEMBERED


def test_the_newest_stages_are_the_ones_kept(in_a_stage) -> None:
    for index in range(stage_memory.MAX_STAGES_REMEMBERED + 5):
        in_a_stage["thread_id"] = f"run-1:stage-{index}:x"
        stage_memory.store("q", {})["seen"] = index

    in_a_stage["thread_id"] = f"run-1:stage-{stage_memory.MAX_STAGES_REMEMBERED + 4}:x"

    assert stage_memory.store("q", {}).get("seen") is not None


def test_two_purposes_do_not_share_a_slot(in_a_stage) -> None:
    stage_memory.store("read_digests", {})["a"] = 1

    assert stage_memory.store("read_spans", {}) == {}
