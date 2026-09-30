"""A task is a work order a developer new to the codebase can follow.

The operator's plan: "a technical lead will create a detailed technical
specification that will be easy to follow for the new developer". Each task
carries its files, interfaces, steps, edge cases, test cases, verification and
what is out of scope; a plan missing what can be checked without judgement is
sent back once before anyone is dispatched; and the testing task is given the
other tasks' contracts, so tests are written against the plan, not after it.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.agents.specialists import build_specialist_task_request
from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask, build_milestone_planning_request
from app.analysis.work_orders import brief_for, contract_for_testing, readiness_problems
from app.graph.workflow import start_workflow
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    ScriptedAgents,
    _approved_review,
    _document,
    _graph,
    _milestone_review,
    _repository,
    _script_through_architecture,
    _security_review,
    _specialist,
    _sprint_plan,
    agents,
    responds_with,
)


def _order(role: str = "backend", **fields: Any) -> SpecialistTask:
    base = dict(
        specialist_role=role,
        title=f"{role} work",
        task_description=f"Do the {role} work.",
        acceptance_criteria=["works"],
        files=[f"app/{role}.src"],
        interfaces=[f"do_{role}(x) -> y"],
        steps=["one", "two"],
        edge_cases=["empty x -> refused"],
        test_cases=[f"Given x, when do_{role}, then y"],
        verification=["npm test"],
        out_of_scope=["anything else"],
    )
    base.update(fields)
    return SpecialistTask(**base)


def _plan(*tasks: SpecialistTask) -> MilestonePlanOutput:
    return MilestonePlanOutput(selected_sprint_goal="goal", delegated_tasks=list(tasks))


@pytest.fixture
def enforced(monkeypatch):
    monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "on")


@pytest.fixture
def project(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".project-directory").write_text("app", encoding="utf-8")
    return tmp_path


class TestTheDefinitionOfReady:
    def test_a_complete_plan_is_ready(self, enforced, project):
        assert readiness_problems(_plan(_order("backend"), _order("testing", test_cases=[])), project) == []

    def test_a_code_task_with_no_files_is_not_ready(self, enforced, project):
        problems = readiness_problems(_plan(_order("backend", files=[]), _order("testing")), project)
        assert any("names no `files`" in p for p in problems)

    def test_a_file_outside_the_project_is_not_ready(self, enforced, project):
        problems = readiness_problems(
            _plan(_order("backend", files=["other/x.src", "docs/notes.md"]), _order("testing")), project
        )
        assert any("outside the project directory 'app/'" in p for p in problems)
        assert any("inside docs/" in p for p in problems)

    def test_a_code_task_with_no_test_cases_is_not_ready(self, enforced, project):
        problems = readiness_problems(_plan(_order("backend", test_cases=[]), _order("testing")), project)
        assert any("no `test_cases`" in p for p in problems)

    def test_code_with_no_testing_task_is_not_ready(self, enforced, project):
        problems = readiness_problems(_plan(_order("backend")), project)
        assert any("No `testing` work order" in p for p in problems)

    def test_a_refused_verification_command_is_not_ready(self, enforced, project):
        problems = readiness_problems(
            _plan(_order("backend", verification=["node -e \"console.log(1)\""]), _order("testing")), project
        )
        assert any("`verification`" in p and "not permitted" in p for p in problems)

    def test_documentation_needs_no_files_or_cases(self, enforced, project):
        assert readiness_problems(_plan(_order("documentation", files=[], test_cases=[], verification=[])), project) == []

    def test_it_can_be_switched_off(self, monkeypatch, project):
        monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "off")
        assert readiness_problems(_plan(_order("backend", files=[])), project) == []


class TestTheBrief:
    def test_the_specialist_sees_its_whole_work_order(self, project):
        task = _order("backend")
        text = build_specialist_task_request(
            task.task_description, task.acceptance_criteria, str(project), work_order=task
        )["messages"][0]["content"]
        for heading in ("Files you own in this task", "Interfaces to implement or call",
                        "--- Steps ---", "Edge cases and the rule for each",
                        "Test cases your work will be checked against", "Verify with",
                        "Out of scope - do not change"):
            assert heading in text, heading
        assert "1. one\n2. two" in text

    def test_the_testing_task_gets_the_other_tasks_contract(self):
        code, testing = _order("backend"), _order("testing", test_cases=[])
        text = contract_for_testing(testing, [code, testing])
        assert "do_backend(x) -> y" in text
        assert "Given x, when do_backend, then y" in text
        assert contract_for_testing(code, [code, testing]) == ""

    def test_an_empty_work_order_adds_nothing(self):
        assert brief_for(SpecialistTask(specialist_role="backend", task_description="Do it.")) == ""


class TestTheLeadIsGivenWhatAWorkOrderCopies:
    def test_the_contracts_carry_over_and_lessons_reach_the_lead(self):
        from app.agents.principal_architect import TechnicalSpecificationOutput

        spec = TechnicalSpecificationOutput.model_construct(
            product_scope="x", component_boundaries=["store module owns persistence"],
            domain_model=["Item {id, title}"], api_and_event_contracts=["addItem(title) -> Item"],
            data_flows=[], testing=["unit and end-to-end"],
        )
        text = build_milestone_planning_request(
            "plan", "goal", "/", specification=spec,
            carried_forward=["An empty note cannot be edited later (sprint 1 review, minor)"],
            lessons=["`node -e` was refused 5 times"],
        )["messages"][0]["content"]
        assert "addItem(title) -> Item" in text and "Item {id, title}" in text
        assert "Carried forward from earlier sprints" in text and "`carried_forward_decisions`" in text
        assert "`node -e` was refused 5 times" in text


def test_an_unready_plan_goes_back_to_the_lead_once_with_the_reasons(
    agents: ScriptedAgents, tmp_path: Any, enforced
) -> None:
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    unready = _plan(_order("backend", files=[]))
    ready = _plan(_order("backend", files=["app/backend.src"]), _order("testing", files=["app/test.src"]))
    agents.script("technical_lead", [responds_with(unready), responds_with(ready)])
    agents.script("specialist_backend", [responds_with(_specialist())])
    agents.script("specialist_testing", [responds_with(_specialist()), responds_with(_specialist())])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-work-orders")

    assert state["stage"] == "complete", state.get("error")
    second = agents.last_request_text("technical_lead")
    assert "YOUR PREVIOUS PLAN WAS NOT READY TO HAND OUT" in second
    assert "names no `files`" in second
    assert "No `testing` work order" in second
    assert "The plan that was sent back" in second
