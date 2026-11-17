"""The build model's server bounds the context window and each fan-out (Initiatives M.1, O.2, AB).

Measured across runs: forty-odd calls refused with "Context size has been
exceeded" at 20,000-48,000 input tokens under a 100,000-token setting, in
parallel waves on a server that splits its context across its slots.
"""

from __future__ import annotations

import pytest

from app.models import server_profile
from app.models.server_profile import ServerProfile, from_props


@pytest.fixture(autouse=True)
def _clean():
    server_profile.forget()
    yield
    server_profile.forget()


def _recorded(profile: ServerProfile) -> None:
    server_profile._RECORDED = profile


def test_props_give_slots_slot_context_and_quantisation() -> None:
    profile = from_props({
        "total_slots": 4,
        "default_generation_settings": {"n_ctx": 32768},
        "model_path": "/models/Some-Model-30B-Q4_K_M.gguf",
    })
    assert (profile.slots, profile.slot_context, profile.quantisation, profile.bits) == (4, 32768, "Q4_K_M", 4)
    assert "4-bit" in profile.advisory()


def test_a_path_with_no_quantisation_names_none_and_warns_of_nothing() -> None:
    profile = from_props({"total_slots": 1, "default_generation_settings": {"n_ctx": 126464},
                          "model_path": "org/Model-35B-GGUF"})
    assert profile.quantisation == "" and profile.advisory() == ""
    assert from_props({"model_path": "x-Q8_0.gguf"}).advisory() == ""


def test_the_window_is_no_larger_than_a_slot_s_context() -> None:
    from app.agents.context_budget import context_window

    env = {"MODEL_CONTEXT_WINDOW": "100000"}
    assert context_window(env) == 100000
    _recorded(ServerProfile(slots=4, slot_context=32768))
    assert context_window(env) == 32768
    _recorded(ServerProfile(slots=1, slot_context=200000))
    assert context_window(env) == 100000


def test_a_fan_out_is_no_wider_than_the_server_s_slots(monkeypatch) -> None:
    from app.graph.workflow import concurrent_requests, max_parallel

    monkeypatch.setenv("HARNESS_MAX_PARALLEL", "6")
    assert concurrent_requests() == 6
    _recorded(ServerProfile(slots=2))
    assert concurrent_requests() == 2
    assert max_parallel() == 6  # whether to fan out at all is still the owner's setting


def _four_apart():
    from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask

    return MilestonePlanOutput(selected_sprint_goal="g", review_task_assignments=["change -> task 1"], delegated_tasks=[
        SpecialistTask(specialist_role="backend", task_description=f"write part {n}", acceptance_criteria=["works"],
                       files=[f"app/part{n}.js"]) for n in range(4)])


def test_the_fan_outs_use_the_capped_width(tmp_path, monkeypatch) -> None:
    """Work orders, reviews and fixes side by side: as many as the server has slots, not as many as allowed."""
    from types import SimpleNamespace

    from app.graph import workflow
    from app.sprint import Defect, RemediationCycle

    monkeypatch.setenv("HARNESS_MAX_PARALLEL", "6")
    _recorded(ServerProfile(slots=2))
    root = SimpleNamespace(root_path=str(tmp_path))

    builders = workflow._route_from_stage({"stage": "specialist_dispatch_parallel", "repository": root,
                                           "milestone_plan": _four_apart(), "specialist_outputs": {}})
    reviews = workflow._route_from_stage({"stage": "review_parallel", "repository": root,
                                          "reviews_in_flight": ["security", "ux", "db", "backend"]})
    cycle = RemediationCycle(sprint_goal="g", defects=[
        Defect(description=f"part {n} fails", severity="major", reproduction_steps="r", expected_behavior="e",
               actual_behavior="a", owner="backend", affected_files=[f"app/part{n}.js"]) for n in range(4)])
    fixes = workflow._defects_to_fix_together(cycle, [0, 1, 2, 3])

    assert [send.node for send in builders] == ["specialist_worker"] * 2
    assert [send.node for send in reviews] == ["review_worker"] * 2
    assert len(fixes) == 2


def test_the_drafts_use_the_capped_width(tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace

    from workflow_node_stubs import run_node

    monkeypatch.setenv("HARNESS_MAX_PARALLEL", "6")
    _recorded(ServerProfile(slots=2))
    widths = []

    def draft_work_orders(*args, workers: int, **kwargs):
        widths.append(workers)
        return {}

    run_node(monkeypatch, tmp_path, "specialist_dispatch", milestone_plan=_four_apart(),
             technical_specification=SimpleNamespace(), overrides={
                 "app.delivery.fast": lambda *a, **k: True,
                 "app.graph.workflow._the_run_approves_its_own_writes": lambda run_id: True,
                 "app.graph.drafting.with_tests_the_specification_plans": lambda tasks, spec: (tasks, []),
                 "app.graph.drafting.in_work_orders_of_at_most": lambda tasks: (tasks, 0),
                 "app.graph.best_attempt.files_the_best_attempt_already_has": lambda *a, **k: [],
                 "app.graph.drafting.draft_work_orders": draft_work_orders,
             })

    assert widths == [2]


def test_each_run_segment_reads_the_profile_and_ready_prints_it() -> None:
    import inspect
    from pathlib import Path

    from app.server import tasks

    assert "server_profile.record()" in inspect.getsource(tasks.execute_workflow_run)
    ready = (Path(__file__).resolve().parents[1] / "scripts" / "loop" / "model_ready.py").read_text()
    assert "from app.models.server_profile import read" in ready and "ADVISORY" in ready


def test_no_server_records_nothing(monkeypatch) -> None:
    assert server_profile.read("") is None
    assert server_profile.read("http://127.0.0.1:9/v1") is None
