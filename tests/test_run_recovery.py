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
