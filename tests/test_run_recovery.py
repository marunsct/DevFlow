"""Recovery paths for a run that stopped part-way.

Every test here comes from one real run that deadlocked. It reached the
architecture gate, was rejected three times, and then could not be moved
forward by any route: the UI offered Resume because the row said `failed`, but
the graph was parked on an approval gate that only a decision can clear, so each
Resume re-ran the architect from scratch and landed back on the same gate.
"""

from types import SimpleNamespace

import pytest

from app.graph.workflow import (
    APPROVAL_PAUSE_PREFIX,
    MAX_SPECIFICATION_REPAIRS,
    WorkflowResumeError,
    _incomplete_specification_sections,
    _node_that_failed,
    _run_gated_agent,
    resume_failed_run,
)


# ---------------------------------------------------------------------------
# A resume without a decision must not restart a paused agent
# ---------------------------------------------------------------------------


def _write_interrupt():
    """The shape LangGraph hands back when a gated write pauses."""
    return SimpleNamespace(
        id="interrupt-1",
        value={"action_requests": [{"args": {"relative_path": "docs/spec.md", "content": "spec"}}]},
    )


class _CountingAgent:
    """Records how many times the workflow re-invoked the underlying agent."""

    def __init__(self) -> None:
        self.invocations = 0

    def invoke(self, request, config=None):
        self.invocations += 1
        return {"__interrupt__": [_write_interrupt()]}


def _state_paused_at(stage_name: str) -> dict:
    return {
        "stage": f"{APPROVAL_PAUSE_PREFIX}{stage_name}",
        "pending_approval": SimpleNamespace(artifact_path="docs/spec.md"),
        "pending_inner_thread_id": f"thread-outer:{stage_name}:abc123",
        "pending_decision": None,
        "repository": SimpleNamespace(root_path="/workspace"),
    }


def _gated(state: dict, agent, stage_name: str = "principal_architect") -> dict:
    return _run_gated_agent(
        state,
        {"configurable": {"thread_id": "thread-outer"}},
        stage_name=stage_name,
        agent=agent,
        initial_request={"messages": []},
        output_key="technical_specification",
        next_stage="architecture_review",
    )


def test_resuming_an_approval_pause_does_not_re_run_the_agent():
    """The loop that burned a model call per Resume and never progressed."""
    agent = _CountingAgent()

    update = _gated(_state_paused_at("principal_architect"), agent)

    assert agent.invocations == 0
    assert update["stage"] == f"{APPROVAL_PAUSE_PREFIX}principal_architect"


def test_the_paused_inner_thread_is_kept_not_replaced():
    """Minting a fresh inner thread orphans the agent waiting on the gate."""
    state = _state_paused_at("principal_architect")

    update = _gated(state, _CountingAgent())

    assert update["pending_inner_thread_id"] == state["pending_inner_thread_id"]
    assert update["pending_approval"] is state["pending_approval"]


def test_a_pause_belonging_to_another_stage_still_runs_this_agent():
    """The guard must match only this stage's own gate, not any pause."""
    agent = _CountingAgent()

    _gated(_state_paused_at("tools_models"), agent, stage_name="principal_architect")

    assert agent.invocations == 1


def test_a_fresh_stage_runs_the_agent():
    agent = _CountingAgent()

    _gated(
        {"stage": "principal_architect", "repository": SimpleNamespace(root_path="/w")},
        agent,
    )

    assert agent.invocations == 1


# ---------------------------------------------------------------------------
# Locating the node that failed
# ---------------------------------------------------------------------------


def _snapshot(next_nodes: tuple[str, ...]):
    return SimpleNamespace(next=next_nodes, values={})


