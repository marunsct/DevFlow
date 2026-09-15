"""Tests for the top-level LangGraph controller: routing, gates, and resume.

These tests never call a model. Every role agent is replaced with a scripted
fake, so what is being tested is exactly the controller's own job: which node
runs next, what a rejected review sends back to the architect, how a paused run
resumes, and where the bounded loops stop. That separation matters - the role
agents already have their own contract tests, and a test that needed a live LLM
could not assert deterministic routing anyway.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pytest
from langgraph.graph import END

from app.agents.approval import approve_write_decision, reject_write_decision
from app.agents.architecture_reviewer import ArchitectureReviewFinding, ArchitectureReviewOutput
from app.agents.principal_architect import TechnicalSpecificationOutput
from app.agents.product_manager import ProductManagerOutput
from app.agents.scrum_master import SprintDefinition, SprintPlanOutput
from app.agents.specialists import ReportedDefect, SpecialistOutput
from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.agents.tools_models import ToolsAndModelsOutput
from app.documents import DocumentContent
from app.graph import workflow as workflow_module
from app.graph.checkpointing import build_checkpointer
from app.graph.workflow import (
    MAX_ARCHITECTURE_REVISIONS,
    MAX_SPECIFICATION_REPAIRS,
    SPECIFICATION_REVIEW,
    SPRINT_REVIEW,
    _entry_router,
    _route_from_stage,
    approve_decision,
    build_workflow_graph,
    request_changes_decision,
    resume_pending_approval,
    resume_pending_review,
    skip_decision,
    start_workflow,
)
from app.state import RepositoryContext, ReviewRequestStatus

# --------------------------------------------------------------------------
# Scripted fakes standing in for the role agents
# --------------------------------------------------------------------------


class _FakeInterrupt:
    """Minimal stand-in for a LangGraph interrupt payload.

    `app.agents.approval.extract_pending_approval` reads only `.id` and
    `.value["action_requests"][0]`, so reproducing that shape is enough to
    exercise the real approval-extraction path without a real agent pausing.
    """

    def __init__(self, relative_path: str, content: str) -> None:
        self.id = f"interrupt-{relative_path}"
        self.value = {
            "action_requests": [
                {"name": "write_artifact", "args": {"relative_path": relative_path, "content": content}}
            ]
        }


def pause_for_approval(relative_path: str = "intake.md", content: str = "draft") -> dict[str, Any]:
    """Build a fake agent result meaning 'I paused, a human must approve a write'."""
    return {"__interrupt__": [_FakeInterrupt(relative_path, content)]}


def responds_with(structured: Any) -> dict[str, Any]:
    """Build a fake agent result meaning 'I finished, here is my structured output'."""
    return {"structured_response": structured}


class ScriptedAgents:
    """A registry of canned responses and a record of what each role was asked.

    Tests declare, per role, the sequence of results its agent should return.
    Every request the controller sends is recorded, which is how the tests below
    assert that a rejected specification actually carries the reviewer's
    findings back to the architect rather than silently re-sending the original
    brief.
    """

    def __init__(self) -> None:
        self.scripts: dict[str, list[dict[str, Any]]] = {}
        self.requests: dict[str, list[Any]] = defaultdict(list)

    def script(self, role: str, responses: list[dict[str, Any]]) -> None:
        self.scripts[role] = list(responses)

    def agent(self, role: str) -> "_FakeAgent":
        return _FakeAgent(role, self)

    def last_request_text(self, role: str) -> str:
        """Return the text of the most recent `{"messages": [...]}` request for a role."""
        payload = self.requests[role][-1]
        return payload["messages"][0]["content"]


class _FakeAgent:
    """One role's fake agent: records the request, returns the next scripted result."""

    def __init__(self, role: str, registry: ScriptedAgents) -> None:
        self.role = role
        self.registry = registry

    def invoke(self, payload: Any, config: Any = None) -> dict[str, Any]:  # noqa: ARG002
        print(f"INVOKING {self.role}")
        self.registry.requests[self.role].append(payload)
        script = self.registry.scripts.get(self.role)
        if not script:
            raise AssertionError(f"Role '{self.role}' was invoked with no scripted response left.")
        return script.pop(0)


@pytest.fixture
def agents(monkeypatch: pytest.MonkeyPatch) -> ScriptedAgents:
    """Replace every role-agent factory in the controller with a scripted fake."""
    registry = ScriptedAgents()

    simple_roles = {
        "create_product_manager_agent": "product_manager",
        "create_tools_models_agent": "tools_models",
        "create_principal_architect_agent": "principal_architect",
        "create_architecture_reviewer_agent": "architecture_review",
        "create_scrum_master_agent": "scrum_master",
        "create_technical_lead_agent": "technical_lead",
        "create_milestone_reviewer_agent": "milestone_reviewer",
        "create_security_reviewer_agent": "security_reviewer",
        "create_stack_selector_agent": "stack_selector",
    }
    for factory_name, role in simple_roles.items():
        monkeypatch.setattr(
            workflow_module,
            factory_name,
            lambda *args, _role=role, **kwargs: registry.agent(_role),
        )

    monkeypatch.setattr(
        workflow_module,
        "create_specialist_agent",
        lambda role, *args, **kwargs: registry.agent(f"specialist_{role}"),
    )
    
    import app.scaffolding.executor
    monkeypatch.setattr(
        app.scaffolding.executor,
        "execute_scaffolding",
        lambda repo_root, app_name, framework: (True, "Scaffolding succeeded")
    )
    
    import app.build.verifier
    monkeypatch.setattr(
        app.build.verifier.BuildVerifier,
        "verify",
        lambda self, command, role_name: type('Result', (), {'success': True, 'stdout': '', 'stderr': '', 'errors': []})()
    )
    
    import app.analysis.static_analyzer
    monkeypatch.setattr(
        app.analysis.static_analyzer.StaticAnalyzer,
        "analyze",
        lambda self, role_name: type('Result', (), {'success': True, 'stdout': '', 'stderr': '', 'errors': []})()
    )
    return registry


