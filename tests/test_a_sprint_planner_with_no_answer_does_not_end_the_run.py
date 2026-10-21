"""A sprint planner that spends every way to answer gives way to one sprint over every criterion (owner 2026-10-21).

A fix, build or test stage that cannot answer is recorded as blocked and the
run goes on; a planning stage that could not ended the run - one run's sprint
planner did, after six replies. The harness writes the plain plan fast delivery
mostly ends with anyway, from its own inputs, and says it is the harness's: in
the decision log, and in the release's gaps.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.acceptance.criteria import Criterion
from app.agents.scrum_master import (
    THE_HARNESS_S_PLAN,
    a_plan_the_harness_writes,
    how_much_a_plan_leaves_out,
)

CRITERIA = [Criterion("AC-1", "A note can be created with a title and a body", "brief"),
            Criterion("AC-2", "Notes survive a restart", "brief")]
MEASURES = ["Users can add, edit, and delete notes without errors", "Notes persist across restarts"]


def test_the_harness_s_plan_covers_every_criterion_and_measure_and_says_whose_it_is():
    plan = a_plan_the_harness_writes(CRITERIA, MEASURES, ["notes-api/app.py - the routes"], "Notes API")

    (sprint,) = plan.sprints
    assert sprint.criteria == ["AC-1", "AC-2"]
    assert "notes-api/app.py - the routes" in sprint.in_scope
    assert plan.success_measure_coverage == ["1: Sprint 1", "2: Sprint 1"]
    assert how_much_a_plan_leaves_out(plan, MEASURES) == 0
    assert THE_HARNESS_S_PLAN in plan.open_questions[0]


def test_the_stage_goes_on_with_it_recorded_as_a_decision_and_a_gap(tmp_path):
    from app.graph.workflow import _the_harness_s_sprint_plan

    suite.save_criteria(tmp_path, CRITERIA)
    state = {
        "technical_specification": SimpleNamespace(file_plan=["notes-api/app.py - the routes"]),
        "product_intake": SimpleNamespace(product_name="Notes API"),
        "known_issues": ["an earlier issue"],
        "decisions": [],
    }

    update = _the_harness_s_sprint_plan(state, MEASURES, str(tmp_path),
                                        "Agent 'scrum_master' wrote replies that ran to the output limit\nmore")

    assert update["stage"] == "technical_lead" and update["sprint_plan"].sprints[0].criteria == ["AC-1", "AC-2"]
    assert update["known_issues"][0] == "an earlier issue"
    assert THE_HARNESS_S_PLAN in update["known_issues"][1] and "ran to the output limit" in update["known_issues"][1]
    assert update["decisions"][-1]["decision"] == THE_HARNESS_S_PLAN


def test_only_a_stage_that_gave_no_answer_falls_back_and_nothing_else_does():
    from app.graph import workflow

    assert issubclass(workflow.StageGaveNoAnswer, ValueError)
    gated = inspect.getsource(workflow._run_gated_agent)
    assert "raise StageGaveNoAnswer(" in gated and "raise ValueError(\n                _missing_structured_response" not in gated
    graph = inspect.getsource(workflow.build_workflow_graph)
    planner = graph[graph.index("def scrum_master_node"):]
    planner = planner[:planner.index("\n    def ", 10)]
    assert "except StageGaveNoAnswer as gave_none:" in planner and "except ValueError" not in planner


def test_the_release_lists_it_among_the_gaps():
    from app.graph import delivery

    source = inspect.getsource(delivery)
    assert 'f"An escalation left this open: {issue}" for issue in state.get("known_issues")' in source