class _FakeGraph:
    """Only the two methods `resume_failed_run` reaches for."""

    def __init__(self, history, stage="failed"):
        self._history = history
        self._stage = stage
        self.updates: list[tuple[dict, str]] = []
        self.invoked = False

    def get_state(self, config):
        return SimpleNamespace(values={"stage": self._stage})

    def get_state_history(self, config):
        return iter(self._history)

    def update_state(self, config, values, as_node=None):
        self.updates.append((values, as_node))

    def invoke(self, _input, config=None):
        self.invoked = True
        return {"stage": "principal_architect"}


def test_the_failing_node_is_found_on_a_first_resume():
    history = [
        _snapshot(()),
        _snapshot(("failed",)),
        _snapshot(("architecture_review",)),
    ]

    assert _node_that_failed(_FakeGraph(history), {}) == "architecture_review"


def test_bookkeeping_checkpoints_are_skipped_on_a_later_resume():
    """Each earlier resume prepends its own `__start__` entries.

    Trusting the immediate neighbour picked up `__start__`, which matched no
    rewind branch - so the run was never rewound and Resume did nothing.
    """
    history = [
        _snapshot(()),
        _snapshot(("failed",)),
        _snapshot(("__start__",)),
        _snapshot(()),
        _snapshot(("failed",)),
        _snapshot(("architecture_review",)),
    ]

    assert _node_that_failed(_FakeGraph(history), {}) == "architecture_review"


def test_an_unrecognisable_history_yields_no_node():
    history = [_snapshot(()), _snapshot(("failed",)), _snapshot(("__start__",))]

    assert _node_that_failed(_FakeGraph(history), {}) is None


def test_resume_refuses_rather_than_restarting_from_the_beginning():
    """The old fallback rewound to `product_manager`, silently discarding every
    approved artifact and re-billing the entire pipeline."""
    graph = _FakeGraph([_snapshot(()), _snapshot(("failed",)), _snapshot(("__start__",))])

    with pytest.raises(WorkflowResumeError, match="safe point to retry"):
        resume_failed_run(graph, "thread-1")

    assert graph.updates == []
    assert not graph.invoked


def test_resume_refuses_a_run_that_is_waiting_on_a_human():
    graph = _FakeGraph([], stage=f"{APPROVAL_PAUSE_PREFIX}principal_architect")

    with pytest.raises(WorkflowResumeError, match="waiting for a decision"):
        resume_failed_run(graph, "thread-1")

    assert not graph.invoked


def test_a_rewind_clears_both_revision_counters():
    history = [_snapshot(()), _snapshot(("failed",)), _snapshot(("architecture_review",))]
    graph = _FakeGraph(history)

    resume_failed_run(graph, "thread-1")

    values, as_node = graph.updates[0]
    assert as_node == "architecture_review"
    assert values["architecture_revision_count"] == 0
    assert values["specification_repair_count"] == 0
    assert values["stage"] == "principal_architect"
    assert values["error"] is None


# ---------------------------------------------------------------------------
# Where a resume rewinds to
# ---------------------------------------------------------------------------
#
# The bug these cover: the rewind chain was an if/elif over an initialiser that
# defaulted to stage="product_manager", so any node the chain did not name
# restarted the run from intake - discarding every approved artifact and
# re-billing the whole pipeline. That was unreachable until context compaction
# gave every agent node a route to stage="failed", at which point seven nodes
# started restarting runs from the beginning.


def _resume_from(node: str):
    """Resume a run whose failure is attributed to `node`; return the update."""
    history = [_snapshot(()), _snapshot(("failed",)), _snapshot((node,))]
    graph = _FakeGraph(history)
    resume_failed_run(graph, "thread-1")
    return graph.updates[0]


@pytest.mark.parametrize(
    "node",
    [
        "tools_models",
        "stack_selector",
        "principal_architect",
        "scrum_master",
        "technical_lead",
    ],
)
def test_a_stage_that_failed_is_retried_not_restarted_from_intake(node):
    values, as_node = _resume_from(node)

    assert values["stage"] == node
    assert as_node == node
    assert values["error"] is None


