"""A review that passes the work over its own gating finding is sent back.

One run's architecture review graded "the specification never describes how an
existing item is edited" as **major**, then returned `approved` with no
conditions, and the run went on to sprint planning with the gap in place. Both
reviewers are told to approve or accept only when no blocking or major finding
remains; routing read `status` alone. Nothing here names a language, a
framework or a kind of product.
"""
from __future__ import annotations

from typing import Any

from app.agents.architecture_reviewer import ArchitectureReviewFinding, ArchitectureReviewOutput
from app.agents.milestone_reviewer import MilestoneReviewFinding, MilestoneReviewOutput
from app.graph.workflow import start_workflow
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    ScriptedAgents,
    _approved_review,
    _document,
    _graph,
    _intake,
    _milestone,
    _milestone_review,
    _repository,
    _script_through_architecture,
    _script_through_sprint,
    _security_review,
    _specialist,
    _spec,
    _sprint_plan,
    _stack_selector,
    _tools,
    agents,
    responds_with,
)

GAP = "The specification never describes how an existing item is edited"


def _approved_over(severity: str) -> ArchitectureReviewOutput:
    return ArchitectureReviewOutput(status="approved", findings=[ArchitectureReviewFinding(
        severity=severity, description=GAP, evidence="Data Flows lists create, toggle and delete only.",
        required_remediation="Describe the edit flow: how it starts, what it validates, what it saves.",
    )])


def test_an_approval_over_a_major_finding_goes_back_to_the_architect(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    agents.script("product_manager", [responds_with(_intake())])
    agents.script("tools_models", [responds_with(_tools())])
    agents.script("stack_selector", [responds_with(_stack_selector())])
    agents.script("principal_architect", [responds_with(_spec("first")), responds_with(_spec("with editing"))])
    agents.script("architecture_review", [responds_with(_approved_over("major")), responds_with(_approved_review())])
    _script_through_sprint(agents)

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-approved-over-major")

    assert state["stage"] == "complete", state.get("error")
    assert state["architecture_revision_count"] == 1
    assert "Describe the edit flow" in agents.last_request_text("principal_architect")


def test_an_approval_over_a_minor_finding_stands(agents: ScriptedAgents, tmp_path: Any) -> None:
    _script_through_architecture(agents, _approved_over("minor"))
    _script_through_sprint(agents)

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-approved-over-minor")

    assert state["stage"] == "complete", state.get("error")
    assert state.get("architecture_revision_count", 0) == 0


def test_an_acceptance_over_a_major_finding_goes_back_to_the_lead(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("testing")), responds_with(_milestone("testing"))])
    agents.script("specialist_testing", [responds_with(_specialist()) for _ in range(4)])
    agents.script("security_reviewer", [responds_with(_security_review()) for _ in range(2)])
    accepted_over_major = MilestoneReviewOutput(
        status="accepted",
        findings=[MilestoneReviewFinding(severity="major", category="correctness", description=GAP,
                                         required_remediation="Add the edit path and its test.")],
        acceptance_evidence="checked", documentation_reviewed=True, tests_reviewed=True,
    )
    agents.script("milestone_reviewer", [responds_with(accepted_over_major), responds_with(_milestone_review())])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-accepted-over-major")

    assert state["stage"] == "complete", state.get("error")
    assert "Add the edit path and its test." in agents.last_request_text("technical_lead")
