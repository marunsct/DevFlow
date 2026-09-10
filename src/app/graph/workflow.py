"""Top-level LangGraph controller wiring the role agents together.

Every earlier agent module is a narrow, independently testable role worker
(Steps 3.1-5.4). None of them decide when the *next* role should run, whether
rejected architecture goes back to the Principal Architect, or how a paused
approval resumes the rest of the pipeline. That is this module's job: a single
`StateGraph` that owns the stage sequence, the architecture-review retry loop,
the optional user-review gates (Step 3.3), the specialist dispatch loop, and
the per-sprint remediation loop (Step 5.4).

Two different kinds of pause
----------------------------
The workflow can stop for two reasons, and they are deliberately not the same
mechanism:

1. **Mandatory approval** (`awaiting_approval:<stage>`) - a role agent wants to
   write an artifact, and Step 3.2 requires a human to approve, edit, or reject
   that write before anything is saved. Resume with `resume_pending_approval`.
2. **Optional user review** (`awaiting_user_review:<point>`) - an artifact
   already exists and the run configuration asked a human to look at it
   (Step 3.3). The human may approve, request changes, or explicitly skip.
   Resume with `resume_pending_review`.

A skip is recorded as its own status and never looks like an approval, and an
optional review can never bypass the mandatory architecture gate: the review
node only runs *after* `architecture_review` has already returned `approved`.

Design note on approvals (read this before changing routing logic):
Each role agent already pauses its *own* internal graph for a human decision on
`write_artifact`. We deliberately do **not** try to bridge that inner pause into
a genuine LangGraph `interrupt()` on this outer graph - an early prototype of
that approach was tested and found to silently corrupt the inner agent's
conversation, because a paused node function re-executes *every* statement
before its `interrupt()` call on resume, including the "real" call that started
the inner agent. Instead, this graph uses a simpler, verified pattern: a `stage`
field in the graph state records exactly where a run is. A conditional entry
router reads that field on every `invoke` and enters at the matching node, so
calling `invoke` again after a human decision correctly resumes the *inner*
agent (via `resume_with_decision`) instead of restarting it.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agents.approval import extract_pending_approval, resume_with_decision
from app.agents.architecture_reviewer import (
    ArchitectureReviewOutput,
    build_architecture_review_request,
    create_architecture_reviewer_agent,
)
from app.agents.milestone_reviewer import (
    MilestoneReviewOutput,
    build_milestone_review_request,
    create_milestone_reviewer_agent,
)
from app.agents.security_reviewer import (
    SecurityReviewOutput,
    build_security_review_request,
    create_security_reviewer_agent,
)
from app.agents.principal_architect import (
    ArchitectureDecisionRecord,
    TechnicalSpecificationOutput,
    build_architecture_request,
    build_architecture_revision_request,
    create_principal_architect_agent,
)
from app.agents.product_manager import ProductManagerOutput, build_intake_request, create_product_manager_agent
from app.agents.role_agent import create_role_agent
from app.agents.scrum_master import SprintPlanOutput, build_sprint_planning_request, create_scrum_master_agent
from app.agents.stack_selector import StackSelectorOutput, create_stack_selector_agent
from app.agents.specialists import (
    ReportedDefect,
    SpecialistOutput,
    build_defect_fix_request,
    build_specialist_task_request,
    build_test_run_request,
    create_specialist_agent,
)
from app.agents.technical_lead import (
    MilestonePlanOutput,
    build_milestone_planning_request,
    create_technical_lead_agent,
)
from app.agents.tools_models import ToolsAndModelsOutput, build_tools_models_request, create_tools_models_agent
from app.documents import DocumentContent
from app.graph.checkpointing import build_checkpointer
from app.review import (
    ReviewRerunLimitExceeded,
    approve_review,
    build_revision_prompt,
    request_changes,
    skip_review,
    start_review,
)
from app.sprint import (
    Defect,
    RemediationCycle,
    RemediationLimitExceeded,
    build_defect_report,
    is_sprint_acceptable,
    mark_defect_fixed,
    record_test_run,
    start_remediation,
)
from app.state import HumanApprovalRequest, RepositoryContext, ReviewStatus, WorkflowStage
from app.tracing import trace_metadata

logger = logging.getLogger(__name__)

MAX_ARCHITECTURE_REVISIONS = 3

MAX_SPECIFICATION_REPAIRS = 2
"""How many times to ask the architect to refill sections it left empty.

Separate from `MAX_ARCHITECTURE_REVISIONS` because it is a different failure:
not "the reviewer disagrees with the design" but "the structured output came
back missing sections the agent had already written". Spending review cycles on
that wastes two model calls per attempt and burns the revision budget on a
defect the reviewer cannot fix.
"""
"""Bound how many times architecture review can send work back to the Principal
Architect before the run is marked failed instead of looping forever."""

MAX_MILESTONE_REVISIONS = 3
"""Bound how many times milestone review can send work back to the Technical
Lead before the run falls back to a human review instead of looping forever."""

MAX_REMEDIATION_ATTEMPTS = 3
"""Bound one test-fix-retest passes one milestone gets; see `app.sprint`."""

DEFAULT_RECURSION_LIMIT = 100
"""Raise LangGraph's superstep ceiling above its default of 25.

This graph legitimately takes many supersteps in one `invoke`: the specialist
dispatch node loops back to itself once per delegated task, and the remediation
loop can restart that whole sequence. A six-task milestone that needs two
remediation passes already exceeds the default, and hitting the ceiling would
surface as a confusing `GraphRecursionError` rather than as the bounded
escalation this workflow actually implements (`MAX_REMEDIATION_ATTEMPTS`).
"""

APPROVAL_PAUSE_PREFIX = "awaiting_approval:"
"""Stage prefix meaning: a role agent's artifact write needs a human decision."""

REVIEW_PAUSE_PREFIX = "awaiting_user_review:"
"""Stage prefix meaning: an optional human review session is open."""

_PAUSE_PREFIXES = (APPROVAL_PAUSE_PREFIX, REVIEW_PAUSE_PREFIX)

SPECIFICATION_REVIEW = "technical_specification"
"""Review point: the completed technical specification (Step 3.3)."""

SPRINT_REVIEW = "sprint"
"""Review point: a completed sprint/milestone (Step 3.3)."""

PRODUCT_INTAKE_REVIEW = "product_intake"
"""Review point: the refined product intake document."""

_REVIEW_NODES = {
    SPECIFICATION_REVIEW: "user_review_specification",
    SPRINT_REVIEW: "user_review_sprint",
    PRODUCT_INTAKE_REVIEW: "user_review_product_intake",
}
"""Maps a review point to the node that owns its gate, so the entry router can
re-enter the right node when a paused review is resumed."""

_REVIEW_STAGES = {
    SPECIFICATION_REVIEW: WorkflowStage.ARCHITECTURE,
    SPRINT_REVIEW: WorkflowStage.IMPLEMENTATION,
    PRODUCT_INTAKE_REVIEW: WorkflowStage.INTAKE,
}
"""Maps a review point to the `WorkflowStage` recorded on its `ReviewStatus`,
so an auditor can tell which lifecycle stage a review decision belongs to."""

_NODE_NAMES = frozenset(
    {
        "product_manager",
        "user_review_product_intake",
        "tools_models",
        "stack_selector",
        "principal_architect",
        "architecture_review",
        "user_review_specification",
        "scrum_master",
        "technical_lead",
        "specialist_dispatch",
        "test_and_triage",
        "defect_remediation",
        "security_review",
        "milestone_review",
        "user_review_sprint",
        "sprint_advance",
        "complete",
        "failed",
    }
)
"""Every node a router may name as the next stage.

This must stay in sync with the nodes registered on the graph below: it is the
key set for both the entry router and every `_route_from_stage` edge map, so a
node missing here is unreachable and raises `KeyError` the moment a router
returns its name. `test_graph_routing` asserts the two sets match."""