@pytest.mark.parametrize(
    "node, target",
    [
        ("architecture_review", "principal_architect"),
        ("milestone_review", "scrum_master"),
        ("test_and_triage", "technical_lead"),
        ("sprint_advance", "technical_lead"),
        ("specialist_dispatch", "technical_lead"),
        ("defect_remediation", "technical_lead"),
    ],
)
def test_a_stage_with_no_useful_retry_rewinds_to_the_node_that_feeds_it(node, target):
    """Retrying these as themselves reproduces the same failure immediately."""
    values, _ = _resume_from(node)

    assert values["stage"] == target


def test_every_node_in_the_graph_has_a_declared_rewind_target():
    """The structural guard: a new node cannot silently inherit a restart.

    This is the invariant the old if/elif chain could not express. Without it,
    adding a node to `_NODE_NAMES` and forgetting the rewind table reintroduces
    exactly the defect this suite exists to prevent.
    """
    from app.graph.workflow import _NODE_NAMES, _UNREWINDABLE_NODES, _rewind_target

    for node in _NODE_NAMES - _UNREWINDABLE_NODES:
        target = _rewind_target(node)
        assert target is not None, f"{node} has no rewind target"
        assert target in _NODE_NAMES, f"{node} rewinds to unknown node {target}"


def test_a_terminal_node_refuses_the_resume_rather_than_rewinding():
    from app.graph.workflow import _rewind_target

    assert _rewind_target("complete") is None
    assert _rewind_target("failed") is None
    assert _rewind_target("__start__") is None
    assert _rewind_target(None) is None
    assert _rewind_target("a_node_that_does_not_exist") is None


def test_an_unrecognisable_failure_names_the_stage_in_its_refusal():
    graph = _FakeGraph([_snapshot(()), _snapshot(("failed",)), _snapshot(("complete",))])

    with pytest.raises(WorkflowResumeError, match="complete"):
        resume_failed_run(graph, "thread-1")


# ---------------------------------------------------------------------------
# Specification completeness
# ---------------------------------------------------------------------------


def _specification(**overrides):
    from app.agents.principal_architect import TechnicalSpecificationOutput

    fields = {
        "product_scope": "scope",
        "component_boundaries": ["c"],
        "api_and_event_contracts": ["a"],
        "data_flows": ["d"],
        "security_and_privacy": ["s"],
        "reliability_and_observability": ["r"],
        "testing": ["t"],
        "deployment": ["dep"],
        "acceptance_criteria": ["ac"],
    }
    fields.update(overrides)
    return TechnicalSpecificationOutput(**fields)


def test_a_complete_specification_reports_nothing_missing():
    assert _incomplete_specification_sections(_specification()) == []


def test_sections_the_structured_response_dropped_are_reported():
    spec = _specification(security_and_privacy=[], testing=[], deployment=[])

    assert _incomplete_specification_sections(spec) == [
        "security_and_privacy",
        "testing",
        "deployment",
    ]


def test_optional_sections_are_not_required():
    """A small product legitimately has no separate domain model or open questions."""
    spec = _specification(domain_model=[], open_questions=[])

    assert _incomplete_specification_sections(spec) == []


def test_no_specification_yet_is_not_an_incompleteness():
    assert _incomplete_specification_sections(None) == []


def test_the_repair_budget_is_smaller_than_the_review_budget():
    """Repairs must not be able to exhaust the architecture revision budget."""
    from app.graph.workflow import MAX_ARCHITECTURE_REVISIONS

    assert MAX_SPECIFICATION_REPAIRS < MAX_ARCHITECTURE_REVISIONS


def test_a_specialist_must_be_able_to_state_its_evidence():
    """`tests` as prose was the only evidence; this makes a claim checkable."""
    from app.agents.specialists import SpecialistOutput, VerificationRun

    output = SpecialistOutput(
        changed_files=["thehub/api/main.py"],
        verification=[VerificationRun(command=["pytest", "-q"], exit_code=0, summary="17 passed")],
    )

    assert output.verification[0].exit_code == 0
    assert SpecialistOutput().verification == [], "must default to empty, not fail"


