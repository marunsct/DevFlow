"""A run that meets the outer graph's step limit goes on from its checkpoint, and a round queues a bounded number of
fixers from every source.

Measured on one medium run: it ended "GraphRecursionError: Recursion limit of 100 reached". The limit bounds the
supersteps of one invoke, and a run with no gate is one invoke, so a sprint with many fix stages reached it with every
stage healthy; nothing in the runner caught it and the run was recorded failed. In the same runs one round queued 14
and 15 fixers from the test round and the acceptance suite: only the cross-file check's problems were capped.
"""
from __future__ import annotations

from typing import Any, TypedDict

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, StateGraph

from workflow_nodes import a_test_round, reported


class _State(TypedDict, total=False):
    document: Any
    repository: Any
    review_policy: Any
    reviewer: Any
    stage: str
    steps: int
    test_round: int


def a_long_run(*, steps_to_finish: int, steps_a_round: int | None, inner_spin_at: int | None = None):
    """A graph standing in for the workflow: one stage after another until `steps_to_finish`, a new test round every
    `steps_a_round` steps (None: never one, a loop), and a stage whose own agent spins at `inner_spin_at`."""

    def work(state: _State) -> dict[str, Any]:
        steps = int(state.get("steps") or 0) + 1
        if inner_spin_at is not None and steps == inner_spin_at:
            raise GraphRecursionError("Recursion limit of 160 reached without hitting a stop condition.")
        done = steps >= steps_to_finish
        return {
            "steps": steps,
            "stage": "complete" if done else f"defect_fix_{steps}",
            "test_round": steps // steps_a_round if steps_a_round else 0,
        }

    graph = StateGraph(_State)
    graph.add_node("work", work)
    graph.set_entry_point("work")
    graph.add_conditional_edges("work", lambda state: END if state["stage"] == "complete" else "work")
    return graph.compile(checkpointer=MemorySaver())


@pytest.fixture
def runner(run_store, redis_container, monkeypatch):
    from app.server.events import EventBus
    from app.server.redis_client import reset_clients
    from app.server.runner import WorkflowRunner

    reset_clients()
    monkeypatch.setenv("CHECKPOINTER_TYPE", "memory")
    return WorkflowRunner(EventBus(), run_store=run_store)


async def _run(runner, monkeypatch, run_id: str, graph) -> Any:
    from app.server import runner as runner_module

    monkeypatch.setattr(runner_module, "build_workflow_graph", lambda **kwargs: graph)
    record = runner.register_run(
        run_id=run_id, thread_id=f"thread-{run_id}", document_names=["brief.md"],
        document_paths=["/tmp/brief.md"], owner="alice", tenant_id="acme",
    )
    record.status = "running"
    runner.run_store.save(record)

    await runner._run_loop(record, document=None, repository=None)

    return runner.run_store.load(run_id)


async def test_a_run_past_its_step_limit_that_keeps_moving_completes(runner, monkeypatch):
    stored = await _run(runner, monkeypatch, "run-long", a_long_run(steps_to_finish=350, steps_a_round=30))

    assert stored.status == "completed"
    assert stored.error is None


async def test_a_run_that_stops_moving_is_left_paused_for_a_person(runner, monkeypatch):
    from app.server.runner import RESUMABLE_STATUSES

    stored = await _run(runner, monkeypatch, "run-loop", a_long_run(steps_to_finish=10_000, steps_a_round=None))

    assert stored.status == "paused"
    assert stored.status in RESUMABLE_STATUSES
    assert "100 steps" in stored.error and "resume" in stored.error


async def test_a_stage_s_own_agent_spinning_still_fails_the_run(runner, monkeypatch):
    stored = await _run(runner, monkeypatch, "run-spin",
                        a_long_run(steps_to_finish=350, steps_a_round=30, inner_spin_at=150))

    assert stored.status == "failed"
    assert "Recursion limit of 160" in stored.error


def test_a_stop_after_progress_goes_on_and_repeated_stops_without_it_do_not():
    from app.server.step_limit import StepLimitStops, progress_mark

    stops = StepLimitStops()
    early, later = progress_mark({"test_round": 1}), progress_mark({"test_round": 2})

    seen = [stops.go_on_after(early), stops.go_on_after(later), stops.go_on_after(later), stops.go_on_after(later)]

    assert seen == [True, True, True, False]


@pytest.mark.parametrize("before, after", [
    ({"current_sprint_index": 0}, {"current_sprint_index": 1}),
    ({"acceptance_round": 1}, {"acceptance_round": 2}),
    ({"remediation": {"defects": [{"status": "open"}]}}, {"remediation": {"defects": [{"status": "fixed"}]}}),
    ({"remediation": {"defects": [{"status": "open"}]}},
     {"remediation": {"defects": [{"status": "open", "attempts": [{"stage": "defect_fix_1_0"}]}]}}),
    ({}, {"technical_specification": {"summary": "s"}}),
])
def test_each_kind_of_forward_step_is_progress(before, after):
    from app.server.step_limit import progress_mark

    assert progress_mark(before) != progress_mark(after)


def test_a_new_stage_name_alone_is_not_progress():
    from app.server.step_limit import progress_mark

    assert progress_mark({"stage": "defect_remediation", "test_round": 3}) == progress_mark(
        {"stage": "defect_fix_3_4", "test_round": 3})


# A round's defects: at most a bounded number from every source.

def _many(source_words: str, count: int) -> list[Any]:
    """`count` defects of separate causes, each in its own file; the n-th measured by n failing tests."""
    folder = source_words.split()[0]
    return [
        reported(f"{source_words} {n}: route /{folder}{n} answers 500", affected_files=[f"src/{folder}/r{n}.ts"],
                 evidence=[{"test": f"{folder}-{n}-{k}"} for k in range(n)])
        for n in range(count)
    ]


def test_a_round_raises_at_most_ten_fixers_from_each_source(tmp_path):
    suite = _many("criterion AC", 15)
    update, _ = a_test_round(tmp_path, _many("round finding", 14), patches={
        "app.graph.acceptance_nodes.failing_due_defects": lambda state, found: suite,
    })

    raised = update["remediation"].defects
    by_source = {source: [d for d in raised if d.source == source] for source in {d.source for d in raised}}
    assert {source: len(items) for source, items in by_source.items()} == {"test round": 10, "acceptance suite": 10}
    assert "and 4 more of the same check" in by_source["test round"][-1].description
    assert "and 5 more of the same check" in by_source["acceptance suite"][-1].description


def test_the_largest_causes_keep_their_own_fixer():
    from app.agents.specialists import raised_by
    from app.graph.nodes.triage import at_most_of_each_source

    found = raised_by("acceptance suite", _many("criterion AC", 12))  # criterion n has n failing tests

    kept = at_most_of_each_source(found, most=4)

    assert [len(d.evidence) for d in kept[:3]] == [11, 10, 9]
    assert "and 8 more of the same check" in kept[3].description


def test_a_few_defects_from_each_source_are_left_as_they_are_in_their_order():
    from app.agents.specialists import raised_by
    from app.graph.nodes.triage import at_most_of_each_source

    found = [*raised_by("test round", _many("round finding", 3)), *raised_by("page check", _many("page", 2))]

    assert at_most_of_each_source(found) == found