_ITERATED_STAGE_OWNERS = {
    "specialist_": "specialist_dispatch",
    "test_round_": "test_and_triage",
    "defect_fix_": "defect_remediation",
}
"""Maps an iterated stage-name prefix to the node that owns it.

Three nodes run a loop and name each iteration's inner agent thread after the
iteration (`specialist_backend_0`, `test_round_2`, `defect_fix_1_0`) rather than
after the node. Those names are not graph nodes, so when one of them pauses for
approval the entry router uses this map to re-enter the node that owns the loop.
"""


class WorkflowGraphState(TypedDict, total=False):
    """Working memory for the top-level workflow graph.

    Deliberately separate from `app.state.WorkflowState`: that model is the
    audit/reporting contract for external consumers, while this is the
    controller's own scratchpad, holding each stage's structured output plus
    the fields the routing logic needs (`stage`, revision/attempt counters,
    the pending-approval and pending-review bridge fields).
    """

    document: DocumentContent
    repository: RepositoryContext
    stage: str

    product_intake: ProductManagerOutput
    tools_models: ToolsAndModelsOutput
    stack_selection: StackSelectorOutput
    technical_specification: TechnicalSpecificationOutput
    architecture_review: ArchitectureReviewOutput
    architecture_revision_count: int
    specification_repair_count: int
    milestone_revision_count: int
    sprint_plan: SprintPlanOutput
    current_sprint_index: int
    milestone_plan: MilestonePlanOutput
    specialist_task_index: int
    specialist_outputs: dict[str, SpecialistOutput]
    remediation: RemediationCycle
    defect_cursor: int
    test_round: int
    milestone_review: MilestoneReviewOutput
    security_review: SecurityReviewOutput

    # Optional user review sessions (Step 3.3). `review_policy` is opt-in per
    # review point, so a run with no policy behaves exactly as it did before
    # review gates existed.
    review_policy: dict[str, bool]
    reviewer: str
    reviews: dict[str, ReviewStatus]
    pending_review: ReviewStatus | None
    pending_review_decision: dict[str, Any] | None
    revision_comments: list[str]

    pending_approval: HumanApprovalRequest | None
    pending_inner_thread_id: str | None
    inner_thread_ids: list[str]
    pending_decision: dict[str, Any] | None
    error: str | None


_CONTEXT_OVERFLOW_MARKERS = (
    "maximum context length",
    "context_length_exceeded",
    "context length exceeded",
    "too many tokens",
    "reduce the length of the messages",
    "prompt is too long",
)


def _is_context_overflow(error: BaseException) -> bool:
    """Whether this exception is the model refusing an oversized prompt.

    Matched on the message because providers disagree on the type: the same
    condition arrives as BadRequestError, OpenAIInvalidRequestError, or a plain
    ValueError depending on which client is in front of it.
    """
    return any(marker in str(error).lower() for marker in _CONTEXT_OVERFLOW_MARKERS)


def _context_overflow_update(stage_name: str, error: BaseException) -> dict[str, Any]:
    """State update for a stage the model refused as too large.

    `stage` must name a real node. `_route_from_stage` returns it verbatim and
    the conditional-edge map is built from `_NODE_NAMES`, so any other value is
    a KeyError that kills the run instead of failing it - which is worse than
    the overflow it was meant to handle.
    """
    logger.error("Context overflow in stage %s: %s", stage_name, error)
    return {
        "stage": "failed",
        "error": (
            f"The '{stage_name}' stage exceeded the model's context window even after "
            "compaction.\n\n"
            "If this stage is architecture_review or scrum_master, the specification "
            "itself is too large for one request: lower CTX_SPECIFICATION_BUDGET.\n"
            "If it is principal_architect, lower CTX_ARCHITECT_DOCUMENT_BUDGET.\n"
            "Otherwise lower CTX_MAX_TOKENS so compaction triggers sooner, or use a "
            "model with a larger window.\n\n"
            "Resuming this run retries the same stage; change the setting first, or "
            "the retry will overflow identically."
        ),
        "pending_approval": None,
        "pending_inner_thread_id": None,
        "pending_decision": None,
    }


def _is_paused(stage: str) -> bool:
    """Return whether a stage value represents a pause rather than a next node."""
    return stage.startswith(_PAUSE_PREFIXES)


def _is_awaiting_approval_for(state: WorkflowGraphState, stage_name: str) -> bool:
    """Return whether `state` is parked on this stage's own approval gate."""
    return state.get("stage", "") == f"{APPROVAL_PAUSE_PREFIX}{stage_name}"


def _route_from_stage(state: WorkflowGraphState) -> str:
    """Shared conditional-edge router used after every gated node.

    A node sets `stage` to the literal name of whatever should run next
    (including `"complete"` or `"failed"`), or to a paused value prefixed with
    `awaiting_approval:` / `awaiting_user_review:`. This router only has to tell
    those two cases apart: a paused run ends this `invoke` so control returns to
    the human, and everything else routes to the named node.
    """
    stage = state.get("stage", "")
    if _is_paused(stage):
        return END
    return stage


def _entry_router(state: WorkflowGraphState) -> str:
    """Conditional entry point: decide which node this `invoke` call should enter.

    A fresh run has no `stage` yet, so it starts at `product_manager`. A resumed
    run's checkpointed `stage` names why it paused:

    - `awaiting_user_review:<point>` re-enters that review point's gate node.
    - `awaiting_approval:<stage_name>` re-enters the node that paused.
      `<stage_name>` is either a real node name (most stages) or one of many
      per-task specialist stage names like `"specialist_backend_0"`, which all
      route back to the single `specialist_dispatch` node that dispatches them.
    """
    stage = state.get("stage", "product_manager")
    if stage.startswith(REVIEW_PAUSE_PREFIX):
        review_point = stage.split(":", 1)[1]
        return _REVIEW_NODES.get(review_point, "failed")
    if stage.startswith(APPROVAL_PAUSE_PREFIX):
        inner_stage_name = stage.split(":", 1)[1]
        if inner_stage_name in _NODE_NAMES:
            return inner_stage_name
        # Three node types name their stages per iteration rather than after
        # themselves, so their pauses need mapping back to the owning node.
        for prefix, owning_node in _ITERATED_STAGE_OWNERS.items():
            if inner_stage_name.startswith(prefix):
                return owning_node
        return "failed"
    return stage