# ---------------------------------------------------------------------------
# A stage that returns no structured response
#
# From run-0b55ad49: `specialist_ui_ux_0` did its work, then wrote the heading
# "## Structured Response" in prose and continued for 431,441 characters. The
# stage raised, the run was resumed, and the resume re-entered that same inner
# thread, replayed it, and failed identically four minutes later - forever.
# ---------------------------------------------------------------------------


class _NoStructuredResponseAgent:
    """Completes its turn but never fills `structured_response`."""

    def __init__(self, succeed_after: int = 99) -> None:
        self.invocations = 0
        self.threads: list[str] = []
        self._succeed_after = succeed_after

    def invoke(self, request, config=None):
        self.invocations += 1
        self.threads.append((config or {}).get("configurable", {}).get("thread_id", ""))
        if self.invocations > self._succeed_after:
            return {"structured_response": SimpleNamespace(ok=True), "messages": []}
        return {"messages": [SimpleNamespace(type="ai", content="## Structured Response\n" + "x" * 900)]}


def _fresh_state() -> dict:
    return {"stage": "specialist_ui_ux_0", "repository": SimpleNamespace(root_path="/workspace")}


def test_a_missing_structured_response_retries_instead_of_failing():
    agent = _NoStructuredResponseAgent()

    update = _gated(_fresh_state(), agent, stage_name="specialist_ui_ux_0")

    # The owning node, not the stage name: `specialist_ui_ux_0` is not a graph
    # node, and returning it raised KeyError and killed the run.
    assert update["stage"] == "specialist_dispatch"
    assert update["structured_retries"]["specialist_ui_ux_0"] == 1
    # The poisoned conversation must not be carried into the retry.
    assert update["pending_inner_thread_id"] is None
    assert update["pending_decision"] is None


class _DeafAgent:
    """Never returns a structured response, however it is asked.

    Distinct from `_NoStructuredResponseAgent(succeed_after=n)`: that one
    succeeds on its next invocation whatever thread it lands on, which the
    nudge now satisfies. This one fails the nudge too, so the restart behind it
    is what gets exercised.
    """

    def __init__(self) -> None:
        self.threads: list[str] = []

    def invoke(self, request, config=None):  # noqa: ARG002
        self.threads.append((config or {}).get("configurable", {}).get("thread_id", ""))
        return {"messages": [SimpleNamespace(type="ai", content="prose, not a schema")]}


def test_a_stage_is_asked_again_before_its_conversation_is_discarded():
    """The prose answer means the work is done and the last step was skipped.

    Restarting throws away the work as well. Measured on run-61c5a5b6: the
    restart of `test_round_0` re-read the same four files and re-ran the same
    two globs to arrive back where it already was.
    """
    agent = _NoStructuredResponseAgent(succeed_after=1)

    update = _gated(_fresh_state(), agent, stage_name="specialist_ui_ux_0")

    assert agent.invocations == 2, "the stage should have been asked a second time"
    assert agent.threads[0] == agent.threads[1], "the nudge must keep the work above it"
    assert update["stage"] == "architecture_review", "the answer should have been accepted"
    assert not update.get("structured_retries"), "a nudge that worked is not a retry"


def test_the_retry_runs_on_a_different_conversation():
    """Replaying the failed conversation is what made this unrecoverable.

    This is the fallback behind the nudge: once asking again has not worked,
    the conversation really is spent and the restart must not re-enter it.
    """
    agent = _DeafAgent()

    first = _gated(_fresh_state(), agent, stage_name="specialist_ui_ux_0")
    second_state = {**_fresh_state(), **{k: v for k, v in first.items() if k != "stage"}}
    _gated(second_state, agent, stage_name="specialist_ui_ux_0")

    # Two attempts, each an invocation plus a nudge on that same thread.
    assert len(agent.threads) == 4
    assert agent.threads[0] == agent.threads[1], "the nudge stays on the thread"
    assert agent.threads[2] == agent.threads[3]
    assert agent.threads[0] != agent.threads[2], "the retry reused the failed thread"
    assert first["structured_retries"]["specialist_ui_ux_0"] == 1


