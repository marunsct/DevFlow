"""The product builds before the testing work order starts (PA.3).

Measured over three small runs: the unit-test writer was sent to a product that did not build. It had 25 writes refused
(product files, each a builder's) and its answers carried 40 blockers and 41 defects restating compiler errors, with
the fix written out - work the builder of the file had to do anyway, a stage later.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.agents.specialists import SpecialistOutput
from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.graph import workflow

BACKEND = "specialist_backend_0"
TESTING = "specialist_testing_1"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def a_plan() -> MilestonePlanOutput:
    return MilestonePlanOutput(
        selected_sprint_goal="Sprint 1: notes",
        delegated_tasks=[
            SpecialistTask(specialist_role="backend", task_description="Build the notes store",
                           acceptance_criteria=["AC-1: a note is kept"], files=["svc/main.go", "svc/store.go"]),
            SpecialistTask(specialist_role="testing", task_description="Unit tests for the notes store",
                           acceptance_criteria=["AC-1: a note is kept"], files=["svc/store_test.go"]),
        ],
    )


def a_built_plan(root: Path, **more) -> dict:
    """Every product work order handed over; the testing work order is next."""
    for name in ("main.go", "store.go"):
        (root / "svc").mkdir(exist_ok=True)
        (root / "svc" / name).write_text("package main\n")
    (root / "svc" / "go.mod").write_text("module svc\n")
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "milestone_plan": a_plan(),
        "drafted_for_plan": True,
        "current_sprint_index": 0,
        "specialist_outputs": {BACKEND: SpecialistOutput(changed_files=["svc/main.go", "svc/store.go"])},
        "specialist_task_index": 1,
        **more,
    }


@pytest.fixture()
def stages(monkeypatch):
    """Each stage the dispatcher runs, in order, with the request it was handed; model calls stubbed."""
    ran: list[tuple[str, str]] = []

    def gated(state, config, *, stage_name, initial_request, output_key, **kwargs):
        ran.append((stage_name, initial_request["messages"][-1]["content"]))
        return {output_key: SpecialistOutput(changed_files=[]), "stage": kwargs.get("next_stage")}

    monkeypatch.setenv("DELIVERY_MODE", "thorough")
    monkeypatch.setattr(workflow, "build_specialist_task_request",
                        lambda *a, **k: {"messages": [{"role": "user", "content": "the work order"}]})
    monkeypatch.setattr(workflow, "create_specialist_agent", lambda role, *a, **k: SimpleNamespace(role=role))
    monkeypatch.setattr(workflow, "_run_gated_agent", gated)
    monkeypatch.setattr("app.server.runtime_settings.effective_settings",
                        lambda: SimpleNamespace(execution_mode="linear"))
    return ran


def the_compiler_says(monkeypatch, *errors: dict) -> None:
    """The compiler, run in the sandbox (an edge), reports `errors`."""
    monkeypatch.setattr("app.analysis.compiler_check.findings", lambda *a, **k: [dict(e) for e in errors])


STORE_ERROR = {"file": "svc/store.go", "line": 4, "message": "undefined: Note", "code": "error"}


def node(root: Path, name: str, state: dict) -> dict:
    graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(root))
    return graph.nodes[name].bound.invoke(state, {"configurable": {"thread_id": "t"}})


def merged(state: dict, update: dict) -> dict:
    after = {**state, **update}
    for key in ("specialist_outputs", "unfinished_orders"):
        if key in update:
            after[key] = {**(state.get(key) or {}), **update[key]}
    return after


def test_a_product_that_does_not_build_goes_to_its_builder_before_the_testing_work_order(tmp_path, stages, monkeypatch):
    the_compiler_says(monkeypatch, STORE_ERROR)

    update = node(tmp_path, "specialist_dispatch", a_built_plan(tmp_path))

    assert stages == [], "the testing work order waits"
    assert update["stage"] == "specialist_dispatch"
    note = update["unfinished_orders"][BACKEND]
    assert "`svc/store.go` line 4: undefined: Note" in note


def test_the_builder_runs_with_the_build_s_output_and_then_the_testing_work_order(tmp_path, stages, monkeypatch):
    the_compiler_says(monkeypatch, STORE_ERROR)
    state = merged(a_built_plan(tmp_path), node(tmp_path, "specialist_dispatch", a_built_plan(tmp_path)))
    state = merged(state, node(tmp_path, "specialist_dispatch", state))  # the builder corrects it
    the_compiler_says(monkeypatch)

    node(tmp_path, "specialist_dispatch", state)

    assert [stage for stage, _ in stages] == [BACKEND, TESTING]
    assert "undefined: Note" in stages[0][1]


def test_a_product_still_failing_holds_the_testing_work_order_at_most_twice(tmp_path, stages, monkeypatch):
    the_compiler_says(monkeypatch, STORE_ERROR)
    state = a_built_plan(tmp_path)
    for _ in range(6):
        if TESTING in [stage for stage, _ in stages]:
            break
        state = merged(state, node(tmp_path, "specialist_dispatch", state))

    assert [stage for stage, _ in stages] == [BACKEND, BACKEND, TESTING]


def test_a_product_that_builds_starts_the_testing_work_order_at_once(tmp_path, stages, monkeypatch):
    the_compiler_says(monkeypatch)

    node(tmp_path, "specialist_dispatch", a_built_plan(tmp_path))

    assert [stage for stage, _ in stages] == [TESTING]


def test_an_error_in_a_test_file_does_not_hold_the_testing_work_order(tmp_path, stages, monkeypatch):
    the_compiler_says(monkeypatch, {"file": "svc/store_test.go", "line": 2, "message": "undefined: make", "code": "e"})

    node(tmp_path, "specialist_dispatch", a_built_plan(tmp_path))

    assert [stage for stage, _ in stages] == [TESTING]


def test_in_parallel_mode_the_testing_work_order_waits_for_the_builder(tmp_path, stages, monkeypatch):
    the_compiler_says(monkeypatch, STORE_ERROR)
    state = a_built_plan(tmp_path)
    state = merged(state, node(tmp_path, "specialist_gather", state))

    sent = workflow._route_from_stage(state)

    assert [send.arg["__worker_index"] for send in sent] == [0]
    assert "undefined: Note" in state["unfinished_orders"][BACKEND]


def test_the_note_a_builder_reads_avoids_the_banned_words(tmp_path, stages, monkeypatch):
    the_compiler_says(monkeypatch, STORE_ERROR)

    note = node(tmp_path, "specialist_dispatch", a_built_plan(tmp_path))["unfinished_orders"][BACKEND]

    assert not BANNED.findall(re.sub(r"`[^`]*`", "", note))
