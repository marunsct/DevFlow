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


class _NoAnswer:
    """Completes its turn but never fills `structured_response`."""

    def invoke(self, request, config=None):
        return {"messages": [SimpleNamespace(type="ai", content="## Structured Response\n" + "x" * 900)]}


def test_a_stage_that_spent_every_way_to_answer_says_so_in_its_own_error(monkeypatch):
    """Still a `ValueError`, so every handler of that is unchanged; its own class so only the sprint planner falls
    back on it."""
    from app.graph import workflow

    monkeypatch.setenv("WORKFLOW_MAX_STRUCTURED_RETRIES", "0")

    assert issubclass(workflow.StageGaveNoAnswer, ValueError)
    with pytest.raises(workflow.StageGaveNoAnswer):
        workflow._run_gated_agent(
            {"stage": "scrum_master", "repository": SimpleNamespace(root_path="/workspace")},
            {"configurable": {"thread_id": "thread-outer"}},
            stage_name="scrum_master", agent=_NoAnswer(), initial_request={"messages": []},
            output_key="sprint_plan", next_stage="technical_lead",
        )


def _the_sprint_planner_raising(tmp_path, error):
    from unittest.mock import MagicMock, patch

    from langgraph.checkpoint.memory import MemorySaver

    from app.graph.workflow import build_workflow_graph

    suite.save_criteria(tmp_path, CRITERIA)
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "technical_specification": SimpleNamespace(
            file_plan=["notes-api/app.py - the routes"], model_dump_json=lambda indent=None: "{}",
        ),
        "product_intake": SimpleNamespace(product_name="Notes API", success_measures=MEASURES, mvp_candidates=[]),
        "decisions": [],
    }
    with patch("app.graph.workflow.create_scrum_master_agent", return_value=MagicMock()), \
         patch("app.graph.workflow._run_gated_agent", side_effect=error):
        graph = build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(tmp_path))
        return graph.nodes["scrum_master"].bound.invoke(state, {"configurable": {"thread_id": "t", "run_id": "r"}})


def test_only_a_stage_that_gave_no_answer_falls_back_and_nothing_else_does(tmp_path):
    from app.graph.workflow import StageGaveNoAnswer

    update = _the_sprint_planner_raising(tmp_path, StageGaveNoAnswer("Agent 'scrum_master' gave no answer"))

    assert THE_HARNESS_S_PLAN in update["sprint_plan"].open_questions[0]
    with pytest.raises(ValueError, match="something else went wrong"):
        _the_sprint_planner_raising(tmp_path, ValueError("something else went wrong"))


def test_the_release_lists_it_among_the_gaps():
    from app.graph import delivery

    source = inspect.getsource(delivery)
    assert 'f"An escalation left this open{f\' ({accepted_at})\' if accepted_at else \'\'}: "' in source
    assert "for issue in left_open" in source
