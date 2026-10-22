"""A criterion is planned in the earliest sprint in which a test of it can pass.

Measured on a Measure run: sprint 1 held "accounts and items survive a restart"
and sprint 2 the item routes; its only test, carrying both criteria, creates an
item, restarts and lists items. Sprint 1 spent two fix rounds on a criterion
that could not pass yet, and was planned again.
"""
from __future__ import annotations

import inspect

from app.agents.scrum_master import SprintPlanOutput, with_each_criterion_where_its_tests_can_pass
from app.graph import workflow


def _plan(*sprints):
    return SprintPlanOutput.model_validate({"sprints": [
        {"goal": f"goal {n}", "user_value": "v", "criteria": list(ids)} for n, ids in enumerate(sprints, 1)]})


def test_a_criterion_whose_every_test_proves_a_later_one_moves_to_that_sprint():
    plan, notes = with_each_criterion_where_its_tests_can_pass(
        _plan(["AC-1", "AC-7"], ["AC-3", "AC-20"]), [["AC-1"], ["AC-7", "AC-20"], ["AC-3"]])
    assert [s.criteria for s in plan.sprints] == [["AC-1"], ["AC-3", "AC-20", "AC-7"]]
    assert notes == ["AC-7 to sprint 2, where a test of it can first pass"]


def test_one_test_that_can_pass_where_it_is_keeps_it_and_sprint_1_is_never_emptied():
    plan, notes = with_each_criterion_where_its_tests_can_pass(
        _plan(["AC-1", "AC-7"], ["AC-20"]), [["AC-7"], ["AC-7", "AC-20"], ["AC-1"]])
    assert notes == [] and plan.sprints[0].criteria == ["AC-1", "AC-7"]
    plan, notes = with_each_criterion_where_its_tests_can_pass(_plan(["AC-7"], ["AC-20"]), [["AC-7", "AC-20"]])
    assert notes == [] and plan.sprints[0].criteria == ["AC-7"]


def test_the_planner_s_plan_goes_through_it():
    source = inspect.getsource(workflow)
    assert "with_each_criterion_where_its_tests_can_pass(" in source