# --------------------------------------------------------------------------
# Sample structured outputs
# --------------------------------------------------------------------------


def _intake() -> ProductManagerOutput:
    return ProductManagerOutput(product_name="Acme Scheduling")


def _tools() -> ToolsAndModelsOutput:
    return ToolsAndModelsOutput()


def _spec(scope: str = "MVP booking flow", **overrides) -> TechnicalSpecificationOutput:
    """A specification complete enough to pass the architecture gate.

    Every required section is populated. The architect node now routes a
    specification with empty required sections straight back for repair, because
    in practice the agent writes a full document to disk and then returns a
    structured response covering only part of it - so a fixture with empty
    sections no longer models a valid architect output.
    """
    fields = {
        "product_scope": scope,
        "component_boundaries": ["api", "worker"],
        "api_and_event_contracts": ["POST /bookings"],
        "data_flows": ["request -> api -> db"],
        "security_and_privacy": ["tokens are scoped per tenant"],
        "reliability_and_observability": ["health endpoint and request logs"],
        "testing": ["unit and integration"],
        "deployment": ["containers behind a load balancer"],
        "acceptance_criteria": ["a booking can be created and read back"],
    }
    fields.update(overrides)
    return TechnicalSpecificationOutput(**fields)


def _approved_review() -> ArchitectureReviewOutput:
    return ArchitectureReviewOutput(status="approved")


def _rejected_review(description: str = "No authentication described") -> ArchitectureReviewOutput:
    return ArchitectureReviewOutput(
        status="changes_required",
        findings=[
            ArchitectureReviewFinding(
                severity="blocking",
                description=description,
                evidence="Security and privacy section is empty.",
                required_remediation="Describe the authentication and session model.",
            )
        ],
    )


from app.agents.milestone_reviewer import MilestoneReviewFinding, MilestoneReviewOutput
from app.agents.security_reviewer import SecurityFinding, SecurityReviewOutput

def _milestone_review() -> MilestoneReviewOutput:
    return MilestoneReviewOutput(
        status="accepted",
        findings=[],
        acceptance_evidence="All good",
        documentation_reviewed=True,
        tests_reviewed=True,
    )

def _security_review() -> SecurityReviewOutput:
    return SecurityReviewOutput(
        status="passed",
        findings=[],
        local_only_exceptions=[]
    )


def _sprint_plan() -> SprintPlanOutput:
    return SprintPlanOutput(sprints=[SprintDefinition(goal="Sprint 1: booking", user_value="Patients can book")])


def _milestone(*roles: str, assignments: list[str] | None = None) -> MilestonePlanOutput:
    return MilestonePlanOutput(
        selected_sprint_goal="Sprint 1: booking",
        delegated_tasks=[
            SpecialistTask(specialist_role=role, task_description=f"do {role} work", acceptance_criteria=["works"])
            for role in roles
        ],
        # A plan produced *after* a review must name the task that takes each
        # requested change; one that assigns nothing is refused. Defaulting to a
        # populated list keeps every first-plan fixture working, and the
        # assignment rule has its own tests.
        review_task_assignments=assignments if assignments is not None else ["change -> task 1"],
    )


def _specialist(
    blockers: list[str] | None = None,
    *,
    defects: list[ReportedDefect] | None = None,
    tests: list[str] | None = None,
    changed_files: list[str] | None = None,
) -> SpecialistOutput:
    return SpecialistOutput(
        blockers=blockers or [],
        defects=defects or [],
        tests=tests or [],
        changed_files=changed_files or [],
    )


def _defect(owner: str = "backend", description: str = "Booking API returns 500") -> ReportedDefect:
    return ReportedDefect(
        description=description,
        severity="blocking",
        reproduction_steps="POST /bookings with a valid payload.",
        expected_behavior="201 Created",
        actual_behavior="500 Internal Server Error",
        affected_files=["src/api/bookings.py"],
        owner=owner,
    )


def _document() -> DocumentContent:
    return DocumentContent(
        source_path="brief.md",
        source_type="markdown",
        text="Clinics need online booking.",
        truncated=False,
    )


def _repository(tmp_path: Any) -> RepositoryContext:
    return RepositoryContext(root_path=str(tmp_path), branch="main", commit="0000000", status="clean")


def _graph() -> Any:
    """Compile the controller with a shared in-memory checkpointer."""
    from langgraph.checkpoint.memory import MemorySaver
    from app.graph.checkpointing import build_serializer
    return build_workflow_graph(model="fake-model", checkpointer=MemorySaver(serde=build_serializer()))


from app.agents.stack_selector import StackSelectorOutput
from app.agents.tools_models import TechnologyStack

def _stack_selector() -> StackSelectorOutput:
    return StackSelectorOutput(
        technology_stack=TechnologyStack(
            language="Python",
            framework="FastAPI",
            database="PostgreSQL",
            testing_framework="pytest",
            additional_tools=["Docker"]
        ),
        rationale="Standard Python stack."
    )


def _script_through_architecture(agents: ScriptedAgents, review: ArchitectureReviewOutput) -> None:
    """Script the four stages that run before sprint planning."""
    agents.script("product_manager", [responds_with(_intake())])
    agents.script("tools_models", [responds_with(_tools())])
    agents.script("stack_selector", [responds_with(_stack_selector())])
    agents.script("principal_architect", [responds_with(_spec())])
    agents.script("architecture_review", [responds_with(review)])


