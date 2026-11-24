"""Sprints are sized by their work, not only capped by their count (LF.1315).

Measured on a medium brief in thorough delivery, 13 criteria and up to 3 sprints allowed: the sprint plan put every
criterion in sprint 1 and none in sprint 2. The first medium run failed on the same shape - one sprint holding most of
the product - and the suite written a sprint at a time gives nothing when one sprint holds everything. A plan with a
sprint over the limit, or one with no criterion, is sent back once with the reason; a second such plan is split by
the harness in plan order. Fast delivery's single sprint is left as it is.
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.agents.scrum_master import (
    SprintDefinition,
    SprintPlanOutput,
    build_sprint_planning_request,
    sprints_not_sized_by_work,
    with_sprints_sized_by_work,
)

ALL_13 = [f"AC-{n}" for n in range(1, 14)]
TEXTS = {item: f"Criterion {item.split('-')[1]} of the product" for item in ALL_13}


def _sprint(goal: str, criteria: list[str], **fields) -> SprintDefinition:
    return SprintDefinition(goal=goal, user_value="v", criteria=criteria, **fields)


def _plan(*sprints: SprintDefinition, coverage: list[str] | None = None) -> SprintPlanOutput:
    return SprintPlanOutput(sprints=list(sprints), success_measure_coverage=coverage or [])


def _everything_in_sprint_one() -> SprintPlanOutput:
    """The measured plan: sprints [[AC-1..AC-13], []]."""
    return _plan(
        _sprint("Users sign up and manage the whole product", ALL_13,
                in_scope=["Sign-up and sign-in", "AC-12: export", "AC-13 report page"],
                acceptance_criteria=[f"{item}: passes" for item in ALL_13],
                test_strategy=["AC-13: report page test", "Run the suite"]),
        _sprint("Polish", [], in_scope=["Final styling"]),
        coverage=["1: Sprint 1", "2: Sprint 2"],
    )


def _criteria_by_sprint(plan) -> list[list[str]]:
    return [list(sprint.criteria) for sprint in plan.sprints]


class TestTheSizeCheck:
    def test_the_measured_plan_is_not_sized(self):
        notes = sprints_not_sized_by_work(_everything_in_sprint_one(), 13)

        assert len(notes) == 2
        assert "Sprint 1 holds 13 criteria" in notes[0] and "at most 6" in notes[0]
        assert "Sprint 2 holds no criterion" in notes[1]

    def test_a_good_three_sprint_plan_is_sized(self):
        plan = _plan(_sprint("a", ALL_13[:5]), _sprint("b", ALL_13[5:10]), _sprint("c", ALL_13[10:]))

        assert sprints_not_sized_by_work(plan, 13) == []

    def test_fast_deliverys_single_sprint_of_twelve_has_no_limit(self):
        plan = _plan(_sprint("all", ALL_13[:12]))

        assert sprints_not_sized_by_work(plan, 12, fast=True) == []

    def test_where_the_allowed_sprints_cannot_hold_six_each_the_limit_is_the_even_share(self):
        """Fast delivery allows 2 sprints for 30 criteria: 15 each is a plan that can be met."""
        ids = [f"AC-{n}" for n in range(1, 31)]

        assert sprints_not_sized_by_work(_plan(_sprint("a", ids[:15]), _sprint("b", ids[15:])), 30, fast=True) == []
        assert sprints_not_sized_by_work(_plan(_sprint("a", ids[:20]), _sprint("b", ids[20:])), 30, fast=True)


class TestTheSplit:
    def test_the_measured_plan_is_split_in_plan_order_with_no_empty_sprint(self):
        plan, notes = with_sprints_sized_by_work(_everything_in_sprint_one(), 13, texts=TEXTS)

        assert _criteria_by_sprint(plan) == [ALL_13[:5], ALL_13[5:10], ALL_13[10:]]
        assert notes

    def test_the_items_naming_only_moved_criteria_move_with_them(self):
        plan, _ = with_sprints_sized_by_work(_everything_in_sprint_one(), 13, texts=TEXTS)
        first, second, third = plan.sprints

        assert first.acceptance_criteria == [f"{item}: passes" for item in ALL_13[:5]]
        assert third.acceptance_criteria == [f"{item}: passes" for item in ALL_13[10:]]
        assert "AC-13 report page" in third.in_scope and "AC-13 report page" not in first.in_scope
        assert "AC-13: report page test" in third.test_strategy
        # Naming no criterion, it stays where the plan put it.
        assert "Sign-up and sign-in" in first.in_scope
        assert "Run the suite" in first.test_strategy

    def test_a_sprint_split_off_depends_on_the_one_it_continues(self):
        plan, _ = with_sprints_sized_by_work(_plan(_sprint("all", ALL_13[:8]), _sprint("rest", ALL_13[8:])), 13)

        assert _criteria_by_sprint(plan) == [ALL_13[:5], ALL_13[5:10], ALL_13[10:]]
        assert plan.sprints[2].dependencies == ["Sprint 2"]

    def test_an_empty_sprint_is_folded_and_the_numbers_follow(self):
        plan = _plan(
            _sprint("a", ALL_13[:5]), _sprint("b", [], in_scope=["Shared layout"]),
            _sprint("c", ALL_13[5:10], dependencies=["Sprint 2"]),
            coverage=["1: Sprint 1", "2: Sprint 3"],
        )

        shaped, notes = with_sprints_sized_by_work(plan, 13)

        assert _criteria_by_sprint(shaped) == [ALL_13[:5], ALL_13[5:10]]
        assert shaped.sprints[1].in_scope == ["Shared layout"]
        assert shaped.sprints[1].dependencies == []
        assert shaped.success_measure_coverage == ["1: Sprint 1", "2: Sprint 2"]
        assert notes

    @pytest.mark.parametrize("plan, count, fast", [
        (_plan(_sprint("all", ALL_13[:12])), 12, True),
        (_plan(_sprint("a", ALL_13[:5]), _sprint("b", ALL_13[5:10]), _sprint("c", ALL_13[10:])), 13, False),
    ], ids=["fast single sprint of 12", "good three-sprint plan"])
    def test_a_plan_already_sized_comes_back_as_it_came(self, plan, count, fast):
        shaped, notes = with_sprints_sized_by_work(plan, count, fast=fast)

        assert shaped == plan
        assert notes == []


class TestThePlanningRequest:
    def test_a_re_plan_names_the_sprints_not_sized(self, tmp_path):
        notes = sprints_not_sized_by_work(_everything_in_sprint_one(), 13)

        body = build_sprint_planning_request("spec", str(tmp_path), unsized=notes)["messages"][0]["content"]

        assert "NOT SIZED BY THEIR WORK" in body
        assert "Sprint 1 holds 13 criteria" in body

    def test_the_standing_limit_is_given_where_more_than_one_sprint_is_allowed(self, monkeypatch):
        from app.agents import scrum_master

        monkeypatch.setenv("DELIVERY_MODE", "thorough")
        assert "No sprint holds more than 6 criteria" in scrum_master._how_many_sprints(" ".join(ALL_13))
        monkeypatch.setenv("DELIVERY_MODE", "fast")
        assert "No sprint holds more than" not in scrum_master._how_many_sprints(" ".join(ALL_13[:12]))

    def test_the_new_words_name_no_product(self, monkeypatch):
        from app.agents import scrum_master

        monkeypatch.setenv("DELIVERY_MODE", "thorough")
        text = (
            scrum_master._not_sized_by_work(sprints_not_sized_by_work(_everything_in_sprint_one(), 13))
            + scrum_master._how_many_sprints(" ".join(ALL_13))
        ).lower()

        for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
            assert not re.search(rf"\b{re.escape(word)}\b", text), word


def _the_scrum_master(tmp_path, monkeypatch, plan: SprintPlanOutput, state: dict | None = None) -> tuple[dict, list]:
    """The scrum master node on a thorough run of 13 criteria, its planner answering `plan`; the update and requests."""
    from app.acceptance import suite
    from app.acceptance.criteria import Criterion
    from workflow_nodes import a_specification, run_node

    monkeypatch.setenv("DELIVERY_MODE", "thorough")
    monkeypatch.setattr(suite, "criteria", lambda root: [
        Criterion(id=item, text=TEXTS[item], source="brief") for item in ALL_13
    ])
    monkeypatch.setattr(suite, "deferred", lambda root: {})
    requests: list[str] = []

    def gated(state, config, *, initial_request, output_key, **kwargs):
        requests.append(initial_request["messages"][-1]["content"])
        return {output_key: plan, "stage": "technical_lead"}

    update = run_node("scrum_master", {
        "repository": SimpleNamespace(root_path=str(tmp_path)), "technical_specification": a_specification(),
        "product_intake": {"product_name": "Notes"}, **(state or {}),
    }, str(tmp_path), {
        "app.graph.workflow.create_scrum_master_agent": lambda **kwargs: MagicMock(),
        "app.graph.workflow._run_gated_agent": gated,
    })
    return update, requests


class TestTheScrumMaster:
    def test_the_measured_plan_is_sent_back_once_with_the_reason(self, tmp_path, monkeypatch):
        update, _ = _the_scrum_master(tmp_path, monkeypatch, _everything_in_sprint_one())

        assert update["stage"] == "scrum_master"
        assert any("Sprint 1 holds 13 criteria" in note for note in update["sprint_plan_unsized"])

    def test_a_second_such_plan_is_split_by_the_harness(self, tmp_path, monkeypatch):
        first, _ = _the_scrum_master(tmp_path, monkeypatch, _everything_in_sprint_one())

        update, requests = _the_scrum_master(
            tmp_path, monkeypatch, _everything_in_sprint_one(),
            state={"sprint_plan_unsized": first["sprint_plan_unsized"]},
        )

        assert "Sprint 1 holds 13 criteria" in requests[0]
        assert update["stage"] != "scrum_master"
        sizes = [len(ids) for ids in _criteria_by_sprint(update["sprint_plan"])]
        assert sizes == [5, 5, 3]
        assert update["sprint_plan_unsized"] == []
        assert "split by the harness" in update["decisions"][-1]["rationale"]

    def test_a_good_plan_goes_on_as_it_came(self, tmp_path, monkeypatch):
        plan = _plan(_sprint("a", ALL_13[:5]), _sprint("b", ALL_13[5:10]), _sprint("c", ALL_13[10:]))

        update, requests = _the_scrum_master(tmp_path, monkeypatch, plan)

        assert len(requests) == 1
        assert update["stage"] != "scrum_master"
        assert _criteria_by_sprint(update["sprint_plan"]) == _criteria_by_sprint(plan)
