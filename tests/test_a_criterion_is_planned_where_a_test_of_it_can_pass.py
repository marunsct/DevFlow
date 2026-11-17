"""A criterion is planned in the earliest sprint in which a test of it can pass.

Measured on a Measure run: sprint 1 held "accounts and items survive a restart"
and sprint 2 the item routes; its only test, carrying both criteria, creates an
item, restarts and lists items. Sprint 1 spent two fix rounds on a criterion
that could not pass yet, and was planned again.
"""
from __future__ import annotations

from app.agents.scrum_master import SprintPlanOutput, with_each_criterion_where_its_tests_can_pass


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


def test_the_planner_s_plan_goes_through_it(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from workflow_node_stubs import run_node

    given = []

    def moved(plan, tests):
        given.append(tests)
        return _plan(["AC-1"], ["AC-3", "AC-7"]), ["AC-7 to sprint 2, where a test of it can first pass"]

    criteria = [SimpleNamespace(id=n, text=f"criterion {n}") for n in ("AC-1", "AC-3", "AC-7")]
    seen = run_node(
        monkeypatch, tmp_path, "scrum_master", answer=_plan(["AC-1", "AC-7"], ["AC-3"]),
        technical_specification="The specification.", overrides={
            "app.acceptance.suite.criteria": lambda root: criteria,
            "app.acceptance.suite.deferred": lambda root: {},
            "app.acceptance.suite.declared_tests": lambda root: [("a.spec.ts", "[AC-1] [AC-7] lists what was saved"),
                                                                 ("b.spec.ts", "[AC-3] deletes")],
            "app.agents.scrum_master.with_each_criterion_where_its_tests_can_pass": moved,
        })

    assert given == [[["AC-1", "AC-7"], ["AC-3"]]]
    assert [s.criteria for s in seen.update["sprint_plan"].sprints] == [["AC-1"], ["AC-3", "AC-7"]]


def test_only_the_moves_that_would_empty_sprint_1_are_dropped():
    plan, notes = with_each_criterion_where_its_tests_can_pass(
        _plan(["AC-1"], ["AC-2", "AC-3"], ["AC-4"]), [["AC-1", "AC-2"], ["AC-3", "AC-4"]])
    assert [s.criteria for s in plan.sprints] == [["AC-1"], ["AC-2"], ["AC-4", "AC-3"]]
    assert notes == ["AC-3 to sprint 3, where a test of it can first pass"]