def _script_through_sprint(agents: ScriptedAgents) -> None:
    """Script sprint planning plus a clean implementation and verification round.

    The testing specialist is invoked twice on the happy path: once for its
    delegated implementation task, then again for the dedicated verification
    round that triages failures into defects (Step 5.4).
    """
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("testing"))])
    agents.script("specialist_testing", [responds_with(_specialist()), responds_with(_specialist())])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])


# --------------------------------------------------------------------------
# Pure router behavior
# --------------------------------------------------------------------------


def test_fresh_run_enters_at_the_product_manager() -> None:
    assert _entry_router({}) == "product_manager"


def test_entry_router_resumes_the_stage_that_paused_for_approval() -> None:
    assert _entry_router({"stage": "awaiting_approval:tools_models"}) == "tools_models"


def test_entry_router_maps_per_task_specialist_pauses_back_to_the_dispatch_node() -> None:
    """Specialist stages are named per task, so they are not graph nodes themselves."""
    assert _entry_router({"stage": "awaiting_approval:specialist_backend_0"}) == "specialist_dispatch"


def test_entry_router_resumes_an_open_review_at_its_own_gate() -> None:
    assert _entry_router({"stage": "awaiting_user_review:technical_specification"}) == "user_review_specification"
    assert _entry_router({"stage": "awaiting_user_review:sprint"}) == "user_review_sprint"


def test_entry_router_fails_closed_on_an_unknown_review_point() -> None:
    """An unrecognized pause must not silently fall through to a real stage."""
    assert _entry_router({"stage": "awaiting_user_review:not_a_review_point"}) == "failed"


def test_paused_stages_end_the_current_invoke() -> None:
    assert _route_from_stage({"stage": "awaiting_approval:principal_architect"}) == END
    assert _route_from_stage({"stage": "awaiting_user_review:sprint"}) == END


def test_unpaused_stages_route_to_the_named_node() -> None:
    assert _route_from_stage({"stage": "scrum_master"}) == "scrum_master"


# --------------------------------------------------------------------------
# End-to-end routing with scripted agents
# --------------------------------------------------------------------------


def test_happy_path_runs_every_stage_in_order_and_completes(agents: ScriptedAgents, tmp_path: Any) -> None:
    _script_through_architecture(agents, _approved_review())
    _script_through_sprint(agents)

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-happy")

    if state["stage"] == "failed":
        print("ERROR:", state.get("error", "Unknown error"))
    assert state["stage"] == "complete"
    assert state["product_intake"].product_name == "Acme Scheduling"
    assert state["architecture_review"].status == "approved"
    assert state["sprint_plan"].sprints[0].goal == "Sprint 1: booking"
    assert "specialist_testing_0" in state["specialist_outputs"]


