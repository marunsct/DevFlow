"""Parallel mode finishes a fix batch it started, and its builders get the earlier work orders' reports (LR.15).

Found in the launch review: the parallel/linear mode is read at each visit of the fix node, so switching to linear
while a batch was in flight left `fix_batch` set and never cleared, and a later parallel visit re-entered it with old
indices in a new round; and the parallel work-order builder left out what earlier work orders reported about the
files it shares, which the linear builder gives.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.specialists import SpecialistOutput
from app.graph import workflow
from app.sprint import Defect, RemediationCycle


@pytest.mark.parametrize("side_by_side", [False, True], ids=["mode-now-linear", "mode-now-parallel"])
def test_a_batch_in_flight_is_finished_whatever_the_mode_reads_now(tmp_path, monkeypatch, side_by_side):
    from workflow_node_stubs import CONFIG, compiled

    monkeypatch.setattr(workflow, "_fixes_run_side_by_side", lambda: side_by_side)
    monkeypatch.setattr(workflow, "_run_gated_agent", lambda *a, **k: pytest.fail("a batch in flight was fixed one at a time"))
    graph = compiled(monkeypatch, tmp_path)
    cycle = RemediationCycle(sprint_goal="g", defects=[
        Defect(description=f"defect {n}", severity="major", reproduction_steps="r", expected_behavior="e",
               actual_behavior="a", owner="backend") for n in (1, 2)])
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "remediation": cycle, "fix_batch": [0, 1],
             "test_round": 1, "specialist_outputs": {}}

    update = graph.nodes["defect_remediation"].bound.invoke(state, CONFIG)

    assert update == {"stage": "defect_fix_parallel"}


@pytest.mark.parametrize("parallel", [False, True], ids=["linear", "parallel"])
def test_both_builders_give_the_earlier_reports(tmp_path, monkeypatch, parallel):
    from workflow_node_stubs import marking, run_a_builder, two_work_orders

    reports = marking(monkeypatch, "app.agents.ledger.with_the_reports", "reports")
    marking(monkeypatch, "app.agents.where_things_stand.with_it", "where things stand")
    finished = {"specialist_backend_0": SpecialistOutput(changed_files=["app/shared.js"])}

    seen = run_a_builder(monkeypatch, tmp_path, parallel=parallel, specialist_outputs=finished)

    (outputs, work_order, plan), kwargs = reports[0]
    assert outputs == finished and work_order == two_work_orders().delegated_tasks[1]
    assert list(plan) == two_work_orders().delegated_tasks and kwargs == {"leave_out": "specialist_ui_ux_1"}
    content = seen.request["messages"][-1]["content"]
    assert content.index("[reports]") < content.index("[where things stand]")