def test_the_retry_budget_is_not_infinite(monkeypatch):
    monkeypatch.setenv("WORKFLOW_MAX_STRUCTURED_RETRIES", "1")
    agent = _NoStructuredResponseAgent()

    first = _gated(_fresh_state(), agent, stage_name="specialist_ui_ux_0")
    state = {**_fresh_state(), **{k: v for k, v in first.items() if k != "stage"}}

    with pytest.raises(ValueError, match="tried 2 times"):
        _gated(state, agent, stage_name="specialist_ui_ux_0")


def test_a_stage_that_succeeds_clears_its_retry_debt():
    """A later failure in the same stage should start from a full budget."""
    agent = _NoStructuredResponseAgent(succeed_after=0)
    state = {**_fresh_state(), "structured_retries": {"specialist_ui_ux_0": 2}}

    update = _gated(state, agent, stage_name="specialist_ui_ux_0")

    assert "specialist_ui_ux_0" not in update["structured_retries"]


# ---------------------------------------------------------------------------
# A revision has to assign the change, not just record it
#
# The generic revision prompt asks an agent to "address every requested change",
# and for a *plan* there is a way to do that which changes nothing: write it
# down. On run-0b55ad49 a review named the exact file, line and fix for a
# test-suite failure; the lead reproduced it verbatim under `## Integration
# Notes`; no delegated task mentioned it; eighty minutes later the file was
# byte-for-byte unchanged. The relay worked. The assignment never happened.
# ---------------------------------------------------------------------------


def _milestone(assignments=None, notes=None):
    from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask

    return MilestonePlanOutput(
        selected_sprint_goal="goal",
        delegated_tasks=[
            SpecialistTask(specialist_role="testing", task_description="write tests",
                           acceptance_criteria=["they pass"])
        ],
        integration_notes=notes or [],
        review_task_assignments=assignments or [],
    )


class _PlanningAgent:
    def __init__(self, plan):
        self._plan = plan

    def invoke(self, request, config=None):
        return {"structured_response": self._plan, "messages": []}


def _gated_lead(state, agent):
    return _run_gated_agent(
        state,
        {"configurable": {"thread_id": "thread-outer"}},
        stage_name="technical_lead",
        agent=agent,
        initial_request={"messages": []},
        output_key="milestone_plan",
        next_stage="specialist_dispatch",
    )


def test_a_revision_that_changes_nothing_is_refused():
    """The proof is an identical task list, not an empty bespoke field.

    Measured on run-95ca3f72: the lead left `review_task_assignments` empty on
    three fresh conversations while returning the same seven tasks each time.
    An empty field alone does not prove the work was unassigned; an unchanged
    task list does.
    """
    from app.graph.workflow import unassigned_review_changes

    before = _milestone(notes=["some note"])
    unchanged = _milestone(notes=["Add jest.setup.js with the TextEncoder polyfill"])

    refusal = unassigned_review_changes(unchanged, revising=True, previous=before)

    assert refusal is not None
    assert "same tasks" in refusal


def test_a_revision_that_changes_the_tasks_is_accepted_without_the_field():
    """A model that will not fill a bespoke field can still do the work."""
    from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
    from app.graph.workflow import unassigned_review_changes

    before = _milestone()
    after = MilestonePlanOutput(
        selected_sprint_goal="goal",
        delegated_tasks=[
            SpecialistTask(specialist_role="testing", task_description="write tests",
                           acceptance_criteria=["they pass"]),
            SpecialistTask(specialist_role="testing", task_description="add jest.setup.js",
                           acceptance_criteria=["TextEncoder defined"]),
        ],
    )

    assert unassigned_review_changes(after, revising=True, previous=before) is None