def test_a_specification_missing_sections_goes_straight_back_to_the_architect(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    """A structured response that dropped sections is repaired before review.

    Observed on a real run: the architect wrote a complete 215-line
    specification to disk, then returned a structured response with seven
    required sections empty. The reviewer reads the structured output, so it
    correctly reported them as empty - and the run spent its entire revision
    budget and died at the gate on a defect no amount of reviewing could fix.
    """
    agents.script("product_manager", [responds_with(_intake())])
    agents.script("tools_models", [responds_with(_tools())])
    agents.script("stack_selector", [responds_with(_stack_selector())])
    agents.script(
        "principal_architect",
        [
            responds_with(_spec("draft", security_and_privacy=[], testing=[], deployment=[])),
            responds_with(_spec("repaired")),
        ],
    )
    agents.script("architecture_review", [responds_with(_approved_review())])
    _script_through_sprint(agents)

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-repair")

    assert state["stage"] == "complete"
    # The reviewer was never asked to adjudicate the incomplete draft, so no
    # revision was charged against the architecture budget.
    assert state.get("architecture_revision_count", 0) == 0
    assert state["specification_repair_count"] == 0

    repair_request = agents.requests["principal_architect"][1]["messages"][0]["content"]
    for section in ("security_and_privacy", "testing", "deployment"):
        assert section in repair_request


def test_the_repair_loop_gives_up_and_lets_the_reviewer_judge(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    """An architect that keeps dropping sections must not spin forever."""
    incomplete = _spec("still missing", testing=[], deployment=[])
    agents.script("product_manager", [responds_with(_intake())])
    agents.script("tools_models", [responds_with(_tools())])
    agents.script("stack_selector", [responds_with(_stack_selector())])
    agents.script(
        "principal_architect",
        [responds_with(incomplete) for _ in range(MAX_SPECIFICATION_REPAIRS + 1)],
    )
    agents.script("architecture_review", [responds_with(_approved_review())])
    _script_through_sprint(agents)

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-repair-limit")

    assert len(agents.requests["principal_architect"]) == MAX_SPECIFICATION_REPAIRS + 1
    assert state["specification_repair_count"] == MAX_SPECIFICATION_REPAIRS
    # It reached the reviewer rather than looping.
    assert agents.requests["architecture_review"]


def test_rejected_architecture_returns_to_the_architect_with_the_findings(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    """The reviewer's findings must reach the architect, not just the routing decision.

    Routing rejected work back is only half of Step 4.3. If the architect is
    re-sent the original brief, it has no idea what was wrong and will very
    likely reproduce the specification that was just rejected.
    """
    agents.script("product_manager", [responds_with(_intake())])
    agents.script("tools_models", [responds_with(_tools())])
    agents.script("stack_selector", [responds_with(_stack_selector())])
    agents.script(
        "principal_architect",
        [responds_with(_spec("first draft")), responds_with(_spec("revised with auth"))],
    )
    agents.script(
        "architecture_review",
        [responds_with(_rejected_review("No authentication described")), responds_with(_approved_review())],
    )
    _script_through_sprint(agents)

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-reject")

    if state["stage"] == "failed":
        print("ERROR:", state.get("error", "Unknown error"))
    assert state["stage"] == "complete"
    assert state["architecture_revision_count"] == 1

    revision_request = agents.last_request_text("principal_architect")
    assert "No authentication described" in revision_request
    assert "Describe the authentication and session model." in revision_request
    assert "first draft" in revision_request, "the rejected specification should come back for revision"


def test_repeated_rejection_fails_the_run_instead_of_looping(agents: ScriptedAgents, tmp_path: Any) -> None:
    agents.script("product_manager", [responds_with(_intake())])
    agents.script("tools_models", [responds_with(_tools())])
    agents.script("stack_selector", [responds_with(_stack_selector())])
    agents.script("principal_architect", [responds_with(_spec())] * MAX_ARCHITECTURE_REVISIONS)
    agents.script("architecture_review", [responds_with(_rejected_review())] * MAX_ARCHITECTURE_REVISIONS)

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-loop")

    assert state["stage"] == "failed"
    assert state["architecture_revision_count"] == MAX_ARCHITECTURE_REVISIONS

    # The message has to say what is still wrong, not just that the run stopped.
    # The reviewer has already written the answer down; a run that dies with
    # "reached the limit" makes the reader open the checkpoint to find out why.
    error = state["error"]
    assert str(MAX_ARCHITECTURE_REVISIONS) in error
    assert "No authentication described" in error
    assert "Describe the authentication and session model." in error


def test_the_architecture_revision_budget_is_bounded_and_configurable(monkeypatch) -> None:
    """Slow convergence is not the same failure as an architect that loops.

    Three rounds was too tight: observed runs died at the cap with one finding
    outstanding and a usable specification already written. It still has to be
    bounded, because a reviewer and an architect that disagree never converge
    and each round costs two model calls.
    """
    from app.graph.workflow import _max_architecture_revisions

    assert 3 < _max_architecture_revisions() <= 10

    monkeypatch.delenv("WORKFLOW_MAX_ARCHITECTURE_REVISIONS", raising=False)
    default = _max_architecture_revisions()

    monkeypatch.setenv("WORKFLOW_MAX_ARCHITECTURE_REVISIONS", "9")
    assert _max_architecture_revisions() == 9

    # A typo must not disable the bound; it falls back to the default.
    monkeypatch.setenv("WORKFLOW_MAX_ARCHITECTURE_REVISIONS", "several")
    assert _max_architecture_revisions() == default


def test_gating_findings_are_separated_from_advisory_ones() -> None:
    """The architect must be able to tell what actually blocks approval.

    Only `blocking` and `major` force `changes_required`. Handed one flat list,
    the architect spread a revision evenly between a missing authorization model
    and a note about naming, and a real run reached the revision limit with the
    blocking findings still open.
    """
    from app.graph.workflow import _collect_required_changes

    review = ArchitectureReviewOutput(
        status="changes_required",
        findings=[
            ArchitectureReviewFinding(
                severity="minor", description="Naming is inconsistent.",
                evidence="Section 3.", required_remediation="Rename the field.",
            ),
            ArchitectureReviewFinding(
                severity="blocking", description="No authorization model.",
                evidence="Section 7.", required_remediation="Define role to permission mapping.",
            ),
        ],
    )

    changes = _collect_required_changes({"architecture_review": review})
    joined = "\n".join(changes)

    assert changes[0].startswith("MUST FIX")
    assert "No authorization model." in changes[1]
    assert joined.index("No authorization model.") < joined.index("Naming is inconsistent.")
    assert "Optional improvements" in joined


def test_an_approved_review_asks_for_no_changes() -> None:
    """Findings on an approved review are not revision instructions."""
    from app.graph.workflow import _collect_required_changes

    assert _collect_required_changes({"architecture_review": _approved_review()}) == []


def test_specialist_dispatch_runs_every_delegated_task(agents: ScriptedAgents, tmp_path: Any) -> None:
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("backend", "ui_ux", "testing"))])
    agents.script("specialist_backend", [responds_with(_specialist())])
    agents.script("specialist_ui_ux", [responds_with(_specialist())])
    agents.script("specialist_testing", [responds_with(_specialist()), responds_with(_specialist())])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-dispatch")

    if state["stage"] == "failed":
        print("ERROR:", state.get("error", "Unknown error"))
    assert state["stage"] == "complete"
    assert set(state["specialist_outputs"]) == {
        "specialist_backend_0",
        "specialist_ui_ux_1",
        "specialist_testing_2",
    }