def _run_gated_agent(
    state: WorkflowGraphState,
    config: RunnableConfig,
    *,
    stage_name: str,
    agent: Any,
    initial_request: dict[str, Any],
    output_key: str,
    next_stage: str,
) -> dict[str, Any]:
    """Run one role agent to completion or pause the workflow waiting for approval.

    `stage_name` becomes part of the inner agent's own `thread_id` (namespaced
    under this run's outer `thread_id`), so distinct stages never share a
    checkpoint even though every inner agent uses the same checkpointer
    instance as the outer graph.
    """
    outer_thread_id = config["configurable"]["thread_id"]

    pending_decision = state.get("pending_decision")
    if pending_decision is not None:
        inner_thread_id = state.get("pending_inner_thread_id")
        if not inner_thread_id:
            inner_thread_id = f"{outer_thread_id}:{stage_name}:{uuid.uuid4().hex[:8]}"
        try:
            result = resume_with_decision(agent, inner_thread_id, pending_decision)
        except Exception as exc:  # noqa: BLE001 - re-raised unless it is overflow
            if not _is_context_overflow(exc):
                raise
            return _context_overflow_update(stage_name, exc)
    elif _is_awaiting_approval_for(state, stage_name) and state.get("pending_inner_thread_id"):
        # Re-entered our own approval pause with no decision attached. That
        # happens whenever something resumes the run without answering the gate
        # (the /resume endpoint, a retry after a transient error).
        #
        # Falling through to the `else` branch would mint a *fresh* inner thread
        # and re-run the whole agent from scratch, which throws away the paused
        # inner thread, burns a full context window, and lands back on this exact
        # gate - a loop that makes no progress and costs a model call each time.
        # Re-surface the pause instead: only a decision can clear it.
        return {
            "stage": f"{APPROVAL_PAUSE_PREFIX}{stage_name}",
            "pending_approval": state.get("pending_approval"),
            "pending_inner_thread_id": state.get("pending_inner_thread_id"),
            "pending_decision": None,
        }
    else:
        # Append a UUID to force a fresh context window for new attempts.
        # This prevents the LLM from drowning in the message history of previous failed attempts.
        inner_thread_id = f"{outer_thread_id}:{stage_name}:{uuid.uuid4().hex[:8]}"
        try:
            result = agent.invoke(initial_request, config={"configurable": {"thread_id": inner_thread_id}})
        except Exception as exc:  # noqa: BLE001 - re-raised unless it is overflow
            if not _is_context_overflow(exc):
                raise
            return _context_overflow_update(stage_name, exc)

    if result.get("__interrupt__"):
        approval = extract_pending_approval(
            result, state["repository"].root_path, requested_by=stage_name, stage=stage_name
        )
        return {
            "stage": f"{APPROVAL_PAUSE_PREFIX}{stage_name}",
            "pending_approval": approval,
            "pending_inner_thread_id": inner_thread_id,
            "pending_decision": None,
            "inner_thread_ids": [*state.get("inner_thread_ids", []), inner_thread_id],
        }

    structured_response = result.get("structured_response")
    if structured_response is None:
        raise ValueError(
            f"Agent '{stage_name}' failed to produce a structured response. "
            "This often happens if the context limit or max token limit was reached."
        )

    return {
        output_key: structured_response,
        "stage": next_stage,
        "pending_approval": None,
        "pending_inner_thread_id": None,
        "pending_decision": None,
        # Recorded so a finished run can reclaim the checkpoints of every inner
        # agent thread it created; each attempt mints a fresh id, so without this
        # they accumulate unreachable forever.
        "inner_thread_ids": [*state.get("inner_thread_ids", []), inner_thread_id],
    }


# Sections a specification is not usable without. `domain_model` and
# `open_questions` are excluded: a small product legitimately has neither.
_REQUIRED_SPECIFICATION_SECTIONS = (
    "component_boundaries",
    "api_and_event_contracts",
    "data_flows",
    "security_and_privacy",
    "reliability_and_observability",
    "testing",
    "deployment",
    "acceptance_criteria",
)


def _incomplete_specification_sections(specification: Any) -> list[str]:
    """Return the required sections this specification left empty.

    Every list field on `TechnicalSpecificationOutput` carries
    `default_factory=list`, so a structured response that simply omits a section
    validates cleanly and arrives as `[]`. In practice the architect writes a
    complete document to disk and then returns a structured response covering
    only part of it, and nothing downstream notices: the reviewer reads the
    structured output, correctly reports the sections as empty, and the run
    burns its whole revision budget on a defect no amount of re-reviewing can
    fix. Catching it here turns that into one targeted retry.
    """
    if specification is None:
        return []
    return [
        section
        for section in _REQUIRED_SPECIFICATION_SECTIONS
        if not getattr(specification, section, None)
    ]


def _collect_required_changes(state: WorkflowGraphState) -> list[str]:
    """Gather everything the Principal Architect must fix in its next revision.

    Two independent sources can reject a specification, and both must reach the
    architect or it will simply reproduce the rejected version:

    - the Senior Architect Reviewer's structured findings (Step 4.3), and
    - a human reviewer's comments from an optional review session (Step 3.3).

    Returns an empty list on the first pass, which is how the caller knows to
    send the original brief instead of a revision request.
    """
    changes: list[str] = []

    review = state.get("architecture_review")
    if review is not None and review.status == "changes_required":
        changes.extend(
            f"[{finding.severity}] {finding.description} Required remediation: {finding.required_remediation}"
            for finding in review.findings
        )

    changes.extend(state.get("revision_comments", []))
    return changes


def _review_enabled(state: WorkflowGraphState, review_point: str) -> bool:
    """Return whether the run configuration asked for this optional review.

    Reviews are opt-in. A run that never sets `review_policy` skips both gates
    entirely, which keeps the mandatory approval and architecture gates as the
    only things that can stop a default run.
    """
    return bool(state.get("review_policy", {}).get(review_point, False))


def _run_review_gate(
    state: WorkflowGraphState,
    config: RunnableConfig,
    *,
    review_point: str,
    artifact_id: str,
    approved_next: str,
    changes_next: str,
) -> dict[str, Any]:
    """Open an optional human review session, or apply the decision that closes it.

    This node is entered twice per review round. The first time there is no
    decision yet, so it creates a `ReviewStatus` and pauses. The human then
    calls `resume_pending_review`, which puts their decision in state and
    re-enters this node, where the decision is applied:

    - `approve` / `skip` -> continue to `approved_next`. These are recorded as
      *different* statuses on purpose: skipping must stay distinguishable from
      approval for anyone auditing the run later.
    - `request_changes` -> go back to `changes_next` with the comment attached,
      producing a new revision rather than overwriting history.

    Exceeding the rerun limit fails the run with an actionable message instead
    of looping the same role agent on a review that never converges.
    """
    thread_id = config["configurable"]["thread_id"]
    reviews = dict(state.get("reviews", {}))
    decision = state.get("pending_review_decision")

    if decision is None:
        review = reviews.get(review_point) or start_review(
            run_id=thread_id,
            thread_id=thread_id,
            stage=_REVIEW_STAGES[review_point],
            artifact_id=artifact_id,
            reviewer=state.get("reviewer", "unassigned"),
        )
        reviews[review_point] = review
        return {
            "stage": f"{REVIEW_PAUSE_PREFIX}{review_point}",
            "reviews": reviews,
            "pending_review": review,
            "pending_review_decision": None,
        }

    review = reviews.get(review_point)
    if review is None:
        # Defensive: a decision arrived for a review that was never opened.
        # Failing loudly beats silently treating it as an approval.
        return {
            "stage": "failed",
            "pending_review": None,
            "pending_review_decision": None,
            "error": f"Received a review decision for '{review_point}', but no review session is open.",
        }

    decision_type = decision.get("type")
    comment = decision.get("comment")

    if decision_type == "approve":
        review = approve_review(review, comment=comment)
        next_stage = approved_next
    elif decision_type == "skip":
        review = skip_review(review)
        next_stage = approved_next
    elif decision_type == "request_changes":
        if not comment:
            return {
                "stage": "failed",
                "pending_review": None,
                "pending_review_decision": None,
                "error": (
                    f"Review decision 'request_changes' for '{review_point}' needs a comment "
                    "saying what must change; the role agent cannot revise without one."
                ),
            }
        try:
            review = request_changes(review, comment=comment)
        except ReviewRerunLimitExceeded as exc:
            reviews[review_point] = review
            return {
                "stage": "failed",
                "reviews": reviews,
                "pending_review": None,
                "pending_review_decision": None,
                "error": str(exc),
            }
        next_stage = changes_next
    else:
        return {
            "stage": "failed",
            "pending_review": None,
            "pending_review_decision": None,
            "error": (
                f"Unknown review decision type {decision_type!r} for '{review_point}'. "
                "Expected 'approve', 'skip', or 'request_changes'."
            ),
        }

    reviews[review_point] = review
    update: dict[str, Any] = {
        "stage": next_stage,
        "reviews": reviews,
        "pending_review": None,
        "pending_review_decision": None,
    }
    if decision_type == "request_changes":
        # Carry the comment forward so the role agent revising the artifact
        # sees exactly what the human asked for.
        revision_comments = [comment]
        if edited_content := decision.get("edited_content"):
            revision_comments.append(
                f"The user has uploaded a modified version of the artifact. Please update your structured output to perfectly reflect this modified version:\n\n<MODIFIED_ARTIFACT>\n{edited_content}\n</MODIFIED_ARTIFACT>"
            )
        update["revision_comments"] = revision_comments
    return update