def test_a_revision_that_names_the_task_proceeds():
    from app.graph.workflow import unassigned_review_changes

    assigned = _milestone(assignments=["Fix the TextEncoder polyfill -> task 1 (testing)"])

    assert unassigned_review_changes(assigned, revising=True, previous=_milestone()) is None


def test_a_first_plan_needs_no_assignments():
    """Nothing has been reviewed yet; requiring assignments would block every run."""
    from app.graph.workflow import unassigned_review_changes

    assert unassigned_review_changes(_milestone(), revising=False, previous=None) is None


def test_the_revision_request_asks_for_assignment_not_acknowledgement():
    """"Address every requested change" is what allowed a note to count."""
    from app.agents.technical_lead import build_milestone_revision_request

    content = build_milestone_revision_request(
        "{}", ["Fix the TextEncoder polyfill in tests/filter.test.js"]
    )["messages"][0]["content"]

    assert "DELEGATED TASK" in content
    assert "integration_notes" in content, "the failure mode must be named"
    assert "review_task_assignments" in content
    # And the original comment still reaches the agent verbatim.
    assert "tests/filter.test.js" in content


def test_an_unassigned_revision_retries_before_failing_the_run():
    """One lapse must not discard every stage that came before it.

    The guard is right that a change nobody owns will not be made - but failing
    the run for a single omission throws away hours of work when asking again on
    a clean conversation usually suffices. Seen on run-95ca3f72: the milestone
    reviewer requested changes, the re-plan omitted the assignments once, and
    the whole run stopped.
    """
    from app.graph.workflow import _max_structured_retries

    assert _max_structured_retries() >= 1


def test_the_retry_budget_is_shared_with_the_structured_response_retry():
    """Both remedies are the same act: abandon the conversation and ask again."""
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    assert "technical_lead:assignments" in source
    assert "structured_retries" in source


class _Review:
    """The reviewer's output, shaped like MilestoneReviewOutput."""

    def __init__(self, findings=(), acceptance_evidence=""):
        self.status = "changes_required"
        self.findings = list(findings)
        self.acceptance_evidence = acceptance_evidence


def test_a_review_with_no_findings_still_says_what_to_change():
    """`findings` is optional in the schema, so a model may leave it empty.

    Observed on run-95ca3f72: `changes_required` with `findings == []` and
    three concrete complaints in `acceptance_evidence`. Joining the empty list
    produced `""`, and the technical lead was asked to revise a plan against a
    revision request that contained nothing.
    """
    from app.graph.workflow import _milestone_changes_requested

    evidence = 'The root `package.json` test script is `exit 1`; `npm test` exits 1.'
    text = _milestone_changes_requested(_Review(acceptance_evidence=evidence))

    assert text is not None
    assert "exit 1" in text
    assert "required change" in text


def test_a_review_that_says_nothing_anywhere_is_refused():
    """A reviewer that cannot be obeyed is a failure of the review, not the lead."""
    from app.graph.workflow import _milestone_changes_requested

    assert _milestone_changes_requested(_Review(acceptance_evidence="   ")) is None


def test_findings_are_preferred_when_the_reviewer_records_them():
    from app.graph.workflow import _milestone_changes_requested

    class _Finding:
        severity = "blocking"
        category = "tests"
        description = "no tests ran"
        required_remediation = "run them"

    text = _milestone_changes_requested(
        _Review(findings=[_Finding()], acceptance_evidence="ignored")
    )

    assert text == "[blocking] tests: no tests ran -> run them"
    assert "ignored" not in text


def test_a_blank_comment_does_not_count_as_a_requested_change():
    """`[""]` is a truthy list. It used to select the revising branch."""
    from app.graph.workflow import _collect_required_changes

    assert _collect_required_changes({"revision_comments": ["", "  "]}) == []
    assert _collect_required_changes({"revision_comments": ["", "fix it"]}) == ["fix it"]