def test_a_defect_that_never_gets_fixed_escalates_instead_of_looping(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    """A defect the owner cannot fix consumes attempts and then escalates."""
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    agents.script("specialist_backend", [responds_with(_specialist())] * 8)
    # Every verification round keeps finding the same failure.
    agents.script("specialist_testing", [responds_with(_specialist(defects=[_defect()]))] * 8)

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-blocked")

    assert state["stage"] == "failed"
    assert state["remediation"].escalated is True
    assert state["remediation"].attempt == workflow_module.MAX_REMEDIATION_ATTEMPTS
    assert "remediation attempts" in state["error"]
    assert "Booking API returns 500" in state["error"], "the defect report is the sprint evidence"


# --------------------------------------------------------------------------
# Mandatory approval gate (Step 3.2) driven through the controller
# --------------------------------------------------------------------------


def test_workflow_pauses_with_a_typed_approval_request(agents: ScriptedAgents, tmp_path: Any) -> None:
    agents.script("product_manager", [pause_for_approval("intake.md", "Product understanding draft")])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-approval")

    assert state["stage"] == "awaiting_approval:product_manager"
    approval = state["pending_approval"]
    assert approval.artifact_path == "intake.md"
    assert approval.requested_by == "product_manager"
    assert approval.risk_level == "low"
    assert state["pending_inner_thread_id"].startswith("run-approval:product_manager")


def test_approving_a_write_resumes_the_run_to_completion(agents: ScriptedAgents, tmp_path: Any) -> None:
    graph = _graph()
    agents.script("product_manager", [pause_for_approval(), responds_with(_intake())])
    agents.script("tools_models", [responds_with(_tools())])
    agents.script("stack_selector", [responds_with(_stack_selector())])
    agents.script("principal_architect", [responds_with(_spec())])
    agents.script("architecture_review", [responds_with(_approved_review())])
    _script_through_sprint(agents)

    state = start_workflow(graph, _document(), _repository(tmp_path), "run-approve")
    assert state["stage"] == "awaiting_approval:product_manager"

    state = resume_pending_approval(graph, "run-approve", approve_write_decision())

    if state["stage"] == "failed":
        print("ERROR:", state.get("error", "Unknown error"))
    assert state["stage"] == "complete"
    assert state["pending_approval"] is None
    assert state["product_intake"].product_name == "Acme Scheduling"


def test_resume_still_lands_when_every_invoke_carries_the_run_id(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    """A resume must apply its input even though the run id never changes.

    The runner passes the same `run_id` to `start_workflow` and to every
    `resume_pending_approval` that follows. LangGraph reserves the config key
    `run_id`: it copies the value into checkpoint metadata, and an invoke whose
    run id equals the checkpoint's is treated as re-entry into an already
    running invocation, so its input is discarded without a node running.

    Keying our id as `app_run_id` is what keeps that from happening. Every other
    test here omits `run_id` entirely, which is why the workflow could ship for
    weeks with every approval silently dropped: an unattended run re-answered
    one gate until MAX_GATES_PER_STAGE failed it, and a supervised run sat back
    down at the gate the human had just released.
    """
    graph = _graph()
    agents.script("product_manager", [pause_for_approval(), responds_with(_intake())])
    agents.script("tools_models", [responds_with(_tools())])
    agents.script("stack_selector", [responds_with(_stack_selector())])
    agents.script("principal_architect", [responds_with(_spec())])
    agents.script("architecture_review", [responds_with(_approved_review())])
    _script_through_sprint(agents)

    run_id = "run-carried-id"
    state = start_workflow(
        graph, _document(), _repository(tmp_path), "run-carried", run_id=run_id
    )
    assert state["stage"] == "awaiting_approval:product_manager"

    state = resume_pending_approval(
        graph, "run-carried", approve_write_decision(), run_id=run_id
    )

    assert state["stage"] != "awaiting_approval:product_manager", (
        "the approval was dropped: the graph came back on the same gate having "
        "run no node, which is the loop that exhausts MAX_GATES_PER_STAGE"
    )
    assert state["stage"] == "complete"
    assert state["pending_approval"] is None


def test_rejecting_a_write_still_lets_the_agent_finish_without_the_artifact(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    """Rejection blocks the file, not the workflow; the agent continues, told why."""
    graph = _graph()
    agents.script("product_manager", [pause_for_approval(), responds_with(_intake())])
    agents.script("tools_models", [responds_with(_tools())])
    agents.script("stack_selector", [responds_with(_stack_selector())])
    agents.script("principal_architect", [responds_with(_spec())])
    agents.script("architecture_review", [responds_with(_approved_review())])
    _script_through_sprint(agents)

    start_workflow(graph, _document(), _repository(tmp_path), "run-reject-write")
    state = resume_pending_approval(graph, "run-reject-write", reject_write_decision("Not accurate yet"))

    if state["stage"] == "failed":
        print("ERROR:", state.get("error", "Unknown error"))
    assert state["stage"] == "complete"


def test_a_specialist_can_pause_for_approval_and_resume_on_the_right_task(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    """A per-task specialist pause must resume that task, not restart the milestone."""
    graph = _graph()
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("backend", "testing"))])
    agents.script("specialist_backend", [pause_for_approval("api.md", "API draft"), responds_with(_specialist())])
    agents.script("specialist_testing", [responds_with(_specialist()), responds_with(_specialist())])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = start_workflow(graph, _document(), _repository(tmp_path), "run-specialist-pause")
    assert state["stage"] == "awaiting_approval:specialist_backend_0"
    assert state["pending_inner_thread_id"].startswith("run-specialist-pause:specialist_backend_0")

    state = resume_pending_approval(graph, "run-specialist-pause", approve_write_decision())

    if state["stage"] == "failed":
        print("ERROR:", state.get("error", "Unknown error"))
    assert state["stage"] == "complete"
    assert set(state["specialist_outputs"]) == {"specialist_backend_0", "specialist_testing_1"}


# --------------------------------------------------------------------------
# Optional user review sessions (Step 3.3) driven through the controller
# --------------------------------------------------------------------------


def test_no_review_policy_means_no_review_pause(agents: ScriptedAgents, tmp_path: Any) -> None:
    """Reviews are opt-in: a default run is gated only by approvals and architecture."""
    _script_through_architecture(agents, _approved_review())
    _script_through_sprint(agents)

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-no-review")

    if state["stage"] == "failed":
        print("ERROR:", state.get("error", "Unknown error"))
    assert state["stage"] == "complete"
    assert not state.get("reviews")


def test_specification_review_pauses_after_the_architecture_gate_passes(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    """An optional review runs only after the mandatory reviewer already approved."""
    _script_through_architecture(agents, _approved_review())

    state = start_workflow(
        _graph(),
        _document(),
        _repository(tmp_path),
        "run-spec-review",
        review_policy={SPECIFICATION_REVIEW: True},
        reviewer="alice",
    )

    assert state["stage"] == "awaiting_user_review:technical_specification"
    review = state["pending_review"]
    assert review.status is ReviewRequestStatus.PENDING
    assert review.reviewer == "alice"
    assert review.revision == 1
    assert review.thread_id == "run-spec-review"


def test_approving_the_specification_review_continues_to_sprint_planning(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    graph = _graph()
    _script_through_architecture(agents, _approved_review())
    _script_through_sprint(agents)

    start_workflow(
        graph,
        _document(),
        _repository(tmp_path),
        "run-spec-approve",
        review_policy={SPECIFICATION_REVIEW: True},
    )
    state = resume_pending_review(graph, "run-spec-approve", approve_decision("Looks good"))

    if state["stage"] == "failed":
        print("ERROR:", state.get("error", "Unknown error"))
    assert state["stage"] == "complete"
    assert state["reviews"][SPECIFICATION_REVIEW].status is ReviewRequestStatus.APPROVED
    assert "Looks good" in state["reviews"][SPECIFICATION_REVIEW].comments


def test_skipping_a_review_is_recorded_as_skipped_not_approved(agents: ScriptedAgents, tmp_path: Any) -> None:
    """The plan is explicit: a skip must never look like an approval was given."""
    graph = _graph()
    _script_through_architecture(agents, _approved_review())
    _script_through_sprint(agents)

    start_workflow(
        graph,
        _document(),
        _repository(tmp_path),
        "run-spec-skip",
        review_policy={SPECIFICATION_REVIEW: True},
    )
    state = resume_pending_review(graph, "run-spec-skip", skip_decision())

    if state["stage"] == "failed":
        print("ERROR:", state.get("error", "Unknown error"))
    assert state["stage"] == "complete"
    assert state["reviews"][SPECIFICATION_REVIEW].status is ReviewRequestStatus.SKIPPED


def test_requested_changes_send_the_comment_back_to_the_architect(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    graph = _graph()
    agents.script("product_manager", [responds_with(_intake())])
    agents.script("tools_models", [responds_with(_tools())])
    agents.script("stack_selector", [responds_with(_stack_selector())])
    agents.script(
        "principal_architect",
        [responds_with(_spec("first draft")), responds_with(_spec("second draft"))],
    )
    agents.script("architecture_review", [responds_with(_approved_review())] * 2)
    _script_through_sprint(agents)

    start_workflow(
        graph,
        _document(),
        _repository(tmp_path),
        "run-spec-changes",
        review_policy={SPECIFICATION_REVIEW: True},
    )
    state = resume_pending_review(
        graph, "run-spec-changes", request_changes_decision("Add a data retention policy")
    )

    # The second review round opens against revision 2 of the artifact.
    assert state["stage"] == "awaiting_user_review:technical_specification"
    assert state["reviews"][SPECIFICATION_REVIEW].revision == 2

    revision_request = agents.last_request_text("principal_architect")
    assert "Add a data retention policy" in revision_request
    assert "first draft" in revision_request


def test_a_change_request_without_a_comment_fails_with_an_actionable_error(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    """A role agent cannot revise anything from an empty change request."""
    graph = _graph()
    _script_through_architecture(agents, _approved_review())

    start_workflow(
        graph,
        _document(),
        _repository(tmp_path),
        "run-empty-comment",
        review_policy={SPECIFICATION_REVIEW: True},
    )
    state = resume_pending_review(graph, "run-empty-comment", {"type": "request_changes", "comment": ""})

    assert state["stage"] == "failed"
    assert "needs a comment" in state["error"]


def test_an_unknown_review_decision_fails_rather_than_being_treated_as_approval(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    graph = _graph()
    _script_through_architecture(agents, _approved_review())

    start_workflow(
        graph,
        _document(),
        _repository(tmp_path),
        "run-bad-decision",
        review_policy={SPECIFICATION_REVIEW: True},
    )
    state = resume_pending_review(graph, "run-bad-decision", {"type": "looks_fine_to_me"})

    assert state["stage"] == "failed"
    assert "Unknown review decision" in state["error"]


def test_repeated_change_requests_stop_at_the_rerun_limit(agents: ScriptedAgents, tmp_path: Any) -> None:
    """A review that never converges must escalate instead of rerunning forever."""
    graph = _graph()
    agents.script("product_manager", [responds_with(_intake())])
    agents.script("tools_models", [responds_with(_tools())])
    agents.script("stack_selector", [responds_with(_stack_selector())])
    agents.script("stack_selector", [responds_with(_stack_selector())] * 4)
    agents.script("principal_architect", [responds_with(_spec())] * 4)
    agents.script("architecture_review", [responds_with(_approved_review())] * 4)

    start_workflow(
        graph,
        _document(),
        _repository(tmp_path),
        "run-review-limit",
        review_policy={SPECIFICATION_REVIEW: True},
    )

    state = resume_pending_review(graph, "run-review-limit", request_changes_decision("first pass"))
    assert state["stage"] == "awaiting_user_review:technical_specification"

    state = resume_pending_review(graph, "run-review-limit", request_changes_decision("second pass"))
    assert state["stage"] == "awaiting_user_review:technical_specification"

    state = resume_pending_review(graph, "run-review-limit", request_changes_decision("third pass"))
    assert state["stage"] == "failed"
    # The message now names the stage and how to lift the limit, rather
    # than the phrase "automatic reruns".
    assert "the configured limit" in state["error"]
    assert "WORKFLOW_MAX_REVIEW_RERUNS" in state["error"]


def test_sprint_review_pauses_after_tests_pass_and_can_be_approved(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    graph = _graph()
    _script_through_architecture(agents, _approved_review())
    _script_through_sprint(agents)

    state = start_workflow(
        graph,
        _document(),
        _repository(tmp_path),
        "run-sprint-review",
        review_policy={SPRINT_REVIEW: True},
    )
    assert state["stage"] == "awaiting_user_review:sprint"
    assert state["remediation"].attempt == 0

    state = resume_pending_review(graph, "run-sprint-review", approve_decision())

    if state["stage"] == "failed":
        print("ERROR:", state.get("error", "Unknown error"))
    assert state["stage"] == "complete"
    assert state["reviews"][SPRINT_REVIEW].status is ReviewRequestStatus.APPROVED


def test_sprint_review_changes_replan_the_milestone_with_the_comment(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    graph = _graph()
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("testing"))] * 2)
    agents.script("specialist_testing", [responds_with(_specialist())] * 4)
    agents.script("milestone_reviewer", [responds_with(_milestone_review())] * 2)
    agents.script("security_reviewer", [responds_with(_security_review())] * 2)

    start_workflow(
        graph,
        _document(),
        _repository(tmp_path),
        "run-sprint-changes",
        review_policy={SPRINT_REVIEW: True},
    )
    state = resume_pending_review(graph, "run-sprint-changes", request_changes_decision("Add an audit log"))

    assert state["stage"] == "awaiting_user_review:sprint"
    assert "Add an audit log" in agents.last_request_text("technical_lead")


def test_a_blocked_sprint_never_reaches_its_optional_review(agents: ScriptedAgents, tmp_path: Any) -> None:
    """An optional review cannot rubber-stamp a sprint whose tests never passed."""
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    agents.script("specialist_backend", [responds_with(_specialist())] * 8)
    agents.script("specialist_testing", [responds_with(_specialist(defects=[_defect()]))] * 8)

    state = start_workflow(
        _graph(),
        _document(),
        _repository(tmp_path),
        "run-blocked-review",
        review_policy={SPRINT_REVIEW: True},
    )

    assert state["stage"] == "failed"
    assert not state.get("reviews")


# --------------------------------------------------------------------------
# Per-sprint test and bug-remediation loop (Step 5.4)
# --------------------------------------------------------------------------


def test_a_clean_verification_round_records_passing_evidence(agents: ScriptedAgents, tmp_path: Any) -> None:
    """Even a clean sprint must leave a test-run record behind as evidence."""
    _script_through_architecture(agents, _approved_review())
    _script_through_sprint(agents)

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-clean-tests")

    cycle = state["remediation"]
    if state["stage"] == "failed":
        print("ERROR:", state.get("error", "Unknown error"))
    assert state["stage"] == "complete"
    assert cycle.attempt == 0
    assert [run.passed for run in cycle.test_runs] == [True]
    assert cycle.defects == []


def test_a_reported_failure_becomes_a_tracked_defect_routed_to_its_owner(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    """The core of Step 5.4: a failure is tracked, owned, fixed, and re-tested."""
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    agents.script(
        "specialist_backend",
        [
            responds_with(_specialist(changed_files=["src/api/bookings.py"])),
            responds_with(_specialist(tests=["tests/test_bookings_regression.py"])),
        ],
    )
    agents.script(
        "specialist_testing",
        [
            responds_with(_specialist(defects=[_defect(owner="backend")])),
            responds_with(_specialist()),
        ],
    )
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-defect-loop")

    if state["stage"] == "failed":
        print("ERROR:", state.get("error", "Unknown error"))
    assert state["stage"] == "complete"

    cycle = state["remediation"]
    assert len(cycle.defects) == 1
    defect = cycle.defects[0]
    assert defect.owner == "backend"
    assert defect.status == "fixed"
    assert defect.regression_test == "tests/test_bookings_regression.py"
    assert [run.passed for run in cycle.test_runs] == [False, True]

    # The defect was routed to the owner with enough detail to act on.
    fix_request = agents.last_request_text("specialist_backend")
    assert "Booking API returns 500" in fix_request
    assert "500 Internal Server Error" in fix_request
    assert "regression test" in fix_request


def test_a_defect_is_routed_to_its_owner_not_to_the_reporter(agents: ScriptedAgents, tmp_path: Any) -> None:
    """A defect the tester found in UI work must go to the UI specialist."""
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("ui_ux"))])
    agents.script(
        "specialist_ui_ux",
        [responds_with(_specialist()), responds_with(_specialist(tests=["tests/test_button.py"]))],
    )
    agents.script(
        "specialist_testing",
        [
            responds_with(_specialist(defects=[_defect(owner="ui_ux", description="Login button is unreachable")])),
            responds_with(_specialist()),
        ],
    )
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-defect-owner")

    if state["stage"] == "failed":
        print("ERROR:", state.get("error", "Unknown error"))
    assert state["stage"] == "complete"
    assert state["remediation"].defects[0].owner == "ui_ux"
    assert "Login button is unreachable" in agents.last_request_text("specialist_ui_ux")
    assert len(agents.requests["specialist_ui_ux"]) == 2, "the owner was invoked to fix its own defect"


def test_a_fix_without_a_regression_test_does_not_close_the_defect(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    """The plan's gate forbids accepting a sprint with missing regression coverage."""
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    # The backend specialist claims to have fixed it but names no test.
    agents.script("specialist_backend", [responds_with(_specialist(tests=[]))] * 8)
    agents.script("specialist_testing", [responds_with(_specialist(defects=[_defect()]))] * 8)

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-no-regression")

    assert state["stage"] == "failed"
    assert state["remediation"].defects[0].status == "open"
    assert state["remediation"].escalated is True


def test_multiple_defects_are_each_routed_to_their_own_owner(agents: ScriptedAgents, tmp_path: Any) -> None:
    """Every defect gets worked; none is skipped as the open set shrinks."""
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    agents.script("specialist_backend", [responds_with(_specialist()), responds_with(_specialist(tests=["t1"]))])
    agents.script("specialist_database", [responds_with(_specialist(tests=["t2"]))])
    agents.script("specialist_ui_ux", [responds_with(_specialist(tests=["t3"]))])
    agents.script(
        "specialist_testing",
        [
            responds_with(
                _specialist(
                    defects=[
                        _defect(owner="backend", description="API 500"),
                        _defect(owner="database", description="Missing index"),
                        _defect(owner="ui_ux", description="Broken layout"),
                    ]
                )
            ),
            responds_with(_specialist()),
        ],
    )
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-multi-defect")

    if state["stage"] == "failed":
        print("ERROR:", state.get("error", "Unknown error"))
    assert state["stage"] == "complete"
    cycle = state["remediation"]
    assert len(cycle.defects) == 3
    assert all(defect.status == "fixed" for defect in cycle.defects), "no defect was skipped"
    assert [defect.regression_test for defect in cycle.defects] == ["t1", "t2", "t3"]


def test_a_defect_fix_can_pause_for_approval_and_resume_on_the_same_defect(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    """A pause mid-remediation must resume that defect, not restart the round."""
    graph = _graph()
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    agents.script(
        "specialist_backend",
        [
            responds_with(_specialist()),
            pause_for_approval("fix.md", "Proposed fix"),
            responds_with(_specialist(tests=["tests/test_fix.py"])),
        ],
    )
    agents.script(
        "specialist_testing",
        [responds_with(_specialist(defects=[_defect()])), responds_with(_specialist())],
    )
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = start_workflow(graph, _document(), _repository(tmp_path), "run-fix-pause")
    assert state["stage"] == "awaiting_approval:defect_fix_1_0"

    state = resume_pending_approval(graph, "run-fix-pause", approve_write_decision())

    if state["stage"] == "failed":
        print("ERROR:", state.get("error", "Unknown error"))
    assert state["stage"] == "complete"
    assert state["remediation"].defects[0].status == "fixed"


def test_a_verification_round_can_pause_for_approval_and_resume(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    """The test round's own artifact write is gated like any other."""
    graph = _graph()
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("testing"))])
    agents.script(
        "specialist_testing",
        [responds_with(_specialist()), pause_for_approval("results.md", "Test results"), responds_with(_specialist())],
    )
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = start_workflow(graph, _document(), _repository(tmp_path), "run-test-pause")
    assert state["stage"] == "awaiting_approval:test_round_0"

    state = resume_pending_approval(graph, "run-test-pause", approve_write_decision())

    if state["stage"] == "failed":
        print("ERROR:", state.get("error", "Unknown error"))
    assert state["stage"] == "complete"


def test_entry_router_maps_the_iterated_stage_names_to_their_owning_nodes() -> None:
    assert _entry_router({"stage": "awaiting_approval:test_round_3"}) == "test_and_triage"
    assert _entry_router({"stage": "awaiting_approval:defect_fix_1_2"}) == "defect_remediation"
    assert _entry_router({"stage": "awaiting_approval:specialist_database_4"}) == "specialist_dispatch"


def test_entry_router_fails_closed_on_an_unrecognised_approval_stage() -> None:
    """An unknown pause must not be silently rerouted into an unrelated stage."""
    assert _entry_router({"stage": "awaiting_approval:not_a_real_stage"}) == "failed"


# ---------------------------------------------------------------------------
# Anything that sets `stage` must name a node
#
# `_route_from_stage` returns the value verbatim and the edge map is keyed by
# `_NODE_NAMES`, so a stage that is not a node is a KeyError that kills the run.
# The structured-response retry set `stage` to the stage's own name
# (`specialist_ui_ux_0`) and took down the run it existed to rescue.
# ---------------------------------------------------------------------------


def test_every_iterated_stage_resolves_to_a_real_node():
    from app.graph.workflow import _NODE_NAMES, _owning_node

    for stage in (
        "specialist_ui_ux_0", "specialist_backend_2", "specialist_testing_11",
        "test_round_0", "test_round_7",
        "defect_fix_0_0", "defect_fix_3_12",
    ):
        assert _owning_node(stage) in _NODE_NAMES, f"{stage} routes nowhere"


def test_a_plain_stage_resolves_to_itself():
    from app.graph.workflow import _owning_node

    for stage in ("principal_architect", "architecture_review", "scrum_master"):
        assert _owning_node(stage) == stage


def test_an_unknown_stage_fails_closed():
    """Better a failed run than a KeyError that kills the process."""
    from app.graph.workflow import _owning_node

    assert _owning_node("something_invented") == "failed"


def test_the_structured_retry_targets_a_routable_node():
    """The exact regression: the retry's stage must be dispatchable."""
    from types import SimpleNamespace

    from app.graph.workflow import _NODE_NAMES, _run_gated_agent

    class _NoStructured:
        def invoke(self, request, config=None):
            return {"messages": [SimpleNamespace(type="ai", content="prose")]}

    for stage in ("specialist_ui_ux_0", "test_round_1", "principal_architect"):
        update = _run_gated_agent(
            {"stage": stage, "repository": SimpleNamespace(root_path="/w")},
            {"configurable": {"thread_id": "t"}},
            stage_name=stage,
            agent=_NoStructured(),
            initial_request={"messages": []},
            output_key="out",
            next_stage="complete",
        )
        assert update["stage"] in _NODE_NAMES, f"retry from {stage} routes nowhere"