def _effective_base_environment() -> dict[str, str]:
    """The environment a run's model overrides are layered on top of.

    Falls back to the raw environment when the settings store is unreachable:
    the deployed configuration is still a valid one, and a run must not fail
    because a settings lookup did.
    """
    import os

    try:
        from app.server.runtime_settings import effective_environment

        return effective_environment()
    except Exception:  # noqa: BLE001 - see docstring
        return dict(os.environ)


def build_workflow_graph(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | None = None,
    allow_subdirectories: bool = True,
    model_overrides: dict[str, str | None] | None = None,
):
    """Compile the top-level workflow graph wiring every role agent together.

    `model`, `checkpointer`, and `repo_root` are threaded through to every
    inner role agent. Passing one shared `checkpointer` (the default if none
    is given) is safe: each inner agent's thread ids are namespaced under the
    outer run's `thread_id`, so nothing collides even though they all share
    one in-memory store.
    """
    shared_checkpointer = checkpointer or build_checkpointer()
    
    if model_overrides:
        from app.config import load_settings
        from app.models import build_default_chat_model

        # The base is the *effective* environment - the deployed one plus any
        # setting an administrator has changed - not this container's raw
        # environment. A run pins its provider and model, but the address the
        # model is served from is deployment configuration and must come from
        # whatever it is now.
        base_env = _effective_base_environment()
        mapping = {
            "llm_provider": "LLM_PROVIDER",
            "openai_base_url": "OPENAI_BASE_URL",
            "openai_api_key": "OPENAI_API_KEY",
            "anthropic_api_key": "ANTHROPIC_API_KEY",
            "google_api_key": "GOOGLE_API_KEY",
            "model_name": "OPENAI_MODEL",
        }
        for k, v in model_overrides.items():
            if v:
                base_env[mapping[k]] = v
                
        settings = load_settings(base_env)
        model = build_default_chat_model(settings)

    def product_manager_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        agent = create_product_manager_agent(model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
        request = build_intake_request(state["document"], state["repository"])
        update = _run_gated_agent(
            state,
            config,
            stage_name="product_manager",
            agent=agent,
            initial_request=request,
            output_key="product_intake",
            next_stage="tools_models",
        )
        if _is_paused(update["stage"]):
            return update
        
        # After product manager finishes, optionally route to review
        next_stage = "user_review_product_intake" if _review_enabled(state, PRODUCT_INTAKE_REVIEW) else "tools_models"
        update["stage"] = next_stage
        return update

    def user_review_product_intake_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return _run_review_gate(
            state,
            config,
            review_point=PRODUCT_INTAKE_REVIEW,
            artifact_id="product-intake",
            approved_next="tools_models",
            changes_next="product_manager",
        )

    def tools_models_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        agent = create_tools_models_agent(model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
        intake_text = state["product_intake"].model_dump_json(indent=2) if hasattr(state["product_intake"], "model_dump_json") else __import__("json").dumps(state["product_intake"], indent=2)
        request = build_tools_models_request(intake_text, state["repository"])
        update = _run_gated_agent(
            state,
            config,
            stage_name="tools_models",
            agent=agent,
            initial_request=request,
            output_key="tools_models",
            next_stage="stack_selector",
        )
        return update

    def stack_selector_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        agent = create_stack_selector_agent(model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
        request = {"messages": [{"role": "user", "content": f"Product Intake: {state['product_intake']}\nTools: {state.get('tools_models')}"}]}
        return _run_gated_agent(
            state,
            config,
            stage_name="stack_selector",
            agent=agent,
            initial_request=request,
            output_key="stack_selection",
            next_stage="principal_architect",
        )

    def principal_architect_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        agent = create_principal_architect_agent(model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)

        # A rejected specification must come back with the reasons attached,
        # otherwise the architect reproduces the version that was rejected.
        required_changes = _collect_required_changes(state)
        previous_specification = state.get("technical_specification")
        if required_changes and previous_specification is not None:
            request = build_architecture_revision_request(
                previous_specification_text=previous_specification.model_dump_json(indent=2) if hasattr(previous_specification, "model_dump_json") else __import__("json").dumps(previous_specification, indent=2),
                required_changes=required_changes,
                product_intake_text=state["product_intake"].model_dump_json(indent=2) if hasattr(state["product_intake"], "model_dump_json") else __import__("json").dumps(state["product_intake"], indent=2),
                tools_and_models_text=state["tools_models"].model_dump_json(indent=2) if hasattr(state["tools_models"], "model_dump_json") else __import__("json").dumps(state["tools_models"], indent=2),
                stack_selection_text=state["stack_selection"].model_dump_json(indent=2) if hasattr(state["stack_selection"], "model_dump_json") else __import__("json").dumps(state["stack_selection"], indent=2) if "stack_selection" in state else "",
                repository=state["repository"],
                document=state["document"],
            )
        else:
            request = build_architecture_request(
                state["product_intake"].model_dump_json(indent=2) if hasattr(state["product_intake"], "model_dump_json") else __import__("json").dumps(state["product_intake"], indent=2),
                state["tools_models"].model_dump_json(indent=2) if hasattr(state["tools_models"], "model_dump_json") else __import__("json").dumps(state["tools_models"], indent=2),
                state["stack_selection"].model_dump_json(indent=2) if hasattr(state["stack_selection"], "model_dump_json") else __import__("json").dumps(state["stack_selection"], indent=2) if "stack_selection" in state else "",
                state["repository"],
                state["document"],
            )

        update = _run_gated_agent(
            state,
            config,
            stage_name="principal_architect",
            agent=agent,
            initial_request=request,
            output_key="technical_specification",
            next_stage="architecture_review",
        )
        if not _is_paused(update["stage"]):
            # Consumed: the revision request above already delivered them, so
            # a later rerun must not re-apply stale comments.
            update["revision_comments"] = []

            missing = _incomplete_specification_sections(update.get("technical_specification"))
            repairs = state.get("specification_repair_count", 0)
            if missing and repairs < MAX_SPECIFICATION_REPAIRS:
                # Straight back to the architect with the exact field names,
                # without spending an architecture-review cycle on it.
                update["specification_repair_count"] = repairs + 1
                update["stage"] = "principal_architect"
                update["revision_comments"] = [
                    "Your structured response left these required sections empty: "
                    + ", ".join(missing)
                    + ". The document you wrote may already cover them - the problem is the "
                    "structured output, not the prose. Return the specification again with "
                    "every one of those fields populated from the document; do not drop the "
                    "sections that are already filled in."
                ]
            elif not missing:
                update["specification_repair_count"] = 0
        return update

    def architecture_review_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        agent = create_architecture_reviewer_agent(model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
        spec_text = state["technical_specification"].model_dump_json(indent=2)
        request = build_architecture_review_request(spec_text, state["repository"].root_path)
        update = _run_gated_agent(
            state,
            config,
            stage_name="architecture_review",
            agent=agent,
            initial_request=request,
            output_key="architecture_review",
            next_stage="scrum_master",  # placeholder; always overridden below
        )
        if _is_paused(update["stage"]):
            return update

        review: ArchitectureReviewOutput = update["architecture_review"]
        if review.status == "approved":
            # The mandatory gate passed. Only now may an optional human review
            # session run; it can never substitute for this gate.
            update["stage"] = (
                "user_review_specification" if _review_enabled(state, SPECIFICATION_REVIEW) else "scrum_master"
            )
        else:
            revision_count = state.get("architecture_revision_count", 0) + 1
            update["architecture_revision_count"] = revision_count
            if revision_count >= MAX_ARCHITECTURE_REVISIONS:
                update["stage"] = "failed"
                update["error"] = f"Architecture review rejected after reaching the limit of {MAX_ARCHITECTURE_REVISIONS} revisions."
            else:
                update["stage"] = "principal_architect"
        return update

    def user_review_specification_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return _run_review_gate(
            state,
            config,
            review_point=SPECIFICATION_REVIEW,
            artifact_id="technical-specification",
            approved_next="scrum_master",
            changes_next="principal_architect",
        )

    def scrum_master_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        agent = create_scrum_master_agent(model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
        spec_text = state["technical_specification"].model_dump_json(indent=2)
        request = build_sprint_planning_request(spec_text, state["repository"].root_path)
        update = _run_gated_agent(
            state,
            config,
            stage_name="scrum_master",
            agent=agent,
            initial_request=request,
            output_key="sprint_plan",
            next_stage="technical_lead",
        )
        if not _is_paused(update["stage"]):
            update["current_sprint_index"] = 0
        return update

    def technical_lead_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        agent = create_technical_lead_agent(model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
        plan_text = state["sprint_plan"].model_dump_json(indent=2)
        sprint_index = state.get("current_sprint_index", 0)
        sprints = state["sprint_plan"].sprints
        current_goal = sprints[sprint_index].goal if sprints and sprint_index < len(sprints) else ""

        # A sprint review that requested changes re-enters here. Reuse the
        # shared revision prompt so the lead sees its previous milestone plan
        # alongside the comments, rather than re-planning from scratch.
        revision_comments = state.get("revision_comments", [])
        previous_milestone = state.get("milestone_plan")
        if revision_comments and previous_milestone is not None:
            request = {
                "messages": [
                    {
                        "role": "user",
                        "content": build_revision_prompt(
                            previous_milestone.model_dump_json(indent=2), revision_comments
                        ),
                    }
                ]
            }
        else:
            request = build_milestone_planning_request(plan_text, current_goal, state["repository"].root_path)
        update = _run_gated_agent(
            state,
            config,
            stage_name="technical_lead",
            agent=agent,
            initial_request=request,
            output_key="milestone_plan",
            next_stage="specialist_dispatch",
        )
        if _is_paused(update["stage"]):
            return update

        milestone: MilestonePlanOutput = update["milestone_plan"]
        update["remediation"] = start_remediation(milestone.selected_sprint_goal, max_attempts=MAX_REMEDIATION_ATTEMPTS)
        update["specialist_task_index"] = 0
        update["revision_comments"] = []
        return update

    def specialist_dispatch_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        milestone = state["milestone_plan"]
        tasks = milestone.delegated_tasks
        index = state.get("specialist_task_index", 0)

        if index < len(tasks):
            task = tasks[index]
            stage_name = f"specialist_{task.specialist_role}_{index}"
            agent = create_specialist_agent(
                task.specialist_role, model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories
            )
            request = build_specialist_task_request(
                task.task_description, task.acceptance_criteria, state["repository"].root_path
            )
            update = _run_gated_agent(
                state,
                config,
                stage_name=stage_name,
                agent=agent,
                initial_request=request,
                output_key="__specialist_result__",
                next_stage="specialist_dispatch",
            )
            if "__specialist_result__" not in update:
                return update  # paused waiting for approval on this task

            outputs = dict(state.get("specialist_outputs", {}))
            outputs[stage_name] = update.pop("__specialist_result__")
            update["specialist_outputs"] = outputs
            update["specialist_task_index"] = index + 1
            return update

        # Every delegated task is done, so the increment is built. Verification
        # is its own stage (Step 5.4): the Test Engineer runs the tests and
        # turns failures into tracked, owned defects.
        return {"stage": "test_and_triage"}

    def test_and_triage_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        """Run the tests for this milestone and triage every failure into a tracked defect.

        This is steps 2 and 3 of the plan's remediation loop. It runs after each
        implementation or fix round, so `test_round` gives every round its own
        inner thread id - reusing one thread would make the Test Engineer
        re-read a stale conversation instead of testing the current state.

        Outcomes:
        - failures found -> `defect_remediation` routes each defect to its owner
        - clean run -> the acceptance gate (`is_sprint_acceptable`) decides
          whether the sprint may be accepted at all
        - attempts exhausted -> `failed`, carrying the defect report as evidence
        """
        milestone = state["milestone_plan"]
        test_round = state.get("test_round", 0)
        outputs = state.get("specialist_outputs", {})
        changed_files = sorted({name for output in outputs.values() for name in output.changed_files})

        agent = create_specialist_agent(
            "testing", model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories
        )
        request = build_test_run_request(
            milestone.selected_sprint_goal, changed_files, state["repository"].root_path
        )
        update = _run_gated_agent(
            state,
            config,
            stage_name=f"test_round_{test_round}",
            agent=agent,
            initial_request=request,
            output_key="__test_result__",
            next_stage="test_and_triage",
        )
        if "__test_result__" not in update:
            return update  # paused waiting for approval on a test artifact

        test_result: SpecialistOutput = update.pop("__test_result__")
        reported: list[ReportedDefect] = list(test_result.defects)
        cycle = state.get("remediation") or start_remediation(
            milestone.selected_sprint_goal, max_attempts=MAX_REMEDIATION_ATTEMPTS
        )

        # The model reports what it found; only the workflow may set lifecycle
        # state, so every incoming defect starts as "open" regardless.
        new_defects = [
            Defect(
                description=item.description,
                severity=item.severity,
                reproduction_steps=item.reproduction_steps,
                expected_behavior=item.expected_behavior,
                actual_behavior=item.actual_behavior,
                affected_files=item.affected_files,
                owner=item.owner,
                regression_test_required=item.regression_test_required,
            )
            for item in reported
        ]

        try:
            cycle = record_test_run(
                cycle,
                command=["specialist", "testing", f"round-{test_round}"],
                passed=not new_defects,
                summary=f"{len(new_defects)} defect(s) found" if new_defects else "all applicable tests passed",
                new_defects=new_defects,
            )
        except RemediationLimitExceeded as exc:
            return {
                "stage": "user_review_sprint",
                "remediation": cycle,
                "test_round": test_round + 1,
            }

        base_update: dict[str, Any] = {
            "remediation": cycle,
            "test_round": test_round + 1,
            "pending_approval": None,
            "pending_inner_thread_id": None,
            "pending_decision": None,
        }

        if cycle.escalated:
            return {
                **base_update,
                "stage": "failed",
                "error": (
                    f"Sprint '{cycle.sprint_goal}' exhausted its {cycle.max_attempts} remediation attempts "
                    f"with defects still open. A human must intervene.\n\n{build_defect_report(cycle)}"
                ),
            }

        if any(defect.status == "open" for defect in cycle.defects):
            return {**base_update, "stage": "defect_remediation", "defect_cursor": 0}

        # Tests pass and nothing is open. The acceptance gate is still the
        # authority on whether this sprint may be accepted - it also refuses a
        # fix with missing regression coverage or an undocumented accepted risk.
        if not is_sprint_acceptable(cycle):
            return {
                **base_update,
                "stage": "failed",
                "error": (
                    "The sprint cannot be accepted despite passing tests; a defect is missing "
                    f"regression coverage or a documented accepted risk.\n\n{build_defect_report(cycle)}"
                ),
            }

        return {**base_update, "stage": "security_review"}

    def defect_remediation_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        """Route one open defect to the specialist who owns it, then re-test.

        This is steps 4, 5 and 6 of the plan's loop. Defects are handled one at
        a time, `defect_cursor` marking progress, so a pause for approval midway
        resumes on the same defect instead of restarting the whole round.

        A fix is only recorded as fixed when the specialist names a regression
        test (`mark_defect_fixed` enforces this). A fix with no named test
        leaves the defect open, which costs a remediation attempt on the next
        test round rather than silently closing an unverified fix.
        """
        cycle = state["remediation"]
        cursor = state.get("defect_cursor", 0)

        # Scan forward by absolute index rather than indexing into a list of
        # open defects: marking one fixed changes which defects are open, so a
        # position in that list would shift under us and skip a defect.
        defect_index = cursor
        while defect_index < len(cycle.defects) and cycle.defects[defect_index].status != "open":
            defect_index += 1

        if defect_index >= len(cycle.defects):
            # Every defect has been worked this round; go back and re-run tests.
            return {"stage": "test_and_triage", "defect_cursor": 0}

        defect = cycle.defects[defect_index]
        stage_name = f"defect_fix_{state.get('test_round', 0)}_{defect_index}"

        agent = create_specialist_agent(
            defect.owner, model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories
        )
        request = build_defect_fix_request(
            defect.description,
            defect.reproduction_steps,
            defect.expected_behavior,
            defect.actual_behavior,
            defect.affected_files,
            defect.regression_test_required,
            state["repository"].root_path,
        )
        update = _run_gated_agent(
            state,
            config,
            stage_name=stage_name,
            agent=agent,
            initial_request=request,
            output_key="__fix_result__",
            next_stage="defect_remediation",
        )
        if "__fix_result__" not in update:
            return update  # paused waiting for approval on this fix

        fix_result: SpecialistOutput = update.pop("__fix_result__")
        outputs = dict(state.get("specialist_outputs", {}))
        outputs[stage_name] = fix_result

        regression_test = "; ".join(fix_result.tests)
        if defect.regression_test_required and not regression_test:
            # No named regression test: the defect stays open on purpose. The
            # next test round will count this as another failed attempt, so the
            # bounded loop still terminates.
            update["remediation"] = cycle
        else:
            update["remediation"] = mark_defect_fixed(cycle, defect_index, regression_test=regression_test)

        update["specialist_outputs"] = outputs
        # Advance past this defect whether or not it closed. A defect left open
        # (no regression test named) must not be retried inside this round; the
        # next test round counts it as another failed attempt, keeping the loop
        # bounded by MAX_REMEDIATION_ATTEMPTS.
        update["defect_cursor"] = defect_index + 1
        return update

    def security_review_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        outputs = state.get("specialist_outputs", {})
        changed_files = sorted({name for output in outputs.values() for name in output.changed_files})
        agent = create_security_reviewer_agent(model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
        request = build_security_review_request(
            changed_files,
            "Permissions: All tools have read/write access to the repository scope. Validation tools are restricted to a safe list of commands.",
            state["repository"].root_path,
        )
        update = _run_gated_agent(
            state,
            config,
            stage_name="security_review",
            agent=agent,
            initial_request=request,
            output_key="__security_review__",
            next_stage="security_review", # We re-enter to process the output
        )
        if "__security_review__" not in update:
            return update
            
        review: SecurityReviewOutput = update.pop("__security_review__")
        # Record it and move to milestone_review
        return {"stage": "milestone_review", "security_review": review}

    def milestone_review_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        milestone = state["milestone_plan"]
        outputs = state.get("specialist_outputs", {})
        changed_files = sorted({name for output in outputs.values() for name in output.changed_files})
        test_evidence = "\n".join(test for output in outputs.values() for test in output.tests) or "(none recorded)"
        cycle = state.get("remediation")
        defect_report = build_defect_report(cycle) if cycle else "No remediation cycle data."
        
        # Include security findings in the defect report if any exist
        sec_review = state.get("security_review")
        if sec_review and sec_review.status == "findings":
            defect_report += "\n\n--- Security Findings ---\n"
            for f in sec_review.findings:
                defect_report += f"[{f.severity}] {f.category}: {f.description}\nRemediation: {f.remediation}\n\n"
        
        agent = create_milestone_reviewer_agent(model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
        request = build_milestone_review_request(
            milestone.selected_sprint_goal,
            changed_files,
            test_evidence,
            defect_report,
            state["repository"].root_path,
        )
        update = _run_gated_agent(
            state,
            config,
            stage_name="milestone_review",
            agent=agent,
            initial_request=request,
            output_key="__milestone_review__",
            next_stage="milestone_review", # We re-enter to process the output
        )
        if "__milestone_review__" not in update:
            return update
            
        review: MilestoneReviewOutput = update.pop("__milestone_review__")
        
        if review.status == "blocked":
            return {
                "stage": "failed",
                "error": "Milestone review blocked the sprint from continuing. See findings.",
                "milestone_review": review,
            }
        elif review.status == "changes_required":
            findings_text = "\n".join(
                f"[{f.severity}] {f.category}: {f.description} -> {f.required_remediation}" 
                for f in review.findings
            )
            revision_count = state.get("milestone_revision_count", 0) + 1
            if revision_count >= MAX_MILESTONE_REVISIONS:
                return {
                    "stage": "user_review_sprint",
                    "milestone_revision_count": revision_count,
                    "milestone_review": review,
                }
            return {
                "stage": "technical_lead",
                "revision_comments": state.get("revision_comments", []) + [findings_text],
                "milestone_revision_count": revision_count,
                "milestone_review": review,
            }
        
        sprint_index = state.get("current_sprint_index", 0)
        sprints = state.get("sprint_plan").sprints if state.get("sprint_plan") else []
        has_more_sprints = sprint_index < len(sprints) - 1

        if _review_enabled(state, SPRINT_REVIEW):
            next_stage = "user_review_sprint"
        elif has_more_sprints:
            next_stage = "sprint_advance"
        else:
            next_stage = "complete"

        return {"stage": next_stage, "milestone_review": review}

    def user_review_sprint_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        sprint_index = state.get("current_sprint_index", 0)
        sprints = state.get("sprint_plan").sprints if state.get("sprint_plan") else []
        has_more_sprints = sprint_index < len(sprints) - 1
        
        return _run_review_gate(
            state,
            config,
            review_point=SPRINT_REVIEW,
            artifact_id="sprint-milestone",
            approved_next="sprint_advance" if has_more_sprints else "complete",
            changes_next="technical_lead",
        )

    def sprint_advance_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return {
            "stage": "technical_lead",
            "current_sprint_index": state.get("current_sprint_index", 0) + 1,
            # clear previous sprint's milestone state so it doesn't pollute the next sprint
            "milestone_plan": None,
            "specialist_outputs": {},
            "remediation": None,
            "defect_cursor": 0,
            "test_round": 0,
            "revision_comments": [],
            "milestone_revision_count": 0,
        }

    def complete_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:  # noqa: ARG001
        return {"stage": "complete"}

    def failed_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:  # noqa: ARG001
        return {"stage": "failed"}

    graph = StateGraph(WorkflowGraphState)
    from langgraph.types import RetryPolicy
    
    agent_retry_policy = RetryPolicy(
        initial_interval=2.0,
        backoff_factor=2.0,
        max_interval=30.0,
        max_attempts=3,
    )

    graph.add_node("product_manager", product_manager_node, retry_policy=agent_retry_policy)
    graph.add_node("user_review_product_intake", user_review_product_intake_node)
    graph.add_node("tools_models", tools_models_node, retry_policy=agent_retry_policy)
    graph.add_node("stack_selector", stack_selector_node, retry_policy=agent_retry_policy)
    graph.add_node("principal_architect", principal_architect_node, retry_policy=agent_retry_policy)
    graph.add_node("architecture_review", architecture_review_node, retry_policy=agent_retry_policy)
    graph.add_node("user_review_specification", user_review_specification_node)
    graph.add_node("scrum_master", scrum_master_node, retry_policy=agent_retry_policy)
    graph.add_node("technical_lead", technical_lead_node, retry_policy=agent_retry_policy)
    graph.add_node("specialist_dispatch", specialist_dispatch_node, retry_policy=agent_retry_policy)
    graph.add_node("test_and_triage", test_and_triage_node, retry_policy=agent_retry_policy)
    graph.add_node("defect_remediation", defect_remediation_node, retry_policy=agent_retry_policy)
    graph.add_node("security_review", security_review_node, retry_policy=agent_retry_policy)
    graph.add_node("milestone_review", milestone_review_node, retry_policy=agent_retry_policy)
    graph.add_node("user_review_sprint", user_review_sprint_node)
    graph.add_node("sprint_advance", sprint_advance_node)
    graph.add_node("complete", complete_node)
    graph.add_node("failed", failed_node)

    graph.add_conditional_edges(START, _entry_router, {name: name for name in _NODE_NAMES})

    routable_targets = {name: name for name in _NODE_NAMES}
    routable_targets[END] = END
    for node_name in (
        "product_manager",
        "user_review_product_intake",
        "tools_models",
        "stack_selector",
        "principal_architect",
        "architecture_review",
        "user_review_specification",
        "scrum_master",
        "technical_lead",
        "specialist_dispatch",
        "test_and_triage",
        "defect_remediation",
        "security_review",
        "milestone_review",
        "user_review_sprint",
        "sprint_advance",
    ):
        graph.add_conditional_edges(node_name, _route_from_stage, routable_targets)

    graph.add_edge("complete", END)
    graph.add_edge("failed", END)

    return graph.compile(checkpointer=shared_checkpointer)


def load_thread_state(thread_id: str, checkpointer: BaseCheckpointSaver | None = None) -> dict[str, Any]:
    """Return the checkpointed state for one run thread.

    The checkpointer is the single source of truth for graph state. Reading it
    on demand is why the run metadata table no longer carries a second copy: the
    copy was never written, so approval and review payloads always came back
    empty.
    """
    saver = checkpointer or build_checkpointer()
    graph = StateGraph(WorkflowGraphState)
    graph.add_node("noop", lambda state: {})
    graph.add_edge(START, "noop")
    graph.add_edge("noop", END)
    compiled = graph.compile(checkpointer=saver)
    snapshot = compiled.get_state({"configurable": {"thread_id": thread_id}})
    return dict(snapshot.values) if snapshot and snapshot.values else {}


def discard_thread(thread_id: str, checkpointer: BaseCheckpointSaver | None = None) -> None:
    """Delete every checkpoint for one thread, if the backend supports it."""
    saver = checkpointer or build_checkpointer()
    deleter = getattr(saver, "delete_thread", None)
    if deleter is None:
        return
    try:
        deleter(thread_id)
    except Exception:  # noqa: BLE001 - cleanup must never fail a run
        pass


def _run_config(thread_id: str, recursion_limit: int, metadata: dict | None = None) -> RunnableConfig:
    """Build the per-invoke config every entry point below shares."""
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}, "recursion_limit": recursion_limit}
    if metadata:
        config["metadata"] = metadata
    return config


def start_workflow(
    graph: Any,
    document: DocumentContent,
    repository: RepositoryContext,
    thread_id: str,
    *,
    review_policy: dict[str, bool] | None = None,
    reviewer: str = "unassigned",
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
    metadata: dict | None = None,
) -> dict[str, Any]:
    """Start a brand-new workflow run for one product document.

    Args:
        graph: the compiled graph from `build_workflow_graph`.
        document: the product brief, already read by `app.documents`.
        repository: the repository boundary role agents may inspect.
        thread_id: stable id for this run. Reuse it for every resume call, or
            LangGraph will not find the checkpoint and will start over.
        review_policy: which optional human review sessions to enable, keyed by
            `SPECIFICATION_REVIEW` / `SPRINT_REVIEW`. Omitted means neither, so
            only the mandatory approval and architecture gates can pause the run.
        reviewer: identity recorded on any review this run creates, so a review
            decision has an accountable owner.
        recursion_limit: superstep ceiling; see `DEFAULT_RECURSION_LIMIT`.
        metadata: optional tracing metadata for LangSmith.
    """
    return graph.invoke(
        {
            "document": document,
            "repository": repository,
            "stage": "product_manager",
            "review_policy": review_policy or {},
            "reviewer": reviewer,
        },
        config=_run_config(thread_id, recursion_limit, metadata=metadata),
    )


class WorkflowResumeError(RuntimeError):
    """A run could not be resumed from its checkpoint."""


# Bookkeeping checkpoints written by `update_state`/input, never a real stage.
_SYNTHETIC_NODES = frozenset({"__start__", "__input__", "failed"})

_REWIND_TARGETS: dict[str, str] = {
    # A node that failed because it exhausted a bounded budget cannot be
    # retried as itself - it would hit the same limit on the next attempt. It
    # rewinds to whichever node produces the input it was judging, and the
    # counter that stopped it is reset alongside (see _REWIND_COUNTER_RESETS).
    "architecture_review": "principal_architect",
    "milestone_review": "scrum_master",
    "test_and_triage": "technical_lead",
    # In-sprint nodes rewind to the Technical Lead rather than to themselves.
    # A context overflow here means the delegated task was too large to state,
    # and re-entering the same node re-issues the same oversized task; the
    # Lead is the node that can split it. `sprint_advance` was already treated
    # this way before this table existed.
    "sprint_advance": "technical_lead",
    "specialist_dispatch": "technical_lead",
    "defect_remediation": "technical_lead",
}
"""Where a resume sends a run whose failure was attributed to a given node.

Every other node in `_NODE_NAMES` rewinds to *itself*: it failed for a reason
outside its own control - a context overflow, a provider outage, a bad base URL
- and the operator fixes that cause before resuming. Retrying the node itself is
then the only rewind that does not throw away completed work.

This table exists because the previous implementation was an if/elif chain over
an initialiser that defaulted to `{"stage": "product_manager"}`. Any node the
chain did not name silently restarted the run from intake. That was unreachable
until context compaction gave every agent node a path to `stage="failed"`, at
which point seven nodes started restarting runs from the beginning.
"""

_REWIND_COUNTER_RESETS: dict[str, dict[str, int]] = {
    "architecture_review": {
        "architecture_revision_count": 0,
        "specification_repair_count": 0,
    },
    "milestone_review": {"milestone_revision_count": 0},
}
"""Counters to clear when rewinding, so the retry gets a full budget again.

Rewinding an exhausted review gate without clearing its counter re-enters the
gate already at the limit, which fails immediately and looks to the user like
the resume did nothing.
"""

_UNREWINDABLE_NODES = frozenset({"complete"}) | _SYNTHETIC_NODES
"""Nodes a resume must refuse rather than rewind to.

`complete` is terminal and `failed` is where the run already is; the two
`__`-prefixed entries are LangGraph bookkeeping and never name real work.
"""


def _rewind_target(failed_node: str | None) -> str | None:
    """The stage a resume should rewind to, or None to refuse the resume.

    Returning None is a real answer, not an error path: a run whose failure
    cannot be attributed to a node with a safe retry point must be cloned, not
    silently restarted.
    """
    if not failed_node:
        return None
    if failed_node in _UNREWINDABLE_NODES or failed_node not in _NODE_NAMES:
        return None
    return _REWIND_TARGETS.get(failed_node, failed_node)


def _node_that_failed(graph: Any, config: dict[str, Any]) -> str | None:
    """Find the node whose routing decision sent this run to the `failed` node.

    History is most-recent-first. The previous implementation took the entry
    immediately after the transition into `failed` and trusted its `next`. That
    holds only on the first resume: every later resume prepends its own
    `__start__` bookkeeping checkpoints, so the neighbour became `__start__`,
    which matched none of the rewind branches and dropped through to a fallback
    that restarted the whole run. Skip the synthetic entries and take the most
    recent checkpoint that names a real node.
    """
    history = list(graph.get_state_history(config))
    for index, snapshot in enumerate(history):
        if snapshot.next != ("failed",):
            continue
        for earlier in history[index + 1:]:
            node = earlier.next[0] if earlier.next else None
            if node and node not in _SYNTHETIC_NODES:
                return node
        return None
    return None


def resume_failed_run(
    graph: Any,
    thread_id: str,
    *,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
    metadata: dict | None = None,
) -> dict[str, Any]:
    """Resume a failed run from its last checkpoint.
    
    If the run explicitly entered a terminal 'failed' state due to business logic
    (e.g., reaching max revisions), this rewinds the state to act as a retry.
    """
    config = _run_config(thread_id, recursion_limit, metadata=metadata)
    state_snapshot = graph.get_state(config)

    # A run parked on a human gate cannot be resumed, only decided. Re-invoking
    # here re-enters the gate node and returns the same pause, so the caller
    # would see a "successful" resume that changed nothing. Say so instead.
    if state_snapshot and _is_paused(state_snapshot.values.get("stage", "")):
        raise WorkflowResumeError(
            f"This run is paused at '{state_snapshot.values['stage']}' and is waiting for a "
            "decision, not a retry. Answer the open approval or review to continue."
        )

    if state_snapshot and state_snapshot.values.get("stage") == "failed":
        failed_node = _node_that_failed(graph, config)

        target = _rewind_target(failed_node)

        if target:
            rewind_values: dict[str, Any] = {"stage": target, "error": None}
            rewind_values.update(_REWIND_COUNTER_RESETS.get(failed_node, {}))
            # Written as the node that failed, so the entry router reads the new
            # stage on the next invoke instead of re-entering the failed node.
            graph.update_state(config, rewind_values, as_node=failed_node)
        else:
            # Refusing beats guessing. Falling back to stage="product_manager"
            # silently restarts a run from the very beginning - discarding every
            # approved artifact and re-billing the whole pipeline.
            raise WorkflowResumeError(
                f"Could not find a safe point to retry this run from "
                f"(it failed at {failed_node or 'an unrecognised stage'}). "
                "Clone the run to start a fresh attempt."
            )

    # Self-healing: if we are resuming a corrupted run from before the token limit fix
    if state_snapshot and state_snapshot.values.get("stage") == "architecture_review" and state_snapshot.values.get("technical_specification") is None:
        graph.update_state(config, {"stage": "principal_architect"}, as_node="product_manager")

    return graph.invoke(None, config=config)


def resume_pending_approval(
    graph: Any,
    thread_id: str,
    decision: dict[str, Any],
    *,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
    metadata: dict | None = None,
) -> dict[str, Any]:
    """Resume a run paused on a mandatory artifact-write approval.

    Call this (instead of `start_workflow` or a raw `invoke`) whenever
    `state["stage"]` starts with `awaiting_approval:`. Setting `pending_decision`
    is what tells the paused node to resume its inner agent with this decision
    instead of starting a new inner conversation.

    Build `decision` with the helpers in `app.agents.approval`:
    `approve_write_decision()`, `edit_write_decision(...)`, or
    `reject_write_decision(...)`.
    """
    return graph.invoke({"pending_decision": decision}, config=_run_config(thread_id, recursion_limit, metadata=metadata))


def resume_pending_review(
    graph: Any,
    thread_id: str,
    decision: dict[str, Any],
    *,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
    metadata: dict | None = None,
) -> dict[str, Any]:
    """Resume a run paused on an optional human review session.

    Call this (instead of `start_workflow` or a raw `invoke`) whenever
    `state["stage"]` starts with `awaiting_review:`.

    Build `decision` with the helpers in `app.graph.workflow`:
    `approve_decision()`, `request_changes_decision(...)`, or
    `skip_decision()`.
    """
    return graph.invoke({"pending_review_decision": decision}, config=_run_config(thread_id, recursion_limit, metadata=metadata))


def approve_decision(comment: str | None = None, edited_content: str | None = None) -> dict[str, Any]:
    """Build a review decision that accepts the current artifact revision."""
    return {"type": "approve", "comment": comment, "edited_content": edited_content}


def skip_decision() -> dict[str, Any]:
    """Build a review decision that explicitly skips this optional review.

    Recorded as `SKIPPED`, never as `APPROVED`: an auditor must be able to tell
    "a human looked at this and accepted it" apart from "nobody reviewed it".
    """
    return {"type": "skip"}


def request_changes_decision(comment: str, edited_content: str | None = None) -> dict[str, Any]:
    """Build a review decision that sends the artifact back for a new revision.

    `comment` is required and is handed to the role agent verbatim; a change
    request with no stated change would give the agent nothing to act on, so
    the gate rejects it rather than looping.
    """
    return {"type": "request_changes", "comment": comment, "edited_content": edited_content}


__all__ = [
    "APPROVAL_PAUSE_PREFIX",
    "discard_thread",
    "load_thread_state",
    "DEFAULT_RECURSION_LIMIT",
    "MAX_ARCHITECTURE_REVISIONS",
    "MAX_MILESTONE_REVISIONS",
    "MAX_REMEDIATION_ATTEMPTS",
    "REVIEW_PAUSE_PREFIX",
    "SPECIFICATION_REVIEW",
    "SPRINT_REVIEW",
    "WorkflowGraphState",
    "approve_decision",
    "build_workflow_graph",
    "request_changes_decision",
    "resume_failed_run",
    "resume_pending_approval",
    "resume_pending_review",
    "skip_decision",
    "start_workflow",
]
