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

import json
import re
import os
import logging
import uuid
import operator
import time
from datetime import datetime, timezone
from typing import Any, Mapping, TypedDict, Annotated

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
# `langgraph.constants` is where this lived and still re-exports it, with a
# `LangGraphDeprecatedSinceV10` warning and a stated removal in V2. The
# supported path is `langgraph.types`, confirmed against the API reference for
# `langgraph.types.Send`.
from langgraph.types import Send

from app.agents.approval import extract_pending_approval, resume_with_decision
from app.agents.stage_memory import remembering
from app.agents.stack_selector import the_browser_runner_this_stack_forgot
from app.agents.architecture_reviewer import (
    ArchitectureReviewOutput,
    build_architecture_review_request,
    create_architecture_reviewer_agent,
)
from app.agents.review_document import render_architecture_review, render_security_review
from app.doc_templates import render_document
from app.agents.artifact_document import render_artifact
from app.agents.specification_document import render_specification
from app.agents.milestone_reviewer import (
    MilestoneReviewOutput,
    build_milestone_review_request,
    create_milestone_reviewer_agent,
    findings_for_what_the_checks_proved,
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
from app.agents.product_manager import (
    ProductManagerOutput,
    build_intake_request,
    create_product_manager_agent,
    with_the_constraints_the_brief_states,
    with_the_measures_the_brief_states,
    with_the_workflows_its_measures_require,
    with_what_the_brief_requires_marked_in_deferred_scope,
)
from app.agents.role_agent import create_role_agent
from app.agents.scrum_master import (
    SprintPlanOutput,
    build_sprint_planning_request,
    capabilities_the_plan_never_names,
    create_scrum_master_agent,
    unaccounted_success_measures,
)
from app.agents.sprint_summary import (
    a_suite_that_did_not_pass,
    count_test_cases,
    last_test_run,
    render_sprint_summary,
)
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
    build_milestone_revision_request,
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
from app.tracing import APP_RUN_ID_KEY, trace_metadata

logger = logging.getLogger(__name__)

def _max_architecture_revisions() -> int:
    """How many times review may send the specification back before failing.

    Raised from 3 and made configurable on evidence: across observed runs on a
    small local model, the reviewer kept surfacing one more major finding each
    round, and the run died at the cap with a single finding outstanding after
    having produced a perfectly usable specification. The reviewer converging
    slowly is not the same failure as the architect looping, and three rounds is
    a tight budget for a model that reviews thoroughly.

    It stays bounded, because a reviewer and an architect that simply disagree
    will never converge and each round costs two model calls.

    That reasoning was incomplete, and one run showed why. The reviewer was
    not converging slowly on a fixed specification - the specification was
    growing under it. Each round the architect answered a finding by adding
    ADRs, and each new ADR gave the reviewer more artefacts to find missing:
    four blocking findings became five, citing ADR-12 and ADR-17 that did not
    exist a round earlier. None of it was in the brief. Raising this number
    buys more rounds of that; `app.agents.scope_discipline` is what stops the
    specification growing, and is the actual fix. The cap remains as a bound on
    the case it was written for.
    """
    default = 6
    try:
        return int(os.environ.get("WORKFLOW_MAX_ARCHITECTURE_REVISIONS", str(default)))
    except ValueError:
        logger.warning("Malformed WORKFLOW_MAX_ARCHITECTURE_REVISIONS; using %d", default)
        return default


MAX_ARCHITECTURE_REVISIONS = _max_architecture_revisions()

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

# Imported rather than restated: this ceiling is derived from the call budget
# below, and a second copy of the number is how the two drifted apart before.
from app.agents.settled_answer import MODEL_CALLS_PER_STAGE

#: Supersteps one model call costs, measured. A react agent spends one node on
#: the call and one on each tool it invokes, so this is above 1 by however much
#: the stage uses its tools.
#:
#: Measured across 203 stage executions in the stored runs: median 2.29, 90th
#: percentile 3.14, 95th 3.30, maximum 3.87.
#:
#: The **maximum** is what this has to cover, and the reason changed underneath
#: the first version of this constant. That one took the 90th percentile
#: deliberately - "so nine stages in ten reach their full model-call budget and
#: the tenth is bounded by the budget rather than by this" - on the reasoning
#: that a higher ceiling lets a runaway burn more supersteps. It was written
#: when the model-call budget only nagged. The budget now *ends* a stage, and
#: withholds every tool two calls before it does, so the budget is what bounds
#: a runaway and this ceiling only decides which of the two stops a stage
#: first.
#:
#: That decision matters because the two degrade differently. The budget guard
#: forces an answer and can salvage one. The superstep ceiling raises
#: `GraphRecursionError`, and the stage restarts from an empty conversation
#: with everything it learned discarded.
#:
#: At 3.2 the ceiling is 128, which the worst-ratio stage reaches at 33 model
#: calls - five before the guard withholds tools at 38 - so on those stages the
#: guard never acts at all. Measured live on one run, where
#: `defect_fix_1_1` hit the ceiling and restarted while the guard sat
#: unreached. At 4.0 the ceiling is 160, which the worst ratio on record
#: reaches at 41 calls, one past the budget: the budget now stops every stage
#: measured, and a stage with a ratio worse than any yet seen falls back to the
#: behaviour this replaces rather than to something worse.
SUPERSTEPS_PER_MODEL_CALL = 4.0

#: The worst ratio any stored stage execution has shown, kept beside the
#: constant above so the relationship between the two ceilings can be asserted
#: rather than described. See
#: `test_the_budget_guard_reaches_a_stage_before_the_ceiling_does`.
WORST_MEASURED_SUPERSTEP_RATIO = 3.87

INNER_AGENT_RECURSION_LIMIT = int(MODEL_CALLS_PER_STAGE * SUPERSTEPS_PER_MODEL_CALL)
"""Superstep ceiling for one role agent's own graph.

The outer workflow has had a ceiling since it was written; the agent invoked
inside a stage had none, so it ran on LangGraph's default. A stage that loops
internally - model emits text, tools run, model emits the same text - never
returns, so no workflow guard applies to it: not the structured-response retry,
not the repeat guard, not the approval ceiling. All of those are checked when a
stage *ends*.

Measured on one run, whose principal architect spent twenty-two minutes
and 184 events printing the same specification into the conversation and
re-reading the same three documents, with zero restarts recorded because the
stage never finished one.

**Derived rather than chosen, since 2026-09-22.** It was 60, described as
"roughly twice the longest healthy stage observed across fourteen runs" - but
that was counted in stages, not in supersteps, and a superstep is not a model
call. At the measured 2.41 supersteps per call, 60 supersteps is about 25 model
calls, while `MODEL_CALLS_PER_STAGE` is 40 and the largest stage that has ever
finished used 36. So this ceiling could kill a stage the call budget says is
healthy, and did: one run's `specialist_ui_ux_0` spun out three times at
roughly 32 calls an attempt, never reached its call budget, and failed the run.

Worse than stopping a healthy stage, it stopped the *better* guard from acting.
`MODEL_CALLS_PER_STAGE` ends a stage by looking for an answer already written
and returning it (`_decide`); this ends it with a `GraphRecursionError` and a
restart. Letting the call budget bind first means a spin is caught by the guard
that can salvage something.

Deriving one from the other is what `_request_timeout` does with
`_time_to_generate_a_full_answer`, and for the same reason: the two numbers
were chosen independently, drifted, and the drift was invisible until a run
died of it.
"""
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
        # Parallel mode's fan-out target. `graph.add_node` registers it and
        # routers reference it, but it was absent here - and every conditional
        # edge map, including the entry router's, is built from this set. So no
        # edge map contained it and a resume parked on it had no target.
        "specialist_worker",
        "specialist_gather",
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


def _merge_or_reset(
    current: dict[str, Any] | None, update: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge per-task entries, treating an empty update as "start again".

    `operator.ior` cannot express a reset. `current |= {}` leaves the dictionary
    exactly as it was, so the four places that hand on `specialist_outputs={}`
    to begin a sprint, a re-plan, a fresh milestone or a blocked review with a
    clean slate were keeping every earlier milestone's output instead of
    dropping it. `test_and_triage` builds `changed_files` from those outputs and
    hands them to the Test Engineer as the work to verify, so a later sprint was
    asked to test files an earlier sprint had changed and this one had not
    touched - and `milestone_review` read the same set as the milestone's work.

    Merging is still the behaviour that matters: the parallel fan-out has every
    worker writing one key of this dictionary in the same superstep, and a
    last-write-wins channel would keep one specialist's output and discard the
    rest.
    """
    if not update:
        return {}
    return {**(current or {}), **update}


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
    # Set once the workflow has raised its one success-measure coverage finding
    # against a specification. See `_a_success_measure_the_specification_drops`.
    specification_coverage_checked: bool
    specification_repair_count: int
    # Per-stage count of attempts that ended without a structured response.
    structured_retries: dict[str, int]
    # Per-stage note from the attempt that just died, read once by the
    # fresh one and then cleared. See `app.agents.carry_over`.
    stage_carry_over: dict[str, str]
    milestone_revision_count: int
    sprint_plan: SprintPlanOutput
    # Success measures a sprint plan left unassigned or only partly delivered,
    # as {"measure": n, "missing": [items]}, carried into the one re-plan that
    # asks for them. See `unaccounted_success_measures` and
    # `capabilities_the_plan_never_names`.
    sprint_plan_gaps: list[dict[str, Any]]
    current_sprint_index: int
    # Every attempt at every sprint, oldest first, each one a mapping of the
    # shape `sprint_summary.render_sprint_summary` documents. A sprint that
    # fails is re-planned and attempted again, and without this the second
    # attempt's summary overwrote the first - so the failure that caused the
    # re-run left no record, and the extra milestone it cost looked like an
    # extra sprint. Appended to, never rewritten.
    sprint_attempts: list[dict[str, Any]]
    # A milestone plan that failed the definition of ready, and why - sent back
    # to the lead once. See `app.analysis.work_orders`.
    work_order_problems: list[str]
    unready_plan: str
    # The best plan of this planning cycle's unready attempts, and its
    # problems - dispatched instead of the last one when the attempts run out.
    # See `_the_better_plan`.
    best_unready_plan: str
    best_unready_problems: list[str]
    # The Sprint Record. Every review finding of this sprint, round by round;
    # what the last sprint left for this one's lead to take or decline; and what
    # the harness saw fail repeatedly. See `app.sprint.record`.
    sprint_findings: list[dict[str, Any]]
    carried_forward: list[str]
    lessons: list[str]
    milestone_plan: MilestonePlanOutput
    specialist_task_index: int
    specialist_outputs: Annotated[dict[str, SpecialistOutput], _merge_or_reset]
    # A parallel worker that paused, keyed by its stage name. Written by the
    # workers, drained by `specialist_gather`. It exists because `stage` cannot
    # be written from a fan-out: every worker writes the same superstep and
    # `stage` has no reducer, so two workers pausing is an `InvalidUpdateError`
    # rather than a pause.
    specialist_pauses: Annotated[dict[str, dict[str, Any]], _merge_or_reset]
    # Decisions for queued parallel pauses, answered in the same resume as the
    # surfaced one - see `_only_this_worker_s_pause`. Written only by the
    # runner under auto-approve, cleared by `specialist_gather` after every
    # fan-out superstep, so a decision is never carried to a worker's next gate.
    queued_decisions: Annotated[dict[str, dict[str, Any]], _merge_or_reset]
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
    "max context length",
    "context window",
    "input is too long",
    "exceeds the maximum",
)


def _is_context_overflow(error: BaseException) -> bool:
    """Whether this exception is the model refusing an oversized prompt.

    Checked by type first. `langchain_core` raises `ContextOverflowError` for
    exactly this condition, and a type is not a guess: substring matching has to
    be kept in step with every provider's wording, and a provider that rephrases
    its message silently turns a handled overflow into an unhandled crash.

    The substring list stays as a fallback, because providers still disagree on
    the type - the same condition arrives as `BadRequestError`,
    `OpenAIInvalidRequestError` or a plain `ValueError` depending on which
    client is in front of it, and the OpenAI-compatible servers this runs
    against are the ones least likely to raise the typed error.
    """
    try:
        from langchain_core.exceptions import ContextOverflowError

        if isinstance(error, ContextOverflowError):
            return True
    except ImportError:  # older langchain-core; the markers below still apply
        pass

    return any(marker in str(error).lower() for marker in _CONTEXT_OVERFLOW_MARKERS)


#: Model-side failures worth another attempt on a fresh conversation. These are
#: generation faults, not requests the model refused: the same input usually
#: succeeds next time, and the run has nothing to gain from stopping.
_TRANSIENT_MODEL_MARKERS = (
    # A local model truncated a tool call mid-string and the server rejected it.
    # Measured on one run: "Failed to parse tool call arguments as JSON:
    # parse error at line 1, column 26: invalid string: missing closing quote".
    # The run ended at 2,333 events over one malformed message.
    "failed to parse tool call",
    "invalid tool call",
    "tool call arguments",
    # The server stumbled rather than refusing the request.
    "internal server error",
    "server_error",
    "service unavailable",
    "connection reset",
    "connection aborted",
    "read timed out",
    "timeout",
)


def _is_transient_model_error(error: BaseException) -> bool:
    """Whether this is a generation fault worth retrying, not a refusal.

    A context overflow is a statement about the request, and re-sending it
    unchanged achieves nothing; these are statements about one attempt. The
    responses differ - overflow compacts and retries with less, this simply
    tries again - so they are classified apart.
    """
    if _is_context_overflow(error):
        return False
    text = str(error).lower()
    return any(m in text for m in _TRANSIENT_MODEL_MARKERS)



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


def _queued_pauses(state: Any) -> dict[str, dict[str, Any]]:
    """The parallel pauses still waiting to be surfaced.

    `specialist_gather` marks a pause it has surfaced by setting its entry to
    `None` rather than removing it, because `_merge_or_reset` merges and an empty
    update resets the whole channel. So `None` means answered, not paused.
    """
    return {
        stage: pause
        for stage, pause in (state.get("specialist_pauses") or {}).items()
        if pause
    }


#: When a parallel pause joined the queue, kept on its entry so the queue can be
#: drained oldest first. Stripped before a pause is surfaced into state.
_QUEUED_AT = "__queued_at"


def _as_a_queued_pause(
    state: Any, stage_name: str, update: dict[str, Any], *, answered: bool = False
) -> dict[str, Any]:
    """`update`, the pause a worker returns, stamped with when it joined the queue.

    A pause still queued from an earlier superstep keeps its original time: the
    dispatcher re-sends every paused worker, each hands the same pause straight
    back, and a fresh stamp on every pass would send it to the back each time.
    A pause for a new gate - the entry was surfaced and cleared - joins the back.
    """
    # `answered`: this worker's last pause was decided in a batch and it has
    # reached a new gate, so it joins the back like any other new gate.
    earlier = {} if answered else (state.get("specialist_pauses") or {}).get(stage_name) or {}
    queued_at = earlier.get(_QUEUED_AT) if isinstance(earlier, dict) else None
    return {**dict(update), _QUEUED_AT: queued_at or time.time()}


def _the_pause_to_surface(pauses: dict[str, dict[str, Any]]) -> str:
    """The queued pause that has waited longest; stage name breaks a tie.

    It was `sorted(pauses)[0]` - the stage name - under a docstring that said
    "oldest task first". On one run a testing task and three interface tasks
    paused in the same superstep. `specialist_testing_4` sorts before every
    `specialist_ui_ux_*`, so it was surfaced, approved, ran one gated call,
    paused again and was surfaced again - at least eleven times - while the
    three interface tasks, queued since the first minute of the fan-out, never
    got their turn. The testing task, finding no page to test, wrote the page,
    the script and a server itself.
    """
    return min(
        pauses,
        key=lambda stage: ((pauses[stage] or {}).get(_QUEUED_AT) or float("inf"), stage),
    )


def _the_stage_that_paused(state: Any) -> str | None:
    """The stage whose approval gate the pending decision answers, or None.

    Read from `pending_inner_thread_id` first, not from `stage`. In parallel mode
    a resume enters `specialist_dispatch`, which returns
    `stage: specialist_dispatch_parallel` before the router fans out - so by the
    time any worker runs, the `awaiting_approval:<name>` marker is gone and
    `stage` names nobody.

    That cost one run. The first version of the ownership check read
    `stage`, found no worker it named, and so took the decision away from every
    worker including the one it was for. `specialist_backend_1` restarted from
    scratch at least six times - the same `ls`, the same three document reads,
    "I'll create app.js", the gated write, the pause - and never wrote a byte,
    while the tests passed on a fixture holding the marker the worker never
    sees.

    The inner thread id is minted as `{outer}:{stage}:{8 hex}` by
    `_run_gated_agent`, is carried unchanged through the pause, the surfacing
    and the dispatcher, and names the stage it belongs to. `stage` is kept as a
    fallback for a state that has the marker and no thread.
    """
    thread = str(state.get("pending_inner_thread_id") or "")
    parts = thread.rsplit(":", 2)
    if len(parts) == 3 and parts[1]:
        return parts[1]
    stage = str(state.get("stage") or "")
    if stage.startswith(APPROVAL_PAUSE_PREFIX):
        return stage[len(APPROVAL_PAUSE_PREFIX):] or None
    return None


def _only_this_worker_s_pause(state: Any, stage_name: str) -> dict[str, Any]:
    """The pause fields a parallel worker may act on, as an override for its state.

    A worker may only answer its *own* approval gate.

    `pending_decision` and `pending_inner_thread_id` are single fields, and every
    worker in a superstep is handed a copy of the one state that holds them. On a
    resume the dispatcher re-sends every task that has no output yet, so without
    this each of those workers resumed whichever inner thread happened to be
    stored there - a sibling's - and executed the gated call waiting on it.

    Measured on one run: one `call_id` recorded three times under three
    stage names, with three `tool_result` records microseconds apart, one
    reporting `"status": "edited"` and the other two "already contains the text
    you asked to put there". Every call that was multiplied was a gated one -
    write_artifact 4, replace_lines 5, edit_artifact 3, run_terminal_command 2 -
    and every ungated one ran exactly once, which is the signature of the shared
    field and not of three models choosing the same call in the same second.
    `run_terminal_command` in that list means the shell commands ran three times
    as well.

    The cost was not only the duplicated work. Every repeat counter in the
    harness is per stage, and three executions raised each of them three times,
    so the read refusals and the withholding rungs fired at a third of the
    repetition they describe - which is what made the counts in an audit of a
    parallel run untrustworthy.

    Returns `{}` for the worker whose gate is the one being answered, so it
    resumes exactly as it did before.
    """
    if _the_stage_that_paused(state) == stage_name:
        return {}
    queued = _queued_pauses(state).get(stage_name) or {}
    decided = (state.get("queued_decisions") or {}).get(stage_name)
    if queued and decided:
        # Answered in the same resume as the surfaced pause. Under auto-approve
        # the runner decides every queued pause at once, each through the same
        # gate budget and loop checks, so the fan-out's workers go on together
        # instead of one per superstep. Measured on one run: more than one
        # model call was in flight for 13-28% of the specialists' time, and
        # LM Studio's other parallel slots sat idle.
        return {
            "pending_decision": decided,
            "pending_inner_thread_id": queued.get("pending_inner_thread_id"),
            "pending_approval": queued.get("pending_approval"),
            "stage": f"{APPROVAL_PAUSE_PREFIX}{stage_name}",
        }
    override: dict[str, Any] = {
        "pending_decision": None,
        # Our own paused thread if we have one, and otherwise none at all. Never
        # the value a sibling left behind.
        "pending_inner_thread_id": queued.get("pending_inner_thread_id"),
        "pending_approval": queued.get("pending_approval"),
    }
    if queued:
        # Our pause is still queued behind another stage's. Declaring it here
        # lets `_run_gated_agent` recognise its own gate and hand the pause
        # straight back, which costs no model call and keeps the paused inner
        # thread alive until its turn comes.
        override["stage"] = f"{APPROVAL_PAUSE_PREFIX}{stage_name}"
    return override


def _that_do_not_share_a_file(
    pending: list[tuple[int, Any]],
    already_going: list[tuple[int, Any]] | tuple = (),
) -> list[tuple[int, Any]]:
    """As many pending tasks as can run at once without editing one file.

    `already_going` are tasks that must be dispatched whatever they share - a
    worker holding an approval pause, which is only answered by re-dispatching
    it. They go first and claim their files, and the rest are staggered against
    them exactly as against each other.

    Two tasks naming the same file are the most expensive thing the parallel
    fan-out does. They run in the same superstep, so each reads the file, plans
    an edit against the line numbers it saw, and the second one's numbers have
    moved by the time it writes. The guards catch it - a `replace_lines` whose
    anchor shifted is refused, and so is an edit that would leave the file
    unparseable - which is why nothing corrupt ships, but every one of those
    refusals cost a model call.

    Measured on one run, a seven-task milestone in which four tasks named
    `app.js`: of 400 calls, 64 failed, and 45 of those were this - 28 redundant
    reads of `app.js`, 13 identical `replace_lines` and 7 identical
    `edit_artifact`, each stage re-reading and retrying against a file another
    stage was moving underneath it.

    `_a_file_another_specialist_is_also_given` already detects this exactly, and
    its note has fired correctly in production; a note is all it can be, because
    by then the tasks are already running. Deferring the task instead costs one
    superstep and removes the contention, and the deferred task is dispatched on
    the next pass, against a file that has stopped moving.

    Parallelism is kept where it is real: tasks naming different files all go
    at once, and so do tasks naming no file at all - but not with each other,
    because a task with no named file may change any of them. The first
    pending task always goes, so a
    milestone whose every task names one file still makes progress - one at a
    time, which is what it asked for.

    The docstring on `_a_file_another_specialist_is_also_given` records the
    upstream cause: of 25 stored sprint plans, 17 assign one file to more than
    one specialist. This makes such a plan slow instead of wasteful.
    """
    try:
        from app.analysis.planned_files import paths_a_plan_named
    except Exception:  # noqa: BLE001 - never hold up a dispatch over a hint
        return pending

    def named_by(task: Any) -> set[str] | None:
        """The files a task names, by basename; None when it could not be read.

        None is not "no files": a task that could not be read is a broken hint,
        and a hint must never hold a dispatch up, so it neither waits nor makes
        anything wait.
        """
        # The work order's own `files` first - the structured list the lead is
        # asked for - and whatever its prose names besides.
        declared = {
            str(path).strip().rstrip("/").rsplit("/", 1)[-1].lower()
            for path in (getattr(task, "files", None) or ())
            if str(path).strip()
        }
        try:
            return declared | {
                path.rsplit("/", 1)[-1].lower()
                for path in paths_a_plan_named(
                    [
                        str(getattr(task, "task_description", "") or ""),
                        *[str(item) for item in (getattr(task, "acceptance_criteria", None) or ())],
                    ]
                )
            }
        except Exception:  # noqa: BLE001 - a task whose files cannot be read runs
            return declared or None

    # A task that declares the package manifest goes before the tasks that do
    # not. Everything else builds and tests on top of the manifest - its
    # dependencies, its test script - and without it each of them makes its
    # own: on one run a plan gave `package.json` to one backend task, and
    # both testing tasks and the other backend task wrote it too, in the same
    # superstep, three of them refused as blind overwrites of the first.
    try:
        from app.tools.repository import PACKAGE_MANIFESTS

        manifests = {name.lower() for name in PACKAGE_MANIFESTS}
    except Exception:  # noqa: BLE001 - never hold up a dispatch over a hint
        manifests = set()
    first_the_manifest = {
        index for index, task in pending if (named_by(task) or set()) & manifests
    }
    if first_the_manifest:
        committed_first = {index for index, _ in already_going}
        pending = [
            (index, task) for index, task in pending
            if index in first_the_manifest or index in committed_first
        ]

    going: list[tuple[int, Any]] = list(already_going)
    claimed: set[str] = set()
    # Whether a task that names no file is going. Such a task may change any
    # file - one run's security task, with no `files` in its work order, wrote
    # `index.html` three times over the interface task that owned it, in the
    # same superstep - so it does not share a superstep with a task that has
    # claimed files, in either order. Tasks that name no file still go
    # together: nothing is known to collide, and a review that writes nothing
    # is the usual one.
    unknown_going = False
    for _, task in going:
        named = named_by(task)
        if named is None:
            continue
        claimed |= named
        unknown_going = unknown_going or not named
    committed = {index for index, _ in going}
    for index, task in pending:
        if index in committed:
            continue
        named = named_by(task)
        if named is None:
            going.append((index, task))
            continue
        if going:
            if not named and claimed:
                continue
            if named and unknown_going:
                continue
            # Compared by basename: one task writes `app/app.js` and another
            # `app.js`, and the plan's prose spells the same file both ways.
            if named & claimed:
                continue
        going.append((index, task))
        claimed |= named
        unknown_going = unknown_going or not named
    return going or pending


def _tasks_without_an_output(state: Any) -> list[tuple[int, Any]]:
    """The milestone's delegated tasks that have not produced an output yet.

    The router's resume guard and the gather node's "is anything left" question
    are the same question, and two copies of it is how one of them comes to
    disagree about what "done" means.

    `getattr` with a default, like every other reader of this field:
    `state.get(...)` is None when no plan has been stored, and
    `None.delegated_tasks` is an AttributeError inside a router - which takes
    the run down rather than routing it anywhere.
    """
    tasks = getattr(state.get("milestone_plan"), "delegated_tasks", None) or []
    done = set(state.get("specialist_outputs") or {})
    return [
        (index, task)
        for index, task in enumerate(tasks)
        if _specialist_stage_name(task, index) not in done
    ]


def _stages_holding_a_pause(state: Any) -> set[str]:
    """The specialist stages that paused inside the fan-out and are still paused.

    The one whose gate is being answered - see `_the_stage_that_paused` - and every one whose
    pause is still queued behind it. These are the tasks a resume has to
    re-dispatch; any other pending task is free to wait its turn.
    """
    holding = set(_queued_pauses(state))
    paused = _the_stage_that_paused(state)
    if paused:
        holding.add(paused)
    return holding


def _specialist_stage_name(task: Any, index: int) -> str:
    """The stage name one delegated task runs under.

    Shared by linear dispatch, the parallel router and the parallel worker.
    Three copies of one f-string is how a fan-out comes to record its results
    under names the dispatcher does not recognise, which would make every task
    look unfinished forever.
    """
    return f"specialist_{getattr(task, 'specialist_role', 'unknown')}_{index}"


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
        
    if stage == "specialist_dispatch_parallel":
        # Only the tasks that have not already produced an output. A run that
        # paused inside the fan-out resumes at the dispatcher - the paused stage
        # name maps there, exactly as it does in linear mode - and re-deriving
        # the whole fan-out would run every task that had already finished a
        # second time, re-applying its edits. Linear mode is kept honest by
        # `specialist_task_index`; this is the parallel equivalent, and it reads
        # the outputs themselves rather than a counter because a fan-out has no
        # order to count through.
        pending = _tasks_without_an_output(state)
        if not pending:
            # Not straight to the tests: `specialist_gather` is the one writer
            # that may set `stage` after a fan-out, and it is also what surfaces
            # a worker that paused. An empty milestone reaches it with nothing
            # recorded and moves on, which is what an empty fan-out needs.
            return "specialist_gather"
        # A worker holding a pause must be re-dispatched: that is how its
        # decision is delivered, and deferring it leaves the decision with no
        # hanging call to answer - `ValueError: Number of human decisions (2)
        # does not match number of hanging tool calls (1)`, which ended
        # one run on 2026-09-11.
        #
        # That used to be met by sending the whole pending set whenever a
        # decision was in state, which switched the staggering off for the rest
        # of the milestone after its first approval: with `auto_approve` every
        # fan-out pauses on its first gated call, and nothing clears the
        # decision until the fan-out ends. Measured on one run:
        # `specialist_testing_2`, which imports `app.js`, was rightly held back
        # while `specialist_backend_1` wrote `app.js` - and was dispatched at
        # 05:57:06 by the first resume, with `backend_1` still writing until
        # 05:58:51. Now only the paused workers are forced through, and every
        # other task is staggered against the files they hold.
        must_go = [
            (index, task)
            for index, task in pending
            if _specialist_stage_name(task, index) in _stages_holding_a_pause(state)
        ]
        going = _that_do_not_share_a_file(pending, already_going=must_go)
        return [
            Send("specialist_worker", {**state, "__worker_task": task, "__worker_index": index})
            for index, task in going
        ]

    return stage


#: Stages that exist only inside one invoke of the parallel fan-out, and so
#: must re-enter the dispatcher rather than themselves when a run resumes.
#:
#: `specialist_dispatch_node` returns `{"stage": "specialist_dispatch_parallel"}`
#: in parallel mode, and `_route_from_stage` turns that into a `Send` to each
#: worker. Both names are then on the checkpoint. Re-entering `specialist_worker`
#: directly cannot work: its task arrives in the `Send` payload as
#: `__worker_task`, which a resumed state does not carry, so it would fail on a
#: missing key. Re-entering the dispatcher re-derives the fan-out from the plan,
#: which is exactly what the linear path already does - `specialist_ui_ux_0`
#: resumes at `specialist_dispatch` too.
_RESUME_AT_THE_DISPATCHER = frozenset({
    "specialist_dispatch_parallel",
    "specialist_worker",
    "specialist_gather",
})


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
        return _owning_node(inner_stage_name)
    if stage in _RESUME_AT_THE_DISPATCHER:
        return "specialist_dispatch"
    # Through `_owning_node`, not verbatim. The conditional-edge map here is
    # built from `_NODE_NAMES`, so returning a stage that is not a node hands
    # LangGraph a target it has no edge for - which is how a parallel-mode
    # resume died. `_owning_node` passes a node through unchanged, maps an
    # iterated stage to the node that runs it, and answers `failed` for
    # anything it does not know, which is a stop rather than a crash.
    return _owning_node(stage)


#: State belonging to a stage's pause, which must not outlive that stage.
#:
#: `_run_gated_agent` clears these on success, but a node that pops its private
#: result key and then returns a *fresh* dict silently drops that reset. The
#: next stage inherits `pending_decision` and `pending_inner_thread_id` from the
#: stage before it - and `_run_gated_agent`, seeing a pending decision, resumes
#: that inherited thread instead of starting its own.
#:
#: Observed on one run: `milestone_review` finished with `changes_required`
#: and handed back to `technical_lead`, which resumed the *reviewer's*
#: conversation and was handed a `MilestoneReviewOutput`. It stored that under
#: `milestone_plan` and died on `'MilestoneReviewOutput' object has no attribute
#: 'selected_sprint_goal'` - an error naming neither the stage that leaked nor
#: the field that carried it.
_PAUSE_CLEARED: dict[str, Any] = {
    "pending_approval": None,
    "pending_inner_thread_id": None,
    "pending_decision": None,
}


def _task_fingerprint(milestone: Any) -> tuple[tuple[str, str], ...]:
    """What a plan actually delegates, ignoring prose that does not assign work."""
    return tuple(
        (str(getattr(task, "specialist_role", "")), str(getattr(task, "task_description", "")))
        for task in getattr(milestone, "delegated_tasks", []) or []
    )


def unassigned_review_changes(
    milestone: Any, *, revising: bool, previous: Any = None
) -> str | None:
    """Why this revised milestone plan cannot proceed, or None if it can.

    A plan is a list of assignments. Asked to "address every requested change",
    an agent can satisfy that for a *plan* by writing the change down, which
    changes nothing: on one run a review named the exact file, line and fix
    for a test-suite failure, the lead reproduced it verbatim under
    `## Integration Notes`, no delegated task mentioned it, and eighty minutes
    later the file was byte-for-byte unchanged.

    `review_task_assignments` is the forcing function: naming the task that took
    each change is something you cannot do without having created one.
    """
    if not revising:
        return None
    # Saying which task took each change is the clearest signal, and when a
    # model gives it there is nothing to check.
    if getattr(milestone, "review_task_assignments", None):
        return None

    # Not every model fills a bespoke field. Measured on one run, this one
    # left it empty on three fresh conversations while producing a plan that was
    # otherwise complete - so an empty field alone cannot mean the work was not
    # assigned. What *does* prove it is a revision whose delegated tasks are
    # identical to the ones it was asked to change: the same seven tasks came
    # back all three times.
    if previous is not None and _task_fingerprint(milestone) != _task_fingerprint(previous):
        return None

    return (
        "The revised milestone plan delegates exactly the same tasks as the plan the "
        "review sent back, so nothing was assigned to the requested changes. A change "
        "recorded in `integration_notes`, or left out entirely, belongs to nobody and "
        "will not be made. Resume to re-plan this milestone."
    )


def _handing_on(**fields: Any) -> dict[str, Any]:
    """A state update that leaves none of the finished stage's pause behind.

    Use this for every return that follows a completed `_run_gated_agent` call.
    Spelling the fields out at each site was the arrangement that failed: five
    nodes have between two and seven such returns, and one of them forgetting is
    invisible until two stages later.
    """
    return {**_PAUSE_CLEARED, **fields}


def _owning_node(stage_name: str) -> str:
    """The graph node that runs a given stage, or `"failed"` if none does.

    Most stages are named after their node. The three looping nodes are not:
    they name each iteration's stage after the iteration - `specialist_ui_ux_0`,
    `test_round_2`, `defect_fix_1_0` - and those names are not nodes.

    Anything that sets `stage` must route through here. `_route_from_stage`
    returns the value verbatim and the conditional-edge map is keyed by
    `_NODE_NAMES`, so a stage that is not a node raises `KeyError` and kills the
    run outright - a worse outcome than whatever was being handled. That is not
    hypothetical: the structured-response retry below set `stage` to the stage's
    own name and took down the run it was written to rescue.
    """
    if stage_name in _NODE_NAMES:
        return stage_name
    for prefix, owning_node in _ITERATED_STAGE_OWNERS.items():
        if stage_name.startswith(prefix):
            return owning_node
    return "failed"


def _the_better_plan(
    current: tuple[Any, list[str]], earlier: tuple[str, list[str]]
) -> tuple[Any, list[str]]:
    """Of this attempt and the best earlier one, the plan to keep, with its problems.

    Fewer readiness problems wins, then more work orders. When the attempts ran
    out, the last plan was dispatched whatever it was. Measured on one run:
    the second attempt was a six-work-order plan covering the page, the five
    modules of the sprint's scope, the manifest, the tests and the README, with
    three small problems; the lead then reasoned to its ceiling, the recovery
    call answered with two work orders - the page skeleton and the manifest -
    and that was the plan the sprint built. `earlier` is the stored JSON of the
    best unready plan so far, "" when there is none or it cannot be read.
    """
    plan, problems = current
    stored, stored_problems = earlier
    if not stored:
        return plan, problems
    try:
        previous = type(plan).model_validate_json(stored)
    except Exception:  # noqa: BLE001 - an unreadable record is no better plan
        return plan, problems

    def rank(candidate: Any, found: list[str]) -> tuple[int, int]:
        return (len(found), -len(getattr(candidate, "delegated_tasks", None) or []))

    if rank(previous, stored_problems) < rank(plan, problems):
        return previous, stored_problems
    return plan, problems


#: Retry budgets the technical lead's node keeps under its own keys, beside the
#: stage's structured-response budget. Each belongs to one plan: see where
#: they are cleared when a plan is dispatched.
_READINESS_RETRIES = "technical_lead:work_orders"
_ASSIGNMENT_RETRIES = "technical_lead:assignments"


def _max_structured_retries() -> int:
    """How many times a stage may be restarted for producing no structured answer.

    A retry here is not a repeat of the same request: the previous attempt's
    conversation is abandoned and the stage starts a fresh one. That distinction
    is the whole reason retrying works. The failure is not "the model cannot do
    this" but "this particular conversation went somewhere it could not come
    back from" - on one run a specialist answered in 431,441 characters of
    prose under a heading it wrote itself, and every resume replayed that same
    conversation and failed the same way in four minutes.

    Two by default: a stage costs minutes, so a third attempt is cheap next to a
    dead run, and a model that fails three fresh conversations is not going to
    succeed on a fourth.
    """
    raw = os.environ.get("WORKFLOW_MAX_STRUCTURED_RETRIES", "").strip()
    if not raw:
        return 2
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning("Malformed WORKFLOW_MAX_STRUCTURED_RETRIES=%r; using 2", raw)
        return 2


def _transient_retry_update(
    state: WorkflowGraphState, stage_name: str, error: BaseException
) -> dict[str, Any] | None:
    """Retry a stage whose model call failed in a way another attempt may fix.

    Returns None when the error is not transient, or when the budget is spent -
    the caller then re-raises, so a persistent fault still ends the run with the
    provider's own message rather than looping on it.
    """
    if not _is_transient_model_error(error):
        return None
    retries = dict(state.get("structured_retries") or {})
    key = f"{stage_name}:transient"
    attempted = retries.get(key, 0)
    if attempted >= _max_structured_retries():
        return None
    retries[key] = attempted + 1
    logger.warning(
        "Stage %s hit a transient model error (attempt %d of %d): %s",
        stage_name, attempted + 1, _max_structured_retries(), str(error)[:200],
    )
    return {
        "stage": _owning_node(stage_name),
        "structured_retries": retries,
        "pending_approval": None,
        "pending_inner_thread_id": None,
        "pending_decision": None,
    }


def _hand_back(update: dict[str, Any], output_key: str) -> bool:
    """Whether the caller must return this update unchanged.

    A gated agent hands back without output in two shapes: paused waiting on a
    human, and retrying after a stage produced no structured response. Both
    look the same from here - the output key is simply absent - and both must
    be returned untouched.

    Callers used to test only for the pause. A retry therefore fell through
    into code that rewrote `stage` and read an output key that was not there:
    on one run `product_manager_node` overwrote the retry's
    "go back to product_manager" with "tools_models" and sent a state carrying
    no `product_intake` downstream, which is how the run reached
    `KeyError: 'product_intake'` despite the retry working correctly.
    """
    return output_key not in update


_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def _first_json_object(text: str) -> str | None:
    """The first balanced `{...}` in `text`, fenced or bare.

    A plain `json.loads` is not enough. The model writes the object and then
    keeps talking, so the message is valid JSON followed by prose and
    `json.loads` fails with "Extra data" on an answer that is entirely present.
    Measured on one run: two such messages, 2,027 and 2,028 characters,
    each a complete response object with a paragraph after it.
    """
    fenced = _JSON_FENCE.search(text)
    if fenced:
        return fenced.group(1)

    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    # Unbalanced: the object never closed. Returning None here made the answer
    # unreachable for every consumer of this function, because each of them
    # treats None as "no object present" rather than "object unfinished" - so
    # a model that truncated one character short of valid JSON had written an
    # answer nothing could read. Measured on one run, whose
    # `specialist_testing` wrote the same 3068-byte object fifty-nine times and
    # failed at character 3067 every time.
    #
    # Hand the remainder back instead. Callers that need valid JSON parse it
    # and fail, which is what they did before; callers that can repair it -
    # `settled_answer._answer_in` - now get the chance.
    return text[start:] if depth > 0 else None


def _answer_written_into_the_conversation(result: dict[str, Any], schema: Any) -> Any | None:
    """The structured response, recovered from a message that contains it.

    The failure this exists for is not a model that could not answer. It is a
    model that answered correctly and sent it down the wrong channel: on
    one run `specialist_backend_0` emitted its complete response object as
    a chat message three times, each followed by a sentence of commentary, and
    the workflow discarded all three and then failed the stage. The nudge did
    not help, because being asked for the schema produced the same thing again.

    Validated against the stage's own response model before it is accepted, so
    this recognises the answer rather than guessing at one: anything that does
    not satisfy the schema is ignored exactly as before.
    """
    if schema is None:
        return None
    messages = result.get("messages") or []
    for message in reversed(messages):
        if getattr(message, "type", None) != "ai":
            continue
        text = str(getattr(message, "content", "") or "")
        if "{" not in text:
            continue
        candidate = _first_json_object(text)
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except ValueError:
            # `_first_json_object` hands back an unbalanced object rather than
            # None now, because that is the shape of a truncated answer. Try to
            # close it; the schema still has to accept the result.
            from app.agents.settled_answer import _repair_json

            repaired = _repair_json(candidate)
            if not repaired:
                continue
            try:
                payload = json.loads(repaired)
            except ValueError:
                continue
        if not isinstance(payload, dict):
            continue
        from app.agents.settled_answer import _without_repeats
        from app.agents.wrapped_answer import unwrapped

        try:
            return schema.model_validate(unwrapped(_without_repeats(payload), schema))
        except Exception:  # noqa: BLE001 - a near-miss is not the answer
            continue
    return None


_STRUCTURED_RESPONSE_NUDGE = (
    "Stop. You wrote your answer into the conversation as text. Text in the "
    "conversation is not returned to the workflow - only the structured "
    "response is, and you have not produced one, so from the workflow's side "
    "this stage has delivered nothing.\n\n"
    "Do not redo the work, do not write any more files, and do not call any "
    "more tools. You already have the answer above. Return it now through the "
    "response schema, and nothing else."
)
"""What to say to a model that answered in prose.

It is addressed to a model that has the answer and failed only at the last
step, so it forbids the two things such a model does next: starting over, and
explaining itself in more prose."""


_CUT_OFF_WHILE_REASONING_NUDGE = (
    "Your last reply was cut off at its output limit while you were still "
    "reasoning, so nothing of it reached the workflow - no text, no tool call, "
    "no structured response.\n\n"
    "Do not start the work again and do not reason it all through a second "
    "time: that reaches the same limit. Return your structured response now, "
    "briefly, from what you have already established. If something you needed "
    "is still unknown, say what in `blockers` - that is a complete answer too."
)
"""What to say to a model whose reply was all reasoning and no answer."""


def _answer_left_in_a_spinning_stage(
    agent: Any, inner_thread_id: str, schema: Any
) -> Any | None:
    """The structured response a looping stage kept writing into its messages.

    A structured-output agent runs until the model calls the response tool. A
    model that writes its answer as text instead never satisfies that, so the
    loop continues: it re-reads its inputs, writes the same answer again, and
    only the superstep ceiling ends it.

    The answer is in the conversation the whole time. `_run_gated_agent`'s
    recovery cannot reach it, because that runs on the agent's return and this
    agent does not return - it raises. So read the messages back off the
    checkpoint and try the same recovery there.

    Measured on one run: forty minutes and 266 events, every cycle
    containing a complete specification object printed as a chat message.
    """
    if schema is None:
        return None
    try:
        snapshot = agent.get_state({"configurable": {"thread_id": inner_thread_id}})
    except Exception:  # noqa: BLE001 - a failed read is not worse than no read
        logger.debug("Could not read %s back after it spun", inner_thread_id, exc_info=True)
        return None
    values = getattr(snapshot, "values", None)
    if not isinstance(values, dict):
        return None
    return _answer_written_into_the_conversation(values, schema)


def _what_the_ledger_confirms(repo_root: str, verification: Any) -> str:
    """A claimed command the ledger records running and passing, or "".

    See `app.analysis.verification_claims`. Never raises: a ledger that cannot
    be read proves nothing, which is the same answer as a claim that was never
    run, and neither may break a fix.
    """
    try:
        from app.analysis.verification_claims import proven_commands

        proven = proven_commands(repo_root, verification)
        return " ".join(proven[0]) if proven else ""
    except Exception:  # noqa: BLE001
        logger.debug("Could not check verification claims against the ledger")
        return ""


def _what_the_last_failure_printed(run_id: str | None) -> dict[str, str] | None:
    """The last failing command's own output, or None. Never raises.

    Imported here rather than at module scope: the transcript module is
    observability, and a defect fix must not fail because a record could not be
    read.
    """
    try:
        from app.observability.transcript import last_failing_command

        return last_failing_command(run_id)
    except Exception:  # noqa: BLE001 - a brief is better without it than absent
        logger.debug("Could not read the last failing command for %s", run_id)
        return None


def _outcome_summary(structured_response: Any) -> str:
    """One line saying what a stage decided, or "" when it decided nothing.

    Read off the response object by field name rather than by stage, because
    every reviewing stage has its own schema and they agree on the two fields
    that matter: what the verdict was, and what has to change. A stage whose
    schema has neither - a specialist returning a report, say - produces
    nothing, which is the right amount of narration for it.
    """
    status = getattr(structured_response, "status", None)
    findings = getattr(structured_response, "findings", None)
    if status is None and not findings:
        return ""

    verdict = str(getattr(status, "value", status) or "").strip()
    parts = [f"Outcome: {verdict}"] if verdict else []

    described: list[str] = []
    for finding in list(findings or [])[:3]:
        severity = getattr(finding, "severity", "") or ""
        severity = str(getattr(severity, "value", severity)).strip()
        text = str(
            getattr(finding, "description", None)
            or getattr(finding, "summary", None)
            or finding
        ).strip()
        if not text:
            continue
        described.append(f"[{severity}] {text}" if severity else text)

    total = len(list(findings or []))
    if total:
        parts.append(f"{total} finding(s)")
    parts.extend(described)
    if total > len(described):
        parts.append(f"... and {total - len(described)} more")
    return "\n".join(parts)


#: How many items of one kind a stage summary lists. A stage that changed thirty
#: files is described by the first few and a count, not by all thirty.
MOST_ITEMS_IN_A_STAGE_SUMMARY = 6

#: The fields of `SpecialistOutput` worth a line, in the order a reader wants
#: them: what changed, then what was decided, then what was proven, then what is
#: in the way.
_WORTH_RECORDING = (
    ("changed_files", "Files changed"),
    ("decisions", "Decisions"),
    ("tests", "Tests"),
    ("documentation", "Documentation"),
    ("risks", "Risks"),
    ("blockers", "Blockers"),
)


def _what_this_stage_reported(structured_response: Any) -> str:
    """The body of a stage's summary document, or "".

    `_outcome_summary` returns "" for a stage whose schema has neither a status
    nor findings, and says in its own docstring that this is "the right amount of
    narration for it" - which is a decision about the live activity stream, where
    publishing nothing is correct.

    The same empty string was also written to `docs/stage_summaries/<stage>.md`.
    Across the stored runs that is 204 of 229 summary documents holding 25 bytes:
    a heading and nothing else. Every `defect_fix`, every `test_round`, and every
    specialist. Only the three reviewing stages, which have a status, said
    anything.

    So the stream keeps its silence and the document gets what the stage actually
    returned. A specialist reports changed files, decisions, tests, documentation,
    risks and blockers, and all of it is already on the object.

    Returns "" when the response really carries nothing, and the caller then
    writes no document rather than an empty one.
    """
    lines: list[str] = []
    for field, label in _WORTH_RECORDING:
        items = [str(item).strip() for item in (getattr(structured_response, field, None) or ())]
        items = [item for item in items if item]
        if not items:
            continue
        shown = items[:MOST_ITEMS_IN_A_STAGE_SUMMARY]
        lines.append(f"{label} ({len(items)}):")
        lines.extend(f"- {item}" for item in shown)
        if len(items) > len(shown):
            lines.append(f"- ... and {len(items) - len(shown)} more")
        lines.append("")
    runs = list(getattr(structured_response, "verification", None) or ())
    if runs:
        lines.append(f"Commands run ({len(runs)}):")
        for entry in runs[:MOST_ITEMS_IN_A_STAGE_SUMMARY]:
            # `command` is the argv list, which is how every execution tool in
            # this harness passes one. `str()` on it renders "['npm', 'test']",
            # so it is joined back into the command a reader would type.
            raw = getattr(entry, "command", "") or ""
            command = (
                " ".join(str(part) for part in raw) if isinstance(raw, (list, tuple))
                else str(raw)
            ).strip()
            code = getattr(entry, "exit_code", getattr(entry, "returncode", None))
            if command:
                lines.append(f"- {command}" + (f" -> exit {code}" if code is not None else ""))
        if len(runs) > MOST_ITEMS_IN_A_STAGE_SUMMARY:
            lines.append(f"- ... and {len(runs) - MOST_ITEMS_IN_A_STAGE_SUMMARY} more")
    return "\n".join(lines).strip()


def _spun_without_finishing(stage_name: str, exc: Exception) -> str | None:
    """Explain a stage that hit its superstep ceiling, or None if it did not.

    A `GraphRecursionError` from an inner agent reads as a LangGraph internal,
    and the operator is left with a stack trace for a condition that has a plain
    description: the stage went round in a circle and never produced an answer.

    Measured on one run: the principal architect spent twenty-two minutes
    printing the same specification into the conversation and re-reading the
    same three documents, with no restart recorded, because every workflow guard
    is checked when a stage ends and this one never ended.
    """
    text = f"{type(exc).__name__}: {exc}"
    if "recursion" not in text.lower() and "GraphRecursionError" not in text:
        return None
    return (
        f"The '{stage_name}' stage ran {INNER_AGENT_RECURSION_LIMIT} steps without "
        "finishing, so it was stopped. That is a loop inside the stage itself - "
        "typically the model writing its answer into the conversation, re-reading "
        "the same files, and writing it again - rather than work that was taking "
        "a long time.\n"
        "The usual cause is a model that will not return its structured response. "
        "The artifacts the stage wrote are on disk and a resume re-runs it on a "
        "fresh conversation; if it spins again, the stage's response schema is "
        "likely too large for this model to produce in one turn."
    )


def _repository_root(state: WorkflowGraphState) -> str | None:
    """This run's workspace path, or None when the state has no repository.

    Threaded into the restart so the carry-over note can name files the way the
    tools name them. It was not, and the parameter defaulted to None, so the
    note shipped absolute container paths and the unit test that covered the
    None case passed while production did the wrong thing - visible only by
    reading a live run's transcript.
    """
    try:
        return state["repository"].root_path
    except Exception:  # noqa: BLE001 - a hint must never fail a restart
        return None


def _restart_on_a_fresh_conversation(
    state: WorkflowGraphState,
    stage_name: str,
    inner_thread_id: str,
    why: str,
    repo_root: str | None = None,
) -> dict[str, Any] | None:
    """Start the stage over on a clean conversation, or None when spent.

    Clearing `pending_inner_thread_id` is what makes this a retry instead of a
    loop: without it the resume path re-enters the very conversation that
    failed, replays it, and fails identically - which is exactly what happened
    on one run until this existed.

    Shared by the two ways a stage can produce no answer. They were handled
    differently for no reason anyone could defend: a stage that RETURNED
    without a structured response got three fresh conversations, and a stage
    that SPUN until the recursion limit got none - it failed the whole run on
    its first attempt. One run died that way in `specialist_ui_ux_2`,
    with three restarts unused, while the error it raised said in as many
    words that "a resume re-runs it on a fresh conversation".
    """
    retries = dict(state.get("structured_retries") or {})
    attempted = retries.get(stage_name, 0)
    if attempted >= _max_structured_retries():
        return None
    retries[stage_name] = attempted + 1
    logger.warning(
        "Stage %s %s; retrying on a fresh conversation (attempt %d of %d)",
        stage_name, why, attempted + 2, _max_structured_retries() + 1,
    )
    # What the dying attempt established, before its thread stops being
    # anybody's key. Clearing the conversation is right and discarding the
    # facts is not: three attempts used to re-read the same files and re-run
    # the same commands. See `app.agents.carry_over`.
    carried = dict(state.get("stage_carry_over") or {})
    try:
        from app.agents.carry_over import carry_over_note

        note = carry_over_note(inner_thread_id, repo_root)
    except Exception:  # noqa: BLE001 - never fail a restart over a hint
        note = ""
    if note:
        carried[stage_name] = note
    return {
        "stage_carry_over": carried,
        # The node that owns this stage, never the stage's own name:
        # `specialist_ui_ux_0` is not a graph node.
        "stage": _owning_node(stage_name),
        "structured_retries": retries,
        "pending_approval": None,
        "pending_inner_thread_id": None,
        "pending_decision": None,
        "inner_thread_ids": [*state.get("inner_thread_ids", []), inner_thread_id],
    }


def _inner_agent_config(
    inner_thread_id: str,
    run_id: str | None,
    callbacks: Any,
    *,
    stage: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """The config for one role agent's own invocation.

    The run id travels with it. Middleware inside the agent has no other way to
    learn which run it is part of - `get_config()` is all it can see - and the
    transcript middleware found nothing at all until this was added: the
    callbacks carry the run id because they are constructed with it, and the
    middleware is constructed once per agent and cannot be.

    Built here rather than inline at each call site, because there are two of
    them and a third would otherwise be written without it, which is how the
    transcript came to record half a run.

    `stage` travels for the same reason and was missing for the same reason:
    one agent serves many stages, so middleware built with a stage name knows
    only the phase. Without it the transcript filed 93% of tool calls under
    `implementation`. See `app.tracing.APP_STAGE_KEY`.
    """
    from app.tracing import APP_STAGE_KEY

    configurable: dict[str, Any] = {"thread_id": inner_thread_id}
    if run_id:
        configurable[APP_RUN_ID_KEY] = run_id
    if stage:
        configurable[APP_STAGE_KEY] = stage
    return {"configurable": configurable, "callbacks": callbacks, **extra}


def _nudge_text(result: dict[str, Any] | None, schema: Any) -> str:
    """What to say to a model that has not returned its structured response.

    Two different failures wear the same face here. A model that wrote a
    correct answer as prose needs only to be told the channel - that is
    `_STRUCTURED_RESPONSE_NUDGE`. A model whose answer is nearly right needs to
    know which field is wrong, and telling it "return it through the schema"
    produces the same near miss again.

    Measured on one run's `principal_architect`. The correction that rides
    on the model request fixed it mid-conversation: the turn after it fired,
    `product_scope` came back as the string the schema asks for. But that turn
    made no tool call, so the stage ended, the generic nudge ran, the restart
    threw the conversation away, and the fresh one opened with the same object
    shape as before. The diagnosis existed and was not used at the one moment
    it would have settled the stage.
    """
    last_ai = next(
        (m for m in reversed((result or {}).get("messages") or []) if getattr(m, "type", None) == "ai"),
        None,
    )
    if _nothing_but_reasoning(last_ai):
        # Checked before anything else, because the prose nudge is false here:
        # it opens "You wrote your answer into the conversation as text" and
        # "You already have the answer above", to a model whose reply was cut
        # off before it wrote a word. Measured on one run's `test_round_1`.
        return _CUT_OFF_WHILE_REASONING_NUDGE
    if schema is None or not result:
        return _STRUCTURED_RESPONSE_NUDGE
    try:
        from app.agents.settled_answer import _why_it_was_not_accepted

        for message in reversed(result.get("messages") or []):
            if getattr(message, "type", None) != "ai":
                continue
            why = _why_it_was_not_accepted(message, schema)
            if why:
                return why
            # The most recent AI message decides; an older near miss has
            # already been superseded.
            break
    except Exception:  # noqa: BLE001 - a nudge must not fail the stage
        return _STRUCTURED_RESPONSE_NUDGE
    return _STRUCTURED_RESPONSE_NUDGE


def _nudge_for_the_structured_response(
    agent: Any,
    inner_thread_id: str,
    callbacks: Any,
    previous: dict[str, Any] | None = None,
    schema: Any = None,
    run_id: str | None = None,
    stage: str | None = None,
) -> dict[str, Any] | None:
    """Ask the same conversation for the answer it already worked out.

    The retry below starts the stage over on a clean conversation, which works
    but throws away everything the stage learned. Measured on one run:
    `test_round_0` read four files, globbed for existing tests, and wrote a
    paragraph of correct analysis - then returned it as prose. The restart
    re-read the same four files and re-ran the same globs, about twenty-seven
    events and five approval gates to get back to where it already was.

    A restart is also the wrong remedy for the observed failure. The model did
    not run out of room or lose the thread; it did the work and skipped the
    schema. So ask it for the schema.

    Returns the new result when the nudge produced something worth acting on (a
    structured response, or an approval pause), and None when it changed
    nothing and the caller should fall through to the restart.
    """
    try:
        with remembering(inner_thread_id):
            result = agent.invoke(
                {"messages": [{"role": "user", "content": _nudge_text(previous, schema)}]},
                config=_inner_agent_config(inner_thread_id, run_id, callbacks, stage=stage),
            )
    except Exception:  # noqa: BLE001 - a failed nudge is not a failed run
        # Whatever went wrong here, the restart below is still available and is
        # the path this code took before the nudge existed.
        logger.warning(
            "Nudging thread %s for its structured response failed; falling back "
            "to a fresh conversation", inner_thread_id, exc_info=True,
        )
        return None

    if result.get("structured_response") is not None:
        # Logged because a nudge that works is otherwise invisible: it leaves no
        # warning, so the only measurable trace of this whole mechanism was the
        # restarts it failed to prevent. Comparing the two counts is how anyone
        # tells "the nudge is working" from "prose failures got rarer".
        logger.info(
            "Thread %s returned its structured response after one reminder; "
            "no restart needed", inner_thread_id,
        )
        return result
    if result.get("__interrupt__"):
        return result

    # A model that answered in prose once often does it again, and the answer
    # it wrote the second time is just as usable as the first. Reading it here
    # costs nothing and saves the restart, which is the expensive path this
    # whole function exists to avoid.
    recovered = _answer_written_into_the_conversation(result, schema)
    if recovered is not None:
        logger.info(
            "Thread %s answered in the conversation again after the reminder; "
            "recovered it without a restart", inner_thread_id,
        )
        return {**result, "structured_response": recovered}
    return None


def _the_reply_was_cut_off_before_it_began(message: Any) -> bool:
    """Whether the model hit its output ceiling having emitted nothing.

    The provider says so: `finish_reason` is `length` when the reply was
    truncated at `max_tokens`, and it arrives on the message in
    `response_metadata`. With no content and no tool call beside it, the whole
    budget went on reasoning the model never got to summarise.

    `_missing_structured_response` guessed at four causes and asked the reader
    to tell them apart by the shape of the last message - while this flag sat
    on that same message, saying which one it was.
    """
    for holder in ("response_metadata", "additional_kwargs"):
        data = getattr(message, holder, None)
        if isinstance(data, dict) and str(data.get("finish_reason") or "") == "length":
            return True
    return False


def _it_spent_its_whole_output_budget(stage_name: str, attempts: int) -> str:
    """The message for a stage that reasoned until its reply was truncated.

    Measured on one run, which failed after 3 hours 23 minutes at
    `defect_fix_2_4`. Fourteen model responses across the run came back with
    `finish_reason: length`, no text and no tool call - nine of them in that
    one stage. The run's settings were `model_max_output_tokens = 20000` with
    `thinking_effort = high`, and the defect-fix stages are where reasoning
    runs longest, so those nine calls produced literally nothing.

    The generic message named `MODEL_MAX_OUTPUT_TOKENS` second of four causes
    and told the reader to check whether the last message ends mid-sentence.
    There was no last message to check. An operator reading it would go
    looking for a prompt problem.

    It also says plainly that a fresh conversation cannot help, because the
    ceiling is per reply rather than per conversation. That is what the
    harness did next, three times, for over an hour.
    """
    import os

    configured = os.environ.get("MODEL_MAX_OUTPUT_TOKENS", "").strip()
    budget = f"{configured} output tokens" if configured else "its configured output limit"
    # Only the attempt that failed is known to have hit the ceiling. The one
    # before it may have ended some other way - on one run it had used up its
    # model-call budget - so the message must not say they all hit it.
    tried = (
        f" This was attempt {attempts} at the stage; the earlier ones ended "
        "without a structured response too."
        if attempts > 1
        else ""
    )
    return (
        f"Agent '{stage_name}' spent its entire output budget before writing "
        "anything. The provider reported `finish_reason: length` with no text "
        f"and no tool call, which means the reply was cut off at "
        f"{budget} while the model was still reasoning."
        f"{tried}\n\n"
        "The work it did is not lost - artifacts it wrote are on disk.\n"
        "A FRESH CONVERSATION CANNOT FIX THIS. The ceiling is per reply, not "
        "per conversation, so a restart reasons from the beginning and reaches "
        "the same limit. Change one of these instead:\n"
        "- Raise MODEL_MAX_OUTPUT_TOKENS, or `model_max_output_tokens` in the "
        "runtime settings. This is the direct fix and costs only tokens.\n"
        "- Lower `thinking_effort` from `high`. Reasoning is what consumes the "
        "budget here, and the defect-fix stages are where it runs longest.\n"
        "- Use a model that stops reasoning to answer. A model that reasons "
        "past its own reply budget will do this on any long task."
    )


def _nothing_but_reasoning(message: Any) -> bool:
    """Whether this reply hit the output ceiling having produced nothing at all.

    Stricter than `_the_reply_was_cut_off_before_it_began`, which reports the
    truncation flag alone and so is also true of a reply that said a great deal
    and was cut off at the end. That difference decides whether a restart is
    worth attempting: a model that wrote nothing will write nothing again,
    because the ceiling is per reply, but one that was truncated mid-answer may
    well land inside the budget on a second pass.

    So this asks for what the name says - the flag, no content, and no tool call
    - and only that case skips the restart. The looser check keeps choosing the
    message, where naming the ceiling is right either way.
    """
    if not _the_reply_was_cut_off_before_it_began(message):
        return False
    if str(getattr(message, "content", "") or "").strip():
        return False
    return not (getattr(message, "tool_calls", None) or ())


def _missing_structured_response(
    stage_name: str, result: dict[str, Any], *, attempts: int = 1
) -> str:
    """Say why a stage produced no structured response, from what it did produce.

    The old message guessed - "this often happens if the context limit or max
    token limit was reached" - and the guess was usually wrong. It cost five
    commits of context-budget tuning on a branch where the budgets were never
    the problem.

    The last message is the evidence. A model that ran out of room stops
    mid-sentence and leaves a short tail; a model that answered in prose leaves
    a long one, often with the words it was asked to structure written out as a
    heading. Reporting the length and the tail lets a reader tell those apart
    without going to the event log.
    """
    messages = result.get("messages") or []
    last = next(
        (m for m in reversed(messages) if getattr(m, "type", None) == "ai"), None
    )
    text = str(getattr(last, "content", "") or "")

    ran_out = _the_reply_was_cut_off_before_it_began(last)
    detail = (
        f"Its last message was {len(text):,} characters."
        if text
        else "It produced no final message at all."
    )
    if ran_out:
        return _it_spent_its_whole_output_budget(stage_name, attempts)
    if "structured response" in text.lower():
        detail += (
            " That message mentions a structured response, so the model most "
            "likely wrote the answer as prose instead of returning it through "
            "the response schema."
        )

    tried = (
        f" This was tried {attempts} times, each on a fresh conversation."
        if attempts > 1
        else ""
    )
    return (
        f"Agent '{stage_name}' finished without returning its structured response. "
        f"{detail}{tried}\n\n"
        "The work it did is not lost - artifacts it wrote are on disk - but the "
        "workflow needs the structured answer to continue.\n"
        "Common causes, in the order worth checking:\n"
        "- The model answered in prose rather than calling the response schema. "
        "Smaller local models do this; a model with stronger structured-output "
        "support fixes it.\n"
        "- The reply was cut off by MODEL_MAX_OUTPUT_TOKENS. Raise it if the "
        "last message ends mid-sentence.\n"
        "- The conversation outgrew the window. Lower CTX_MAX_TOKENS so "
        "compaction runs sooner."
    )


class RunCancelled(RuntimeError):
    """A cancellation was seen between supersteps and the graph stopped for it.

    Item 7 of `docs/harness-hardening-plan-part3.md`. Cancelling a run did two
    things - set `cancel_requested`, and revoke the Celery task with SIGTERM -
    and the flag was read only between graph *invokes*. Within one invoke the
    graph runs every stage it can reach, so a cancellation arriving at the start
    of a specialist was not seen until that specialist finished, and the SIGTERM
    that would have stopped it sooner kills the turn wherever it is: the run
    then resumes from the last checkpoint, which for a specialist stage can be a
    whole stage of work back.

    Raised at a stage boundary, where the graph has just checkpointed and
    nothing is in flight, so stopping costs nothing that was not already saved.
    """


#: Per-process memo of runs already known to be cancelled, so the check costs
#: one query per run rather than one per stage after the first sighting. A
#: cancellation is never withdrawn - `request_cancel` only sets the flag - so
#: this can cache the positive and must not cache the negative.
_CANCELLED_RUNS: set[str] = set()


def _stop_if_cancelled(run_id: str | None) -> None:
    """Raise `RunCancelled` when this run has been asked to stop.

    Called at stage boundaries. One indexed lookup per stage against a run that
    lasts minutes is not worth caching further, and reading it fresh is what
    makes a cancellation take effect at the next stage rather than at the next
    invoke.

    Never raises anything else. A database that cannot answer must not be the
    reason a healthy run stops: the coarser checks in `runner._run_loop` still
    hold, and this is an improvement in granularity, not the only guard.
    """
    if not run_id:
        return
    if run_id in _CANCELLED_RUNS:
        raise RunCancelled(f"Run {run_id} was cancelled.")
    try:
        from app.server.run_store import RunStore

        requested = RunStore.shared().is_cancel_requested(run_id)
    except Exception:  # noqa: BLE001 - a cancel check must never fail a run
        logger.debug("Could not read the cancel flag for %s", run_id, exc_info=True)
        return
    if requested:
        _CANCELLED_RUNS.add(run_id)
        logger.info("Run %s was cancelled; stopping at a stage boundary", run_id)
        raise RunCancelled(f"Run {run_id} was cancelled.")


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
    # Before anything else, and before this stage's first model call. The graph
    # has just checkpointed the previous stage, so stopping here costs nothing
    # that was not already saved.
    _stop_if_cancelled(config["configurable"].get(APP_RUN_ID_KEY))

    # Narration only. `build_activity_callbacks` returns [] when the run id is
    # unknown or the feature is switched off, and the handler never raises.
    from app.server.agent_stream import build_activity_callbacks

    activity = build_activity_callbacks(config["configurable"].get(APP_RUN_ID_KEY), stage_name)

    pending_decision = state.get("pending_decision")
    if pending_decision is not None:
        inner_thread_id = state.get("pending_inner_thread_id")
        if not inner_thread_id:
            inner_thread_id = f"{outer_thread_id}:{stage_name}:{uuid.uuid4().hex[:8]}"
        try:
            result = resume_with_decision(
                agent,
                inner_thread_id,
                pending_decision,
                callbacks=activity,
                recursion_limit=INNER_AGENT_RECURSION_LIMIT,
                run_id=config["configurable"].get(APP_RUN_ID_KEY),
                stage=stage_name,
            )
        except Exception as exc:  # noqa: BLE001 - re-raised unless handled below
            if _is_context_overflow(exc):
                return _context_overflow_update(stage_name, exc)
            spun = _spun_without_finishing(stage_name, exc)
            if spun is not None:
                # It spent the whole loop writing the answer into its messages.
                # Read it back rather than discard a stage's work over the
                # channel it arrived on.
                salvaged = _answer_left_in_a_spinning_stage(
                    agent, inner_thread_id, getattr(agent, "workflow_response_format", None)
                )
                if salvaged is not None:
                    logger.info(
                        "Stage %s spun without returning, but had written its "
                        "structured response into the conversation; recovered it",
                        stage_name,
                    )
                    return {
                        output_key: salvaged,
                        "stage": next_stage,
                        "pending_approval": None,
                        "pending_inner_thread_id": None,
                        "pending_decision": None,
                        "inner_thread_ids": [
                            *state.get("inner_thread_ids", []), inner_thread_id
                        ],
                    }
                restarted = _restart_on_a_fresh_conversation(
                    state, stage_name, inner_thread_id,
                    "spun without returning an answer",
                    _repository_root(state),
                )
                if restarted is not None:
                    return restarted
                return _handing_on(stage="failed", error=spun)
            retry = _transient_retry_update(state, stage_name, exc)
            if retry is not None:
                return retry
            raise
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
        # A previous attempt at this stage left what it established. The
        # conversation is deliberately gone; the facts are worth keeping, and
        # without them each attempt re-read the same files and re-ran the same
        # commands. Prepended, so it is the first thing the attempt reads
        # rather than something it reaches after its own instructions.
        # A small project's files, before the stage's own request - read once
        # and kept in the server's prompt cache for the stage, instead of found
        # out one read at a time. Before the request, not after: the last
        # message a model reads is the one it answers. See
        # `app.agents.project_snapshot`.
        from app.agents.project_snapshot import project_snapshot

        snapshot = project_snapshot(getattr(state.get("repository"), "root_path", None))
        if snapshot:
            initial_request = {
                **initial_request,
                "messages": [
                    {"role": "user", "content": snapshot},
                    *(initial_request.get("messages") or []),
                ],
            }
        carried = (state.get("stage_carry_over") or {}).get(stage_name)
        if carried:
            initial_request = {
                **initial_request,
                "messages": [
                    {"role": "user", "content": carried},
                    *(initial_request.get("messages") or []),
                ],
            }
        try:
            # `remembering`, so the per-stage memory is keyed by the thread this
            # invocation owns rather than by whatever config a fan-out reports.
            # Every `Send` in a superstep sees the parent's config, so six
            # concurrent specialists shared one slot - and that memory holds
            # which lines of which files a stage has been given.
            with remembering(inner_thread_id):
                result = agent.invoke(
                    initial_request,
                    config=_inner_agent_config(
                        inner_thread_id,
                        config["configurable"].get(APP_RUN_ID_KEY),
                        activity,
                        stage=stage_name,
                        recursion_limit=INNER_AGENT_RECURSION_LIMIT,
                    ),
                )
        except Exception as exc:  # noqa: BLE001 - re-raised unless handled below
            if _is_context_overflow(exc):
                return _context_overflow_update(stage_name, exc)
            spun = _spun_without_finishing(stage_name, exc)
            if spun is not None:
                # It spent the whole loop writing the answer into its messages.
                # Read it back rather than discard a stage's work over the
                # channel it arrived on.
                salvaged = _answer_left_in_a_spinning_stage(
                    agent, inner_thread_id, getattr(agent, "workflow_response_format", None)
                )
                if salvaged is not None:
                    logger.info(
                        "Stage %s spun without returning, but had written its "
                        "structured response into the conversation; recovered it",
                        stage_name,
                    )
                    return {
                        output_key: salvaged,
                        "stage": next_stage,
                        "pending_approval": None,
                        "pending_inner_thread_id": None,
                        "pending_decision": None,
                        "inner_thread_ids": [
                            *state.get("inner_thread_ids", []), inner_thread_id
                        ],
                    }
                restarted = _restart_on_a_fresh_conversation(
                    state, stage_name, inner_thread_id,
                    "spun without returning an answer",
                    _repository_root(state),
                )
                if restarted is not None:
                    return restarted
                return _handing_on(stage="failed", error=spun)
            retry = _transient_retry_update(state, stage_name, exc)
            if retry is not None:
                return retry
            raise

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
        # First, look for the answer in what the model already said. This costs
        # no model call and recovers the common case: the schema was produced
        # and printed rather than returned.
        recovered = _answer_written_into_the_conversation(
            result, getattr(agent, "workflow_response_format", None)
        )
        if recovered is not None:
            logger.info(
                "Stage %s wrote its structured response into the conversation; "
                "recovered it without a retry", stage_name,
            )
            structured_response = recovered

    if structured_response is None:
        # Then ask the conversation for it. Once per node execution, so this
        # cannot loop.
        #
        # But not when `settled_answer` ended the thread at its model-call
        # budget. That re-invokes the same inner thread, which re-enters at
        # `__start__` and runs another model call before stopping again - so
        # every gate costs a call and the count climbs until the run's repeat
        # guard kills it. Measured on one run's `test_round_3`: eighteen
        # re-entries and thirty-four hard stops on one inner thread. The model
        # has already been told it is out of room and kept going; asking again
        # cannot produce a different answer, so go straight to the retry.
        from app.agents.settled_answer import was_stopped_by_the_budget

        nudged = None
        if not was_stopped_by_the_budget(result):
            nudged = _nudge_for_the_structured_response(
                agent,
                inner_thread_id,
                activity,
                result,
                getattr(agent, "workflow_response_format", None),
                config["configurable"].get(APP_RUN_ID_KEY),
                stage_name,
            )
        elif schema_of_stage := getattr(agent, "workflow_response_format", None):
            # The nudge's second half is free: it reads the conversation the
            # thread already holds. Do that here rather than lose it.
            recovered = _answer_written_into_the_conversation(result, schema_of_stage)
            if recovered is not None:
                logger.info(
                    "Stage %s was stopped at its model-call budget but had "
                    "written its structured response; recovered it without a "
                    "retry", stage_name,
                )
                structured_response = recovered
        if nudged is not None:
            if nudged.get("__interrupt__"):
                approval = extract_pending_approval(
                    nudged,
                    state["repository"].root_path,
                    requested_by=stage_name,
                    stage=stage_name,
                )
                return {
                    "stage": f"{APPROVAL_PAUSE_PREFIX}{stage_name}",
                    "pending_approval": approval,
                    "pending_inner_thread_id": inner_thread_id,
                    "pending_decision": None,
                    "inner_thread_ids": [
                        *state.get("inner_thread_ids", []), inner_thread_id
                    ],
                }
            result = nudged
            structured_response = nudged["structured_response"]

    if structured_response is None:
        # One failure is not worth restarting for: a reply cut off at the output
        # ceiling before it produced anything. The ceiling is per reply, so a
        # fresh conversation reasons from the beginning and reaches it again,
        # which is what `_it_spent_its_whole_output_budget` tells the operator in
        # capitals - while the harness did it three times anyway.
        #
        # Recorded on one run, which spent 3h23m reaching that conclusion,
        # and reproduced on one run: `test_round_2` after four sprints of
        # work, three restarts, same ceiling, run failed. The remedy is a setting
        # - a bigger output budget, or less reasoning - and no number of attempts
        # substitutes for it. Failing now says the same thing an hour earlier and
        # leaves the artifacts on disk either way.
        out_of_room = _nothing_but_reasoning(
            next(
                (
                    m
                    for m in reversed(result.get("messages") or [])
                    if getattr(m, "type", None) == "ai"
                ),
                None,
            )
        )
        # Start the stage over on a clean conversation rather than failing the
        # run. Clearing `pending_inner_thread_id` is what makes this a retry
        # instead of a loop: without it the resume path re-enters the very
        # conversation that failed, replays it, and fails identically - which is
        # exactly what happened on one run until this existed.
        restarted = (
            None
            if out_of_room
            else _restart_on_a_fresh_conversation(
                state, stage_name, inner_thread_id, "produced no structured response",
                _repository_root(state),
            )
        )
        if restarted is not None:
            return restarted
        attempted = (state.get("structured_retries") or {}).get(stage_name, 0)
        raise ValueError(
            _missing_structured_response(stage_name, result, attempts=attempted + 1)
        )

    # An answer is cleaned, a file is refused: see `app.agents.model_output`.
    from app.agents.model_output import answer_without_leaked_turns

    structured_response = answer_without_leaked_turns(structured_response)

    succeeded = dict(state.get("structured_retries") or {})
    succeeded.pop(stage_name, None)
    # Dropped with the retry count, and for the same reason. A stage name
    # recurs - `specialist_ui_ux_0` ran in three separate sprints of one
    # run - so a note kept past the attempt it was written for would
    # arrive at a later sprint describing files a different task had read.
    spent = dict(state.get("stage_carry_over") or {})
    spent.pop(stage_name, None)

    # What the stage decided, on the record. Narration only, and never allowed
    # to fail the stage that produced it.
    try:
        from app.server.agent_stream import publish_stage_outcome

        outcome_text = _outcome_summary(structured_response)
        publish_stage_outcome(activity, outcome_text)
        # The document says more than the stream. A reviewing stage's verdict is
        # the whole story for it; a specialist's is what it changed and found,
        # and writing "" left 204 of 229 summaries holding only a heading.
        recorded = outcome_text or _what_this_stage_reported(structured_response)
        if recorded:
            _record_document(
                state,
                f"docs/stage_summaries/{stage_name}.md",
                render_document("stage_summary", stage=stage_name, recorded=recorded),
            )
    except Exception:  # noqa: BLE001 - narration is never load-bearing
        logger.debug("Could not publish the outcome of %s", stage_name, exc_info=True)

    return {
        output_key: structured_response,
        "stage": next_stage,
        "structured_retries": succeeded,
        "stage_carry_over": spent,
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


_GATING_SEVERITIES = frozenset({"blocking", "major", "critical", "high"})
"""Severities that justify sending work back.

Spans all four reviewer vocabularies, which differ: architecture uses
blocking/major/minor/informational, milestone blocking/major/minor/suggestion,
specialists blocking/major/minor, and security critical/high/medium/low/info.
A set that covered only one of them would gate that reviewer and silently let
the others through - or, as it did, gate none of them.

Kept as the canonical spelling of "bad enough to send back". The check itself
now asks `app.agents.severity` for the rank, so the same two rungs of the
ladder gate whatever word a reviewer used to reach them - including the ones
no vocabulary here defines but models write anyway (`severe`, `P1`, `Sev 2`).
"""

#: The worst rank that does NOT gate. Ranks 0 and 1 are exactly the four words
#: above; 2 is `medium`, which every vocabulary treats as "note it".
_WORST_RANK_THAT_PASSES = 1


def _severity_gates(value: Any) -> bool:
    """Whether a finding at this severity justifies another round of work."""
    from app.agents.severity import rank_of

    word = str(value or "").strip().lower()
    if word in _GATING_SEVERITIES:
        return True
    rank = rank_of(word)
    return rank is not None and rank <= _WORST_RANK_THAT_PASSES


def _a_success_measure_the_specification_drops(state: Any, spec_text: str) -> Any:
    """A major finding for a capability the intake requires and the spec never names.

    The Senior Architect Reviewer is given the specification and the brief's
    constraints, not its requirements, so it cannot see a feature that is
    missing - and the architect, which is given the whole intake, drops one
    whenever the intake's core workflows leave out what its success measures
    keep. On two runs the success measure read "Users can
    add, edit, and delete tasks", the workflows read add, toggle, delete and
    filter, and neither specification named editing; both were approved, and
    the gap surfaced at the milestone review a full build cycle later.

    Raised by the workflow rather than asked of the reviewer, because it is a
    comparison of two texts and not a judgement: see
    `app.agents.success_measures`. Once per run, and never on the revision that
    would exhaust `MAX_ARCHITECTURE_REVISIONS` - an architect that still leaves
    it out is not worth failing the run over, because the sprint-plan check and
    the milestone review are both still behind it.
    """
    if state.get("specification_coverage_checked"):
        return None
    if state.get("architecture_revision_count", 0) + 1 >= MAX_ARCHITECTURE_REVISIONS:
        return None
    measures = [
        str(m) for m in (getattr(state.get("product_intake"), "success_measures", None) or []) if str(m).strip()
    ]
    from app.agents.success_measures import capabilities_never_named

    missing = capabilities_never_named(spec_text, measures)
    if not missing:
        return None
    from app.agents.architecture_reviewer import ArchitectureReviewFinding

    lines = [
        f"success measure {n} (\"{measures[n - 1]}\") lists {', '.join(repr(w) for w in words)}"
        for n, words in sorted(missing.items())
    ]
    return ArchitectureReviewFinding(
        severity="major",
        description=(
            "The specification never mentions a capability the product intake's "
            "success measures require: " + "; ".join(lines) + ". Every later stage "
            "plans and builds from this document, so a capability it leaves out is "
            "left out of the product."
        ),
        evidence=(
            "Compared by the workflow against docs/product_intake.md: the "
            "specification text does not name it anywhere."
        ),
        required_remediation=(
            "Add each missing capability to the specification the way the others "
            "are specified - its data flow, the functions or endpoints that carry "
            "it, the UI that exposes it, and an acceptance criterion that verifies it."
        ),
    )


def _a_pass_over_its_own_findings(
    review: Any, repo_root: str | None, passing_status: str, stage_name: str
) -> Any:
    """`review`, sent back when its status passes the work over findings that gate.

    Both reviewers are told the same rule - approve or accept only when no
    blocking or major finding remains - and routing read `status` alone. One
    run's architecture review found that the specification never described
    how an existing item is edited, graded that **major**, and returned
    `approved` with no conditions; the run went on to sprint planning with
    the gap in place. The reply was the one written after the reviewer's
    reasoning ran out of room, with thinking switched off to get an answer at
    all, which is when a verdict and its findings are most likely to part.

    The findings are what the reviewer checked; the status is one word written
    after them. Where they disagree the findings win, filtered exactly as a
    `changes_required` is (`_findings_that_block`), so a finding outside the
    product's scope still does not gate.
    """
    if getattr(review, "status", None) != passing_status:
        return review
    gating = _findings_that_block(review, repo_root)
    if not gating:
        return review
    logger.warning(
        "Stage %s returned '%s' over %d finding(s) of its own at %s; routing it "
        "as changes_required",
        stage_name, passing_status, len(gating), "/".join(sorted(_GATING_SEVERITIES)),
    )
    return review.model_copy(update={"status": "changes_required"})


def _findings_that_block(review: Any, repo_root: str | None = None) -> list[Any]:
    """The findings in a review that justify another round of work.

    This constant existed and was used only to *format* the failure message at
    the end of the revision loop. Nothing routed on it, so `status` alone
    decided, and a reviewer that wrote `changes_required` over nothing but
    `minor` findings sent the work back anyway.

    That is what killed one run. Its six architecture reviews went:

        1  8 findings, 2 blocking   - legitimate
        2  4 findings, all minor    - sent back
        3 15 findings, all minor    - sent back
        4  4 findings, all minor    - sent back
        5 10 findings, 3 major      - escalated
        6 10 findings, the same 3   - limit reached, run failed

    Rounds 2, 3 and 4 were revisions nothing had asked for. The specification
    shrank from 205 lines to 134 across them while the reviewer asked for more
    detail, and by round 5 the reviewer had started demanding constructors,
    method signatures and parameter types - implementation detail a
    specification does not carry.

    A severity vocabulary the reviewer is given and the workflow ignores is not
    a vocabulary, it is decoration. `minor` has to mean "not worth another
    round" or there is no reason to offer the word.
    """
    gating = [
        finding
        for finding in (getattr(review, "findings", None) or [])
        if _severity_gates(getattr(finding, "severity", ""))
    ]
    if not gating or not repo_root:
        return gating
    # A finding about something the product's own documents never raise
    # cannot hold the sprint. `SCOPE_DISCIPLINE` says exactly this, at every
    # stage that can inflate scope, and it is ignored: across 50 transcripts
    # milestone review raised 13 BLOCKING accessibility findings against
    # briefs in which the words "accessibility", "aria", "wcag" and "screen
    # reader" do not appear at all. Seven of the last sixty failures are runs
    # that ended with "the milestone review still required changes".
    #
    # The finding is not discarded - it is still reported and still read. It
    # simply stops being a reason for another round, which is what the prompt
    # already told the reviewer to do with it.
    try:
        from app.analysis.scope_attestation import categories_in_scope, out_of_scope_reason

        in_scope = categories_in_scope(repo_root)
    except Exception:  # noqa: BLE001 - a scope check must never fail a review
        return gating
    kept = []
    for finding in gating:
        reason = out_of_scope_reason(str(getattr(finding, "category", "") or ""), in_scope)
        if reason:
            logger.info(
                "Milestone finding capped to minor, out of scope: %s", reason
            )
            continue
        kept.append(finding)
    return kept


def _format_finding(finding: Any) -> str:
    """Render one review finding as a line the architect can act on."""
    return (
        f"[{finding.severity}] {finding.description} "
        f"Required remediation: {finding.required_remediation}"
    )


def _record_document(state: WorkflowGraphState, relative_path: str, content: str) -> None:
    """Write one generated document into the run's workspace.

    Never raises: a review that has already been decided must not be lost
    because the document could not be saved.
    """
    from app.agents.model_output import CONTROL_TOKEN
    from app.tools.repository import write_approved_artifact

    try:
        write_approved_artifact(
            state["repository"].root_path,
            relative_path,
            # The workflow renders these from answers it has already accepted.
            # A delimiter one of them still carries is a model's, not the
            # document's, and refusing the write would lose the whole record -
            # a Sprint Record for one stray token in one work order's blockers.
            CONTROL_TOKEN.sub("", content),
            # The one writer allowed to touch the documents in
            # `WORKFLOW_DOCUMENTS`; it is the thing that renders them.
            by_the_workflow=True,
        )
    except Exception:  # noqa: BLE001 - the decision matters more than the record
        logger.warning("Could not write %s", relative_path, exc_info=True)


def _record_sprint_summary(
    state: WorkflowGraphState, status: str, failure_reason: str | None = None
) -> dict[str, Any]:
    """Record one attempt at the current sprint and re-render its document.

    Returns the `sprint_attempts` update, which every caller must merge into
    what it returns - the attempt list is what makes a re-run appendable rather
    than overwriting, and an attempt that is not checkpointed is an attempt the
    next one cannot see.

    Never raises. It runs at the end of a sprint whose outcome has already been
    decided, and a document that could not be written must not change that
    outcome.
    """
    sprint_index = state.get("current_sprint_index", 0)
    plan = state.get("milestone_plan")
    cycle = state.get("remediation")
    sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
    definition = sprints[sprint_index] if sprint_index < len(sprints) else None

    # The sprint plan's own goal for this index, ahead of the milestone's. Both
    # name a goal and only one of them names *this sprint's*: a milestone plan
    # is re-stored on every revision, and the lead is free to restate the goal
    # each time - so after a sprint is sent back, `selected_sprint_goal`
    # describes the latest revision rather than the sprint being summarised.
    #
    # Measured on one run's `sprint_1_summary.md`, live. Its header read
    # "Wire filter button functionality and inline edit UI ...", which was the
    # third milestone plan's goal, while "Planned for This Sprint" underneath
    # correctly listed sprint 1's scope - create the project directory, build
    # index.html, style.css and the pure logic in app.js. The document
    # contradicted itself, and the goal it showed belonged to the next sprint.
    #
    # This is the rule `planned` below already follows for the same reason: what
    # the sprint promised is a question about the sprint plan.
    goal = (
        getattr(definition, "goal", "")
        or getattr(plan, "selected_sprint_goal", "")
        or "Unknown goal"
    )
    # What the sprint *promised*, from the plan - not what the milestone chose
    # to delegate. "Features planned for the sprint" is a question about the
    # plan, and answering it from the delegated tasks answered a different one.
    planned = [str(item) for item in (getattr(definition, "in_scope", None) or [])]
    if not planned:
        planned = [str(item) for item in (getattr(definition, "acceptance_criteria", None) or [])]
    if not planned and goal:
        planned = [goal]

    # A task's title where the lead gave one - "Delete an item" rather than the
    # first line of an instruction to a specialist, which on one run read
    # "Review existing unit tests ..." under "Features Implemented".
    features = [
        (getattr(task, "title", "") or "").strip() or getattr(task, "task_description", str(task))
        for task in (getattr(plan, "delegated_tasks", None) or [])
    ]
    defects = [
        {
            "status": getattr(defect, "status", "open"),
            "description": getattr(defect, "description", ""),
            "owner": getattr(defect, "owner", "unassigned"),
        }
        for defect in (getattr(cycle, "defects", None) or [])
    ]

    recorded = [dict(entry) for entry in (state.get("sprint_attempts") or [])]
    already = [entry for entry in recorded if entry.get("sprint_index") == sprint_index]
    # Counts belong to this attempt alone, so the window opens where the last
    # recorded attempt closed. Summing every test run in the sprint would count
    # one suite once per round.
    since = max((str(entry.get("ended_at")) for entry in recorded if entry.get("ended_at")), default=None)

    cases = None
    try:
        from app.tools.sandbox import read_execution_ledger

        cases = count_test_cases(
            read_execution_ledger(state["repository"].root_path, limit=1000), since=since
        )
    except Exception:  # noqa: BLE001 - a summary without counts beats no summary
        logger.debug("Could not read test counts for the sprint summary", exc_info=True)

    # The Sprint Record's own sections, from what the workflow and the harness
    # recorded rather than from any agent's account. See `app.sprint.record`.
    record: dict[str, Any] = {}
    try:
        from app.observability.transcript import _run_id_from_config, read_transcript
        from app.sprint import record as sprint_record

        completed = status == "Completed"
        more = sprint_index + 1 < len(sprints)
        findings = list(state.get("sprint_findings") or [])
        run_id = _run_id_from_config()
        record = {
            "work_orders": sprint_record.work_order_outcomes(plan, state.get("specialist_outputs") or {}),
            "defect_log": sprint_record.defect_log(cycle),
            "findings": sprint_record.with_dispositions(findings, completed=completed, more_sprints=more),
            "carried_forward": sprint_record.carried_from(findings, sprint_index + 1) if completed else [],
            "lessons": sprint_record.lessons_from(
                read_transcript(run_id, {"tool_call", "tool_result"}) if run_id else [], since=since
            ),
        }
    except Exception:  # noqa: BLE001 - a summary without the record beats no summary
        logger.warning("Could not assemble the sprint record", exc_info=True)

    attempt = {
        "sprint_index": sprint_index,
        "number": len(already) + 1,
        "status": status,
        "reason": failure_reason or "",
        "cases": cases,
        "rounds": state.get("test_round", 0),
        "features": features,
        "defects": defects,
        **record,
        "ended_at": datetime.now(timezone.utc).isoformat(),
    }
    attempts = recorded + [attempt]

    try:
        _record_document(
            state,
            f"docs/sprint_{sprint_index + 1}_summary.md",
            render_sprint_summary(
                sprint_number=sprint_index + 1,
                total_sprints=len(sprints),
                goal=goal,
                planned=planned,
                attempts=[
                    entry for entry in attempts if entry.get("sprint_index") == sprint_index
                ],
            ),
        )
    except Exception:  # noqa: BLE001 - as above
        logger.warning("Could not render the sprint summary", exc_info=True)
    return {"sprint_attempts": attempts}


def _sprint_already_summarised(state: WorkflowGraphState) -> bool:
    """Whether the current sprint already has a completed attempt recorded.

    `complete_node` records the final sprint, because the run reaches it instead
    of `sprint_advance_node` and the last sprint therefore had no summary at
    all - a three-sprint plan produced two documents. With a sprint review
    switched on the run can pass through both, so the guard is here rather than
    a second copy of the reasoning in each node.
    """
    sprint_index = state.get("current_sprint_index", 0)
    return any(
        entry.get("sprint_index") == sprint_index and entry.get("status") == "Completed"
        for entry in (state.get("sprint_attempts") or [])
    )


def _record_review_document(
    state: WorkflowGraphState, review: Any, milestone_goal: str
) -> None:
    """Write `docs/milestone_review.md` from the reviewer's decision."""
    from app.agents.review_document import render_milestone_review

    _record_document(
        state, "docs/milestone_review.md", render_milestone_review(review, milestone_goal)
    )


#: Which stage produces each artifact the pipeline later reads. Used to send a
#: run back to the stage that owes the output rather than crashing downstream.
_PRODUCED_BY: dict[str, str] = {
    "product_intake": "product_manager",
    "tools_models": "tools_models",
    "stack_selection": "stack_selector",
    "technical_specification": "principal_architect",
    "sprint_plan": "scrum_master",
    "milestone_plan": "technical_lead",
}


def _as_text(value: Any) -> str:
    """One artifact as JSON text, whatever shape it arrived in."""
    if value is None:
        return ""
    if hasattr(value, "model_dump_json"):
        return value.model_dump_json(indent=2)
    return json.dumps(value, indent=2)


def _missing_upstream(state: WorkflowGraphState, *keys: str) -> dict[str, Any] | None:
    """Route back to whichever stage owes a missing artifact, or None if all present.

    A stage that answers in prose instead of returning its structured response
    leaves its artifact out of state, and every later stage that reads the key
    directly dies with a bare `KeyError` raised from inside LangGraph - naming
    neither the stage that failed nor anything to do about it.

    That is not a rare shape. Measured directly against this deployment's model,
    driving the product manager agent to completion twice with identical input:
    One run returned its structured response, the other wrote "# Product Intake
    Complete" as a message and returned nothing. Roughly half. Across a pipeline
    of ten sequential stages, something will land on it most runs.

    So this is treated as a retryable stage failure rather than an error: send
    the run back to the producer on a fresh conversation, bounded by the shared
    `structured_retries` budget, and only fail once that is spent.
    """
    for key in keys:
        if state.get(key) is not None:
            continue
        producer = _PRODUCED_BY.get(key)
        if producer is None:
            return _handing_on(
                stage="failed",
                error=f"The workflow needs '{key}' and no stage has produced it.",
            )
        retries = dict(state.get("structured_retries") or {})
        budget_key = f"{producer}:{key}"
        attempted = retries.get(budget_key, 0)
        if attempted < _max_structured_retries():
            retries[budget_key] = attempted + 1
            return _handing_on(stage=_owning_node(producer), structured_retries=retries)
        return _handing_on(
            stage="failed",
            error=(
                f"The {producer.replace('_', ' ')} stage finished without returning its "
                f"structured response, so '{key}' is missing and the run cannot "
                f"continue. It was re-run {attempted} time(s) on a fresh conversation "
                "and did the same each time. Any document it wrote is still in docs/."
            ),
        )
    return None


def _milestone_changes_requested(review: Any) -> str | None:
    """What the milestone reviewer wants changed, in words the lead can act on.

    `findings` is the field designed to carry this, but it is optional in the
    schema and a model may leave it empty while still voting
    `changes_required` - putting its whole argument in `acceptance_evidence`,
    which is required and so always gets written.

    Observed on one run: the reviewer returned `changes_required` with
    `findings == []` and three concrete complaints in `acceptance_evidence`
    (a root `package.json` whose test script was `exit 1`, duplicate installs
    in CI, `npm test` exiting 1). Joining an empty list produced `""`, and the
    technical lead was sent back to re-plan with a revision request containing
    nothing. It returned the same seven tasks three times, which was the only
    correct response to being told to change something unspecified.

    Returns None only when the reviewer wrote nothing anywhere, which is a
    reviewer that cannot be obeyed rather than a lead that will not comply.
    """
    findings = getattr(review, "findings", None) or []
    if findings:
        def lines(chosen: list[Any]) -> str:
            return "\n".join(
                f"[{f.severity}] {f.category}: {f.description} -> {f.required_remediation}"
                for f in chosen
            )

        # Only what gates is a required change. The revision request makes
        # every requested change a delegated task, and a suggestion made into
        # a task is new work in a sprint that is being sent back. Measured on
        # one run: sprint 1's revisions took on "consider encrypting stored
        # tasks" and "remove @playwright/test", the encryption lost its key on
        # every reload - a new major - and the third review ended the run.
        required = [f for f in findings if _severity_gates(getattr(f, "severity", ""))]
        noted = [f for f in findings if not _severity_gates(getattr(f, "severity", ""))]
        if required and noted:
            return (
                lines(required)
                + "\n\nAlso noted by the review, and NOT required in this revision - do not "
                "plan work for these unless a required change above needs it; they do not "
                "send the sprint back:\n" + lines(noted)
            )
        return lines(findings)

    evidence = (getattr(review, "acceptance_evidence", "") or "").strip()
    if evidence:
        return (
            "The milestone review requires changes. It recorded no structured "
            "findings, so this is its own account of what it checked and what "
            "it found wrong. Treat every problem named here as a required "
            "change:\n\n" + evidence
        )
    return None


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
        # Only blocking and major findings gate approval, so they are listed
        # first and marked as the ones that decide the outcome. Handing the
        # architect one flat list put a note about naming beside a missing
        # authorization model, and it spread its revision evenly across both.
        # Three rounds of that is how a run reaches the revision limit with the
        # blocking findings still open.
        gating = [f for f in review.findings if f.severity in _GATING_SEVERITIES]
        advisory = [f for f in review.findings if f.severity not in _GATING_SEVERITIES]

        if gating:
            changes.append(
                "MUST FIX - the review cannot pass while any of these remain. "
                "Address every one of them in this revision:"
            )
            changes.extend(_format_finding(finding) for finding in gating)
        if advisory:
            changes.append(
                "Optional improvements. Do not spend this revision on them if "
                "that risks leaving anything above unfixed:"
            )
            changes.extend(_format_finding(finding) for finding in advisory)

    # A blank comment is not a requested change. It reached the architect as a
    # revision request that asked for nothing - see
    # `_milestone_changes_requested` for where these came from.
    changes.extend(
        comment for comment in state.get("revision_comments", []) or [] if str(comment).strip()
    )
    return changes


def _review_enabled(state: WorkflowGraphState, review_point: str) -> bool:
    """Return whether the run configuration asked for this optional review.

    Reviews are opt-in. A run that never sets `review_policy` skips both gates
    entirely, which keeps the mandatory approval and architecture gates as the
    only things that can stop a default run.
    """
    return bool(state.get("review_policy", {}).get(review_point, False))


def _a_round_that_found_a_product_defect(defects: list[Any]) -> bool:
    """Whether this round found anything wrong with the *product*.

    A round that found only test defects is the suite settling down, and
    charging it against a budget meant for the product is how one run
    failed after three attempts with a working product: 43 of 43 unit tests
    passing, all five features the brief names built, and seven of its eleven
    defects in `ui.pw.test.mjs` - the Playwright suite the run had just
    written. Its entire second attempt was spent there and on nothing else.

    A defect with no files named counts against the budget. The question this
    asks is "do we know this was only the tests?", and an unlocated defect is
    not known to be anything - reading silence as good news is the mistake
    every other check in this codebase is written against.
    """
    from app.analysis.file_kinds import is_test

    if not defects:
        return True
    for defect in defects:
        files = list(getattr(defect, "affected_files", None) or [])
        if not files:
            return True
        if any(not is_test(str(name)) for name in files):
            return True
    return False


def _what_later_sprints_build(state: Any) -> str:
    """The goal, in-scope work and acceptance criteria of every sprint after this one.

    Never `out_of_scope`: that field names work in order to exclude it. See
    `app.analysis.integration_checks.planned_for_a_later_sprint`. "" on any
    failure, which leaves every finding in place.
    """
    try:
        plan = state.get("sprint_plan")
        sprints = list(getattr(plan, "sprints", None) or [])
        index = int(state.get("current_sprint_index", 0) or 0)
        parts: list[str] = []
        for sprint in sprints[index + 1:]:
            parts.append(str(getattr(sprint, "goal", "") or ""))
            parts.extend(str(item) for item in getattr(sprint, "in_scope", None) or ())
            parts.extend(str(item) for item in getattr(sprint, "acceptance_criteria", None) or ())
        return "\n".join(parts)
    except Exception:  # noqa: BLE001 - see docstring
        return ""


def _what_this_sprint_builds(state: Any) -> str:
    """The goal, in-scope work and acceptance criteria of the current sprint, or ""."""
    try:
        sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
        index = int(state.get("current_sprint_index", 0) or 0)
        if index >= len(sprints):
            return ""
        sprint = sprints[index]
        parts = [str(getattr(sprint, "goal", "") or "")]
        parts.extend(str(item) for item in getattr(sprint, "in_scope", None) or ())
        parts.extend(str(item) for item in getattr(sprint, "acceptance_criteria", None) or ())
        return "\n".join(parts)
    except Exception:  # noqa: BLE001 - "" leaves every finding in place
        return ""


def _this_sprint_s_scope_for_review(state: Any) -> str:
    """This sprint's scope as the milestone reviewer reads it, or "" without a plan."""
    try:
        sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
        index = int(state.get("current_sprint_index", 0) or 0)
        if index >= len(sprints):
            return ""
        sprint = sprints[index]
        lines = [f"Sprint {index + 1} of {len(sprints)}: {getattr(sprint, 'goal', '')}"]
        in_scope = [str(item) for item in getattr(sprint, "in_scope", None) or ()]
        deferred = [str(item) for item in getattr(sprint, "out_of_scope", None) or ()]
        if in_scope:
            lines += ["In scope:", *(f"- {item}" for item in in_scope)]
        if deferred:
            lines += ["Deferred by the plan, not part of this sprint:", *(f"- {item}" for item in deferred)]
        later = [
            f"- Sprint {number}: {getattr(later_sprint, 'goal', '')}"
            for number, later_sprint in enumerate(sprints[index + 1:], index + 2)
        ]
        if later:
            lines += ["Later sprints:", *later]
        return "\n".join(lines)
    except Exception:  # noqa: BLE001 - a review without the scope is the old review
        return ""


def _findings_a_later_sprint_builds(review: Any, state: Any) -> Any:
    """`review` with each gating finding about later sprints' work made minor.

    Kept, not dropped: the finding stays in the review, the document and the
    Sprint Record, where a non-gating finding of an accepted sprint is carried
    to the next sprint's lead. It only stops being a reason to send this sprint
    back to build what the plan put in a later one. See
    `app.analysis.integration_checks.later_sprint_work_in`; the last sprint's
    whole-brief check (`_a_brief_requirement_the_run_never_built`) still
    catches work no sprint builds.
    """
    try:
        from app.analysis.integration_checks import later_sprint_files_in, later_sprint_work_in

        later = _what_later_sprints_build(state)
        if not later:
            return review
        now = _what_this_sprint_builds(state)
        findings = []
        moved = 0
        for finding in getattr(review, "findings", None) or []:
            description = getattr(finding, "description", "")
            actions = (
                later_sprint_work_in(description, now, later)
                or later_sprint_files_in(description, now, later)
                if _severity_gates(getattr(finding, "severity", ""))
                else []
            )
            if actions:
                moved += 1
                finding = finding.model_copy(update={
                    "severity": "minor",
                    "description": f"Planned for a later sprint ({', '.join(actions)}): {finding.description}",
                })
            findings.append(finding)
        if not moved:
            return review
        logger.warning(
            "Milestone review raised %d gating finding(s) about work a later sprint "
            "builds; recorded as minor so this sprint is not sent back to build it",
            moved,
        )
        return review.model_copy(update={"findings": findings})
    except Exception:  # noqa: BLE001 - the review as written stands
        return review


def _a_brief_requirement_the_run_never_built(state: Any) -> str:
    """What the brief asked for that the product still does not do, or "".

    Asked once, at the last sprint, because it is the only point where the
    whole brief is the question. Every milestone review before it is scoped to
    its own milestone, and deferring a requirement out of one is legitimate -
    a sprint plan exists to do exactly that. One run's first review put
    both `edit` and the filter bar into later sprints, correctly.

    What nothing did was ask again at the end. `complete_node` returns
    `{"stage": "complete"}` and nothing else, so a requirement deferred out of
    every milestone in turn was never checked, and three completed runs
    shipped with no way to edit a task: three runs.

    Reads the operator's brief rather than the run's documents, for the reason
    `_actions_the_brief_requires` gives: a run that redefines a requirement
    removes it from every document downstream, after which a check that reads
    those documents agrees with the run.

    Returns "" on any failure. A gate that cannot run must not stop a run that
    has otherwise passed everything.
    """
    try:
        from pathlib import Path as _Path

        from app.analysis.integration_checks import (
            _a_required_action_nothing_implements,
            _source_files,
        )

        brief = getattr(state.get("document"), "text", "") or ""
        if not brief.strip():
            return ""
        root = _Path(state["repository"].root_path).resolve()
        problems = _a_required_action_nothing_implements(
            _source_files(root), root, brief
        )
    except Exception:  # noqa: BLE001 - never fail a finished run over this gate
        logger.warning("Could not check the brief at the last sprint", exc_info=True)
        return ""
    if not problems:
        return ""
    return (
        "MUST FIX - the last sprint is accepted and the brief is not "
        "delivered. This is the final check against the operator's own brief "
        "rather than this run's restatement of it, and the run does not "
        "finish until it passes:\n" + "\n".join(f"- {problem}" for problem in problems)
    )


def _the_files_this_milestone_changed(
    state: WorkflowGraphState, outputs: Mapping[str, Any]
) -> list[str]:
    """Every product file this milestone touched, reported or not.

    `changed_files` comes from each specialist's structured response, and a stage
    under-reports it. Measured across the 28 current-generation runs: 82 stages
    wrote a file and did not name it - every role, about three per run.

        One run  test_round_0         wrote 5 files, reported none
        one run  specialist_ui_ux_1   wrote app.js, index.html,
                                           package.json, server.mjs; reported app.js
        one run  specialist_ui_ux_0   wrote app.js, app.test.mjs,
                                           package.json; reported app.test.mjs

    Three stages read that list - the test round, the security review and the
    milestone review - and all three were told "Files changed in this milestone"
    from it. A round can be told nothing changed after five files did.

    Git is the record that cannot under-report. The previous sprint's tag is the
    boundary, and `git diff --name-only` against it includes uncommitted work,
    which is what a sprint in progress has. `docs/` is dropped: those are the
    workflow's own documents, rendered from structured responses, and naming
    `docs/milestone_plan.md` as a file this milestone changed sends a reviewer to
    read the plan as if it were product code.

    Falls back to the reported list alone in the first sprint, which has no
    earlier tag and where everything is new, and on any failure - a list that
    cannot be gathered must never be the thing that fails a stage.
    """
    reported = {name for output in outputs.values() for name in output.changed_files}
    try:
        from app.tools.version_control import changed_since, is_repository

        index = int(state.get("current_sprint_index", 0) or 0)
        root = state["repository"].root_path
        if index >= 1 and is_repository(root):
            observed = {
                name.strip()
                for name in changed_since(root, f"sprint-{index}")
                if name.strip() and not name.strip().startswith("docs/")
            }
            reported |= observed
    except Exception:  # noqa: BLE001 - evidence is best-effort, never fatal
        logger.warning("Could not read what this sprint changed", exc_info=True)
    return sorted(reported)


def _the_suite_the_ledger_measured(state: WorkflowGraphState) -> dict[str, int] | None:
    """The last test run this sprint recorded, from the execution ledger.

    The same window and the same reading `_record_sprint_summary` uses, so the
    number this gate acts on and the number the sprint summary prints cannot
    disagree. Returns None when no runner reported counts, which is not evidence
    of anything and must not gate.
    """
    try:
        from app.tools.sandbox import read_execution_ledger

        recorded = [dict(entry) for entry in (state.get("sprint_attempts") or [])]
        since = max(
            (str(entry.get("ended_at")) for entry in recorded if entry.get("ended_at")),
            default=None,
        )
        entries = read_execution_ledger(state["repository"].root_path, limit=1000)
        counts = count_test_cases(entries, since=since)
        if counts is None:
            return None
        # The exit code of the same run, because the counts alone can say a suite
        # passed when the command did not - see `a_suite_that_did_not_pass`.
        entry = last_test_run(entries, since=since) or {}
        code = entry.get("returncode")
        # The ledger's own field name, so `a_suite_that_did_not_pass` reads one
        # spelling wherever it is called from.
        return {**counts, "returncode": int(code) if isinstance(code, int) else 0}
    except Exception:  # noqa: BLE001 - a gate that cannot read must not stop a run
        logger.warning("Could not read the measured suite for this sprint", exc_info=True)
        return None


def _a_red_suite_the_review_called_green(state: WorkflowGraphState) -> str:
    """Why this sprint cannot be accepted on the review's word, or "".

    The milestone review decides whether a sprint is delivered, and it decides
    it by reading. The harness does not have to read: every command whose runner
    printed a summary line is in the execution ledger with its own `tests`,
    `passed` and `failed`.

    Measured on one run's third sprint. The ledger recorded `npm test` -
    the project's own gating command - eight times in the four minutes before
    the review:

        10:23:50  npm test   tests=21  passed=15  failed=6
        10:24:57  npm test   tests=21  passed=15  failed=6
        ...
        10:26:56  npm test   tests=21  passed=15  failed=6

    and the review returned:

        Executed npm run test successfully; all tests passed.
        No blocking or major violations found.
        Status: accepted

    Three minor findings, none of them the six failures, and the sprint was
    marked Completed. `app.analysis.verification_claims` was written for this
    exact fault one layer down - "do not claim to have done what was not done" -
    and checks a specialist's claimed commands against the ledger. Nothing
    checked the reviewer's.

    A reviewer may legitimately accept a sprint with known failures deferred.
    What it may not do is accept one while reporting that the suite passed, and
    the remedy names the numbers rather than arguing about judgement: the lead
    is sent the measurement.

    Nothing here names a language or a runner. The counts come from
    `sandbox._RUNNER_TOTALS`, which reads TAP, jest, vitest, pytest, cargo and
    go, and a sprint built in something it cannot parse reports no counts and is
    not gated - the same rule `_record_sprint_summary` follows.
    """
    cases = _the_suite_the_ledger_measured(state)
    if not cases or not a_suite_that_did_not_pass(cases):
        return ""
    # A failure the counts cannot show. A composite command - `npm test` chaining
    # `node --test` and `playwright test` - has its first runner's summary parsed,
    # so a later runner's failure leaves `failed: 0` beside a non-zero exit code.
    # Measured on one run: five ledger entries reading 27 passed, 0 failed,
    # returncode 1. Reading `failed` alone was silent on every one of them.
    if cases.get("failed", 0) <= 0:
        return (
            f"MUST FIX - the command this sprint's suite is measured by failed. "
            f"The execution ledger's last recorded test run exited "
            f"{cases.get('returncode')} while reporting {cases['tests']} case(s), "
            f"{cases['passed']} passed and 0 failed. Those two cannot both be the "
            "whole story: a test command that chains runners has only the first "
            "one's summary counted, so a later runner failed and its cases were "
            "never added up. Run the parts separately to see which, fix it, and do "
            "not report this suite as passing - the exit code is what a CI system "
            "will read."
        )
    return (
        f"MUST FIX - the suite this sprint is measured by is failing. The "
        f"execution ledger's last recorded test run is {cases['tests']} case(s), "
        f"{cases['passed']} passed and {cases['failed']} failed. That is the "
        "measurement, not a reading of the code, and it is the number the sprint "
        "summary reports and every later stage inherits. A sprint accepted over a "
        "failing suite is the one outcome no later gate can recover from, because "
        "every stage after it reads the pass as evidence the product works. Fix "
        "the failing cases, or if they cannot be fixed in this sprint, say so as "
        "a blocking finding naming them - do not report the suite as passing."
    )


def _escalate_to_a_human(
    state: WorkflowGraphState, error: str, **fields: Any
) -> dict[str, Any]:
    """Park the run for a human, or fail it if no human is watching.

    `_run_review_gate` opens a review session and pauses unconditionally - it
    never asks whether that review is switched on. Two escalations routed
    straight to it: a milestone review that exhausted its revisions, and a
    sprint that exhausted its remediation attempts. Both are the right place to
    want a person, and neither checked whether there is one.

    A run with the default `review_policy` of `{}` has opted out of both human
    gates. Sending it to one leaves it `waiting_for_review` with nobody coming -
    not failed, not progressing, and holding the worker. Measured on
    one run, which sat in `awaiting_user_review:sprint` with
    `review_policy` empty.

    So: park it when a reviewer was asked for, and otherwise fail with the
    message that says what is unresolved, which is what an unattended run needs
    and what it already produces everywhere else.
    """
    if _review_enabled(state, SPRINT_REVIEW):
        return _handing_on(stage="user_review_sprint", **fields)
    return _handing_on(stage="failed", error=error, **fields)


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
        if _hand_back(update, "product_intake"):
            return update

        # The brief's own constraints, put back before anything is rendered
        # from this. Every later stage reads the intake; none reads the brief.
        update["product_intake"] = with_the_constraints_the_brief_states(
            update["product_intake"], getattr(state.get("document"), "text", "") or ""
        )
        # Its acceptance criteria too, in the brief's words: the measures are
        # what every later stage checks itself against.
        update["product_intake"] = with_the_measures_the_brief_states(
            update["product_intake"], getattr(state.get("document"), "text", "") or ""
        )
        # And no contradiction between its own lists: a capability a success
        # measure names is a workflow, whatever the workflow list left out,
        # and a deferral that touches what the brief requires says so.
        update["product_intake"] = with_the_workflows_its_measures_require(update["product_intake"])
        update["product_intake"] = with_what_the_brief_requires_marked_in_deferred_scope(
            update["product_intake"], getattr(state.get("document"), "text", "") or ""
        )

        _record_document(
            state,
            "docs/product_intake.md",
            render_document("product_intake", o=update["product_intake"]),
        )
        # The project directory, named once from the product, so no stage has
        # to derive it and none looks for it before it exists.
        from app.tools.repository import pin_the_directory_the_product_names

        pin_the_directory_the_product_names(
            state["repository"].root_path, getattr(update["product_intake"], "product_name", "")
        )
        
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
        intake = state.get("product_intake")
        if intake is None:
            # Send it back to the stage that owes the output, on a fresh
            # conversation, rather than failing here. Resuming re-enters *this*
            # node, where the intake is still missing - so telling the operator
            # to resume, as the first version of this guard did, was advice that
            # could not work. Measured on one run: resumed once, failed
            # again in the same place.
            retries = dict(state.get("structured_retries") or {})
            key = "product_manager:intake"
            attempted = retries.get(key, 0)
            if attempted < _max_structured_retries():
                retries[key] = attempted + 1
                return _handing_on(stage="product_manager", structured_retries=retries)
            # The stage before this one finished without returning its
            # structured response - on one run the product manager wrote
            # `docs/product_intake.md`, then reported "Product intake complete.
            # Here is the structured summary:" as prose. Reading the key
            # directly turned that into `KeyError: 'product_intake'` from deep
            # inside LangGraph, which says nothing about which stage failed or
            # what to do. Every sibling condition in this module returns a
            # recoverable error instead.
            return _handing_on(
                stage="failed",
                error=(
                    "The product manager finished without returning its structured "
                    "response, so there is no product intake for the next stage to "
                    f"read. It was re-run {attempted} time(s) on a fresh conversation "
                    "and did the same thing each time. Its document may still be in "
                    "docs/. A model that writes the answer as prose instead of "
                    "returning it through the response schema usually needs its "
                    "reasoning settings checked - see Settings."
                ),
            )
        intake_text = (
            intake.model_dump_json(indent=2)
            if hasattr(intake, "model_dump_json")
            else json.dumps(intake, indent=2)
        )
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
        if not _hand_back(update, "tools_models"):
            _record_document(
                state,
                "docs/tools_and_models.md",
                render_document("tools_and_models", o=update["tools_models"]),
            )
            # Pin every language the stack names, so the sandbox can open the
            # right toolchain to every role that writes code. The allowlist
            # cannot ask this stage directly - it is handed a role name and a
            # workspace - so the decision is recorded in the workspace the way
            # the project directory already is.
            #
            # Every field, not just `language`. A full-stack product names a
            # backend language and a frontend framework, and passing only the
            # first pinned `go` for a Go/TypeScript product - leaving every
            # role without `tsc`. `frontend_framework` was filled by the stack
            # selector, shown to specialists in prose, and reached no
            # allowlist, no timeout and no analyser.
            try:
                from app.tools.sandbox import pin_project_stack

                stack = getattr(update["tools_models"], "technology_stack", None)
                named = [
                    str(getattr(stack, field, "") or "")
                    for field in ("language", "frontend_framework", "framework")
                ] if stack else []
                if any(named):
                    pin_project_stack(state["repository"].root_path, *named)
            except Exception:  # noqa: BLE001 - a run must not fail over a pin
                logger.warning("Could not pin the project stack", exc_info=True)
        return update

    def stack_selector_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        agent = create_stack_selector_agent(model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
        # The brief's own constraints, quoted, not a model's summary of them.
        # This stage was given `product_intake` and `tools_models` and nothing
        # else, and on one run `ProductManagerOutput.constraints` came
        # back empty - so "No external dependencies beyond basic HTML/CSS/JS"
        # never reached the stage that picked Express. See
        # `app.agents.brief_constraints`.
        from app.agents.brief_constraints import constraints_note

        document = state.get("document")
        constraints = constraints_note(getattr(document, "text", "") or "")
        request = {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"{constraints}"
                        f"Product Intake: {state['product_intake']}\n"
                        f"Tools: {state.get('tools_models')}"
                    ),
                }
            ]
        }
        update = _run_gated_agent(
            state,
            config,
            stage_name="stack_selector",
            agent=agent,
            initial_request=request,
            output_key="stack_selection",
            next_stage="principal_architect",
        )
        if _hand_back(update, "stack_selection"):
            return update

        # The prompt tells this stage, in capitals, that a product with a user
        # interface needs both a logic runner and a browser runner and must name
        # both. One run named only `node --test`, for a brief asking for a
        # "web-based interface with HTML/CSS/JavaScript", and justified it with
        # "manual browser verification" - which the same prompt calls impossible
        # twice, there being no display and nobody to look at one. Its
        # specialists installed Playwright anyway, correctly, and the stack
        # document then disagreed with the product: a package the stack did not
        # name is a blocking finding. Enforced here because saying it was not
        # enough, and because the corrected value is derivable from the answer
        # the stage just gave.
        chosen = update.get("stack_selection")
        stack = getattr(chosen, "technology_stack", None)
        corrected = the_browser_runner_this_stack_forgot(stack)
        if corrected is not None:
            logger.warning(
                "Stack selection named '%s' for a product that runs in a "
                "browser; recording '%s' so the stack matches what the "
                "environment provides",
                getattr(stack, "testing_framework", ""), corrected,
            )
            update["stack_selection"] = chosen.model_copy(
                update={
                    "technology_stack": stack.model_copy(
                        update={"testing_framework": corrected}
                    )
                }
            )

        # Rendered from the decision, like every other document the workflow
        # keeps. On one run this stage still wrote its own: it printed the
        # selection into the conversation, wrote `docs/technology_stack.md`,
        # printed it again, wrote again - five identical writes, and the repeat
        # guard ended the run at stage three. The same shape had already cost
        # earlier runs their technical lead and their architecture reviewer,
        # in the one stage that had not been converted.
        _record_document(
            state,
            "docs/technology_stack.md",
            render_document("technology_stack", o=update["stack_selection"]),
        )
        return update

    def principal_architect_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        missing = _missing_upstream(state, "product_intake", "tools_models")
        if missing is not None:
            return missing
        agent = create_principal_architect_agent(model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)

        # A rejected specification must come back with the reasons attached,
        # otherwise the architect reproduces the version that was rejected.
        required_changes = _collect_required_changes(state)
        previous_specification = state.get("technical_specification")
        if required_changes and previous_specification is not None:
            request = build_architecture_revision_request(
                previous_specification_text=previous_specification.model_dump_json(indent=2) if hasattr(previous_specification, "model_dump_json") else __import__("json").dumps(previous_specification, indent=2),
                required_changes=required_changes,
                product_intake_text=_as_text(state.get("product_intake")),
                tools_and_models_text=_as_text(state.get("tools_models")),
                stack_selection_text=_as_text(state.get("stack_selection")),
                repository=state["repository"],
                document=state["document"],
            )
        else:
            request = build_architecture_request(
                _as_text(state.get("product_intake")),
                _as_text(state.get("tools_models")),
                _as_text(state.get("stack_selection")),
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
        if not _hand_back(update, "technical_specification"):
            # Consumed: the revision request above already delivered them, so
            # a later rerun must not re-apply stale comments.
            update["revision_comments"] = []

            # Rendered from the decision the pipeline routes on, so the
            # document and the structured answer cannot disagree. See
            # `app.agents.specification_document`.
            _record_document(
                state,
                "docs/technical_specification.md",
                render_specification(
                    update["technical_specification"],
                    getattr(state.get("product_intake"), "product_name", ""),
                ),
            )

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
                # Testing nobody here can carry out: a person's check, or an
                # assertion that exits 0 whatever it finds. Same bounded repair
                # path, same reason - the architect can fix it in one pass, and
                # a review cycle would only relay it.
                from app.agents.principal_architect import testing_nobody_can_run

                unrunnable = testing_nobody_can_run(update.get("technical_specification"))
                if unrunnable and repairs < MAX_SPECIFICATION_REPAIRS:
                    update["specification_repair_count"] = repairs + 1
                    update["stage"] = "principal_architect"
                    update["revision_comments"] = [
                        "The `testing` section plans checks nothing in this environment "
                        "can carry out:\n"
                        + "\n".join(f"- {entry}" for entry in unrunnable)
                        + "\nNo person watches the workspace and there is no display, so a "
                        "manual or visual check never happens, and an assertion written "
                        "to a console or log exits 0 whatever it finds. Every check must be "
                        "an automated test run by the runner the technology stack names, "
                        "which fails the command when a test fails. Return the whole "
                        "specification with `testing` corrected; change nothing else."
                    ]
                else:
                    update["specification_repair_count"] = 0
        return update

    def architecture_review_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        missing = _missing_upstream(state, "technical_specification")
        if missing is not None:
            return missing
        agent = create_architecture_reviewer_agent(model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
        spec_text = _as_text(state.get("technical_specification"))
        previous_review = state.get("architecture_review")
        request = build_architecture_review_request(
            spec_text,
            state["repository"].root_path,
            getattr(state.get("document"), "text", "") or "",
            earlier=list(
                (previous_review.get("findings") if isinstance(previous_review, dict) else getattr(previous_review, "findings", None))
                or []
            ),
            revision=state.get("architecture_revision_count", 0),
        )
        update = _run_gated_agent(
            state,
            config,
            stage_name="architecture_review",
            agent=agent,
            initial_request=request,
            output_key="architecture_review",
            next_stage="scrum_master",  # placeholder; always overridden below
        )
        if _hand_back(update, "architecture_review"):
            return update

        review: ArchitectureReviewOutput = update["architecture_review"]

        coverage_finding = _a_success_measure_the_specification_drops(state, spec_text)
        if coverage_finding is not None:
            review = review.model_copy(
                update={"findings": [*review.findings, coverage_finding], "status": "changes_required"}
            )
            update["architecture_review"] = review
            update["specification_coverage_checked"] = True

        review = _a_pass_over_its_own_findings(
            review, state["repository"].root_path, "approved", "architecture_review"
        )
        update["architecture_review"] = review

        # Rendered from the decision, not written by the reviewer as a second
        # copy that can disagree with it. See `app.agents.review_document`.
        _record_document(state, "docs/architecture_review.md", render_architecture_review(review))

        blocking = _findings_that_block(review, state["repository"].root_path)
        if review.status != "approved" and review.findings and not blocking:
            # Findings, but none of them gate. See `_findings_that_block`.
            logger.info(
                "Stage architecture_review asked for changes over %d finding(s), none "
                "above %s; recording them and continuing",
                len(review.findings),
                "/".join(sorted(_GATING_SEVERITIES)),
            )

        if review.status == "approved" or (review.findings and not blocking):
            # The mandatory gate passed. Only now may an optional human review
            # session run; it can never substitute for this gate.
            update["stage"] = (
                "user_review_specification" if _review_enabled(state, SPECIFICATION_REVIEW) else "scrum_master"
            )
        else:
            revision_count = state.get("architecture_revision_count", 0) + 1
            update["architecture_revision_count"] = revision_count
            if revision_count >= MAX_ARCHITECTURE_REVISIONS:
                # Name what is still wrong. The bare "reached the limit" message
                # told a reader that the run died but not what to do about it,
                # even though the reviewer had just written the answer down.
                outstanding = [_format_finding(f) for f in blocking]
                detail = (
                    "\n\nStill unresolved:\n" + "\n".join(f"- {line}" for line in outstanding)
                    if outstanding
                    else ""
                )
                update["stage"] = "failed"
                update["error"] = (
                    f"The architecture reviewer still rejected the specification after "
                    f"{MAX_ARCHITECTURE_REVISIONS} revisions, so the run stopped rather than "
                    f"revising indefinitely. The specification written so far is kept in "
                    f"docs/. Fix these points and resume, or raise "
                    f"MAX_ARCHITECTURE_REVISIONS if the reviewer is simply being strict."
                    f"{detail}"
                )
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
        missing = _missing_upstream(state, "technical_specification")
        if missing is not None:
            return missing
        agent = create_scrum_master_agent(model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
        spec_text = _as_text(state.get("technical_specification"))
        measures = [
            str(m) for m in (getattr(state.get("product_intake"), "success_measures", None) or []) if str(m).strip()
        ]
        gaps_already_asked_about = list(state.get("sprint_plan_gaps") or [])
        request = build_sprint_planning_request(
            spec_text,
            state["repository"].root_path,
            success_measures=measures,
            gaps=gaps_already_asked_about,
        )
        update = _run_gated_agent(
            state,
            config,
            stage_name="scrum_master",
            agent=agent,
            initial_request=request,
            output_key="sprint_plan",
            next_stage="technical_lead",
        )
        if not _hand_back(update, "sprint_plan"):
            unnamed = capabilities_the_plan_never_names(update["sprint_plan"], measures)
            unassigned = unaccounted_success_measures(update["sprint_plan"], measures)
            missing = [
                {"measure": n, "missing": unnamed.get(n, [])}
                for n in sorted(set(unassigned) | set(unnamed))
            ]
            if missing and not gaps_already_asked_about:
                # Once. A plan that omits a success measure is caught at the
                # milestone review otherwise, a full build cycle later and at
                # the cost of one of three revisions; a second planning call is
                # far cheaper. A second omission is let through with a warning
                # rather than looped on - the review is still there behind it.
                logger.warning(
                    "Sprint plan left success measures %s unassigned; asking once more", missing
                )
                return _handing_on(stage="scrum_master", sprint_plan_gaps=missing)
            if missing:
                logger.warning(
                    "Sprint plan still leaves success measures %s unassigned after one "
                    "re-plan; continuing, and the milestone review will judge it", missing
                )
            update["sprint_plan_gaps"] = []
            update["current_sprint_index"] = 0
            _record_document(
                state,
                "docs/sprint_plan.md",
                render_document("sprint_plan", o=update["sprint_plan"]),
            )
        return update

    def technical_lead_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        missing = _missing_upstream(state, "sprint_plan")
        if missing is not None:
            return missing
        agent = create_technical_lead_agent(model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
        plan_text = _as_text(state.get("sprint_plan"))
        sprint_index = state.get("current_sprint_index", 0)
        sprints = state["sprint_plan"].sprints
        current_goal = sprints[sprint_index].goal if sprints and sprint_index < len(sprints) else ""

        # A sprint review that requested changes re-enters here. Reuse the
        # shared revision prompt so the lead sees its previous milestone plan
        # alongside the comments, rather than re-planning from scratch.
        # Blank comments are dropped before the truthiness test: `[""]` is a
        # truthy list, so a revision request carrying one empty string used to
        # send the lead down the revising branch with nothing to revise.
        revision_comments = [
            comment for comment in state.get("revision_comments", []) or [] if str(comment).strip()
        ]
        previous_milestone = state.get("milestone_plan")
        revising = bool(revision_comments) and previous_milestone is not None
        if revising:
            request = build_milestone_revision_request(
                previous_milestone.model_dump_json(indent=2), revision_comments
            )
        else:
            request = build_milestone_planning_request(
                plan_text, current_goal, state["repository"].root_path,
                specification=state.get("technical_specification"),
                carried_forward=state.get("carried_forward") or [],
                lessons=state.get("lessons") or [],
            )
        # The previous answer was not ready to hand out: say exactly why, with
        # the plan it was, so this attempt fixes it rather than starting over.
        unready = [str(p) for p in state.get("work_order_problems") or [] if str(p).strip()]
        if unready:
            from app.analysis.work_orders import readiness_feedback

            request["messages"][-1]["content"] += (
                readiness_feedback(unready)
                + (f"\n\nThe plan that was sent back:\n{state.get('unready_plan')}" if state.get("unready_plan") else "")
            )
        update = _run_gated_agent(
            state,
            config,
            stage_name="technical_lead",
            agent=agent,
            initial_request=request,
            output_key="milestone_plan",
            next_stage="specialist_dispatch",
        )
        if _hand_back(update, "milestone_plan"):
            return update

        # Pinned before the readiness check, which checks each work order's files
        # against it. In parallel mode the specialists all start before a file
        # exists, and the directory was pinned by whichever wrote first. See
        # `pin_the_directory_a_plan_names`.
        try:
            from app.tools.repository import pin_the_directory_a_plan_names

            pin_the_directory_a_plan_names(
                state["repository"].root_path, update["milestone_plan"].model_dump_json()
            )
        except Exception:  # noqa: BLE001 - the first write still pins it
            logger.warning("Could not pin the project directory from the plan", exc_info=True)

        # The definition of ready: every work order complete enough for a
        # specialist who knows nothing but its brief. See `app.analysis.work_orders`.
        from app.analysis.work_orders import (
            readiness_problems,
            with_paths_inside_the_project,
            with_test_cases_from_its_criteria,
        )

        update["milestone_plan"] = with_test_cases_from_its_criteria(
            with_paths_inside_the_project(update["milestone_plan"], state["repository"].root_path)
        )
        problems = readiness_problems(
            update["milestone_plan"],
            state["repository"].root_path,
            carried_forward=[] if revising else (state.get("carried_forward") or []),
        )
        if problems:
            retries = dict(state.get("structured_retries") or {})
            key = _READINESS_RETRIES
            attempted = retries.get(key, 0)
            best_plan, best_problems = _the_better_plan(
                (update["milestone_plan"], problems),
                (state.get("best_unready_plan") or "", list(state.get("best_unready_problems") or [])),
            )
            if attempted < _max_structured_retries():
                retries[key] = attempted + 1
                logger.warning(
                    "Milestone plan is not ready to hand out (%d problem(s)); sending it "
                    "back to the lead (attempt %d of %d): %s",
                    len(problems), attempted + 2, _max_structured_retries() + 1,
                    "; ".join(p[:80] for p in problems[:3]),
                )
                return _handing_on(
                    stage="technical_lead",
                    structured_retries=retries,
                    revision_comments=revision_comments,
                    work_order_problems=problems,
                    unready_plan=update["milestone_plan"].model_dump_json(indent=2),
                    best_unready_plan=best_plan.model_dump_json(),
                    best_unready_problems=best_problems,
                )
            if best_plan is not update["milestone_plan"]:
                logger.warning(
                    "The last attempt was worse than an earlier one (%d problem(s) and "
                    "%d work order(s), against %d and %d); dispatching the earlier plan",
                    len(problems), len(update["milestone_plan"].delegated_tasks or []),
                    len(best_problems), len(best_plan.delegated_tasks or []),
                )
                update["milestone_plan"], problems = best_plan, best_problems
            logger.warning(
                "Milestone plan still not ready after %d attempts; dispatching it with "
                "the problems noted: %s", attempted + 1, "; ".join(p[:80] for p in problems[:3]),
            )
            plan = update["milestone_plan"]
            update["milestone_plan"] = plan.model_copy(update={
                "integration_notes": list(plan.integration_notes) + [
                    f"Not ready when dispatched: {problem}" for problem in problems
                ]
            })
        update["work_order_problems"] = []
        update["unready_plan"] = ""
        update["best_unready_plan"] = ""
        update["best_unready_problems"] = []
        # A budget per plan, not per run. The success path clears the stage's
        # own key and nothing cleared this one, so sprint 1's three attempts
        # were still counted when sprint 2's plan arrived: measured on one run,
        # sprint 2's first unready plan was dispatched as "still not ready after
        # 3 attempts" without being sent back once.
        update["structured_retries"] = {
            key: count
            for key, count in (update.get("structured_retries", state.get("structured_retries")) or {}).items()
            if key != _READINESS_RETRIES
        }

        # Before it is written down or dispatched: a command the plan tells a
        # specialist to run, which the sandbox will refuse, is noted on the task.
        # See `app.analysis.planned_commands`.
        from app.analysis.planned_commands import with_refused_commands_noted

        update["milestone_plan"] = with_refused_commands_noted(
            update["milestone_plan"], state["repository"].root_path
        )

        # Which stage owns each file the work orders list, so a specialist
        # writing another work order's file is told whose it is. A file two
        # work orders list has no single owner and is left open.
        from app.tools.repository import record_work_order_files

        declared: dict[str, list[str]] = {}
        for index, task in enumerate(getattr(update["milestone_plan"], "delegated_tasks", None) or []):
            for path in getattr(task, "files", None) or []:
                declared.setdefault(str(path), []).append(_specialist_stage_name(task, index))
        record_work_order_files(
            state["repository"].root_path,
            {path: stages[0] for path, stages in declared.items() if len(set(stages)) == 1},
        )

        _record_document(
            state,
            "docs/milestone_plan.md",
            render_document("milestone_plan", o=update["milestone_plan"]),
        )

        milestone: MilestonePlanOutput = update["milestone_plan"]

        # A revision that assigns nothing is a revision that changes nothing.
        # The lead can satisfy "address every requested change" by writing it
        # into `integration_notes`, which no specialist is given - so the plan
        # reads as if the change were handled while the file stays untouched.
        unassigned = unassigned_review_changes(
            milestone, revising=revising, previous=previous_milestone
        )
        if unassigned:
            # Retry on a fresh conversation before giving up. Omitting the
            # assignments once is a lapse, not an inability - and failing the
            # whole run for it throws away every stage that came before. The
            # budget is shared with the structured-response retry because both
            # are the same remedy: abandon this conversation and ask again.
            retries = dict(state.get("structured_retries") or {})
            key = _ASSIGNMENT_RETRIES
            attempted = retries.get(key, 0)
            if attempted < _max_structured_retries():
                retries[key] = attempted + 1
                logger.warning(
                    "Milestone revision assigned no task to the requested changes; "
                    "re-planning on a fresh conversation (attempt %d of %d)",
                    attempted + 2, _max_structured_retries() + 1,
                )
                return _handing_on(
                    stage="technical_lead",
                    structured_retries=retries,
                    revision_comments=revision_comments,
                )
            return _handing_on(
                stage="failed",
                error=(
                    f"{unassigned}\n\nThis was tried {attempted + 1} times, each on a "
                    "fresh conversation."
                ),
            )

        # The same per-plan budget as the readiness retries above.
        update["structured_retries"] = {
            key: count
            for key, count in (update.get("structured_retries", state.get("structured_retries")) or {}).items()
            if key != _ASSIGNMENT_RETRIES
        }
        update["remediation"] = start_remediation(milestone.selected_sprint_goal, max_attempts=MAX_REMEDIATION_ATTEMPTS)
        update["specialist_task_index"] = 0
        # The parallel twin of the line above, and for the same reason: a plan
        # just stored has had no specialist run against it. Linear dispatch
        # counts through the tasks, so zeroing the counter is enough; the
        # parallel router instead subtracts the stage names that already produced
        # output, and a stage name is `specialist_{role}_{index}` - it carries no
        # plan identity. Leaving the previous plan's outputs in place therefore
        # told the router that this plan's tasks were done.
        #
        # Measured on one run, whose three plans produced the identical
        # names `specialist_ui_ux_0`, `specialist_backend_1`,
        # `specialist_testing_2`, because the lead assigns those roles in that
        # order every time. Sprint 1 ran all three; the two revisions the
        # milestone review asked for fanned out nothing and reached a test round
        # 174ms after the plan was stored. One of those plans was 16,959 output
        # tokens, and the work it described was eventually done by nine
        # `defect_fix` stages instead.
        #
        # Here rather than on the reviewer's `changes_required` edge, which is
        # where the omission was: its sibling `blocked` branch cleared this and
        # it did not. This is the one place every inbound path passes through.
        update["specialist_outputs"] = {}
        update["revision_comments"] = []
        return update

    def specialist_dispatch_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        missing = _missing_upstream(state, "milestone_plan")
        if missing is not None:
            return missing
            
        # `effective_settings`, not `load_settings`. `load_settings` is a pure
        # function of the environment it is handed, and bare it reads this
        # container's own - which never carries anything an administrator
        # changed. The settings page writes `execution_mode` to the store, and
        # the store is layered in by `effective_environment`; without that step
        # the toggle saved correctly, displayed correctly and was read as
        # `linear` on every dispatch. `_effective_base_environment` is the same
        # source the model overrides above are layered on.
        from app.server.runtime_settings import effective_settings

        try:
            settings = effective_settings()
        except Exception:  # noqa: BLE001 - an unreachable store is the deployed config
            from app.config import load_settings

            logger.warning("Could not read the settings store; dispatching linearly", exc_info=True)
            settings = load_settings()
        if settings.execution_mode == "parallel":
            # A stage no node is named after. `_route_from_stage` turns it into
            # one `Send` per unfinished task; `specialist_gather` joins them.
            return {"stage": "specialist_dispatch_parallel"}
            
        milestone = state["milestone_plan"]
        tasks = milestone.delegated_tasks
        index = state.get("specialist_task_index", 0)

        if index < len(tasks):
            task = tasks[index]
            stage_name = f"specialist_{task.specialist_role}_{index}"
            agent = create_specialist_agent(
                task.specialist_role, model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories
            )
            selection = state.get("stack_selection")
            request = build_specialist_task_request(
                task.task_description,
                task.acceptance_criteria,
                state["repository"].root_path,
                getattr(selection, "technology_stack", None),
                # The sibling tasks, so a specialist sharing a file with another
                # is told before it rewrites the file wholesale.
                other_tasks=tasks,
                work_order=task,
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
        return _handing_on(stage="test_and_triage")

    def specialist_worker_node(state: dict, config: RunnableConfig) -> dict[str, Any]:
        """Worker node for executing a single specialist task in parallel mode."""
        task = state["__worker_task"]
        index = state["__worker_index"]
        stage_name = _specialist_stage_name(task, index)

        # `dict(state)`, with no `cast`: `cast` was never imported, so the first
        # parallel worker to run raised `NameError` before it reached its agent.
        # The annotation it was borrowing is not needed - this dictionary is
        # handed to helpers that read it with `.get`.
        temp_state: Any = dict(state)
        
        agent = create_specialist_agent(
            task.specialist_role, model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories
        )
        selection = state.get("stack_selection")
        request = build_specialist_task_request(
            task.task_description,
            task.acceptance_criteria,
            state["repository"].root_path,
            getattr(selection, "technology_stack", None),
            # The sibling tasks, from the plan rather than a local list: this node
            # is handed one task at a time. Wiring only the linear site left this
            # one without them, and this is the parallel site - the mode where
            # specialists really do run at once, so the one where a file two tasks
            # share matters most. Measured on one run, whose plan named
            # `app.js` in four of six tasks and whose `app.js` was written by five
            # stages, with no brief mentioning the overlap.
            other_tasks=list(
                getattr(state.get("milestone_plan"), "delegated_tasks", None) or ()
            ),
            work_order=task,
        )
        
        # A worker may only answer its *own* approval gate.
        #
        # `pending_decision` and `pending_inner_thread_id` are single fields, and
        # every worker in the superstep is handed a copy of the one state that
        # holds them. On a resume the dispatcher re-sends every task that has no
        # output yet, so without this each of those workers resumed whichever
        # inner thread happened to be stored there - a sibling's - and executed
        # the gated call that was waiting on it.
        #
        # Measured on one run: one `call_id` recorded three times under
        # three stage names, with three `tool_result` records microseconds apart,
        # one reporting `"status": "edited"` and the other two "already contains
        # the text you asked to put there". Every call that was multiplied was a
        # gated one - write_artifact 4, replace_lines 5, edit_artifact 3,
        # run_terminal_command 2 - and every ungated one ran exactly once, which
        # is the signature of the shared field rather than of three models
        # choosing the same call in the same second. `run_terminal_command` in
        # that list means the shell commands ran three times too.
        #
        # The cost was not only the duplicate work. The repeated-read tally is
        # per stage, and three executions raised it three times each, so the
        # read refusals and the withholding rungs fired at a third of the
        # repetition they are meant to describe.
        temp_state.update(_only_this_worker_s_pause(state, stage_name))

        update = _run_gated_agent(
            temp_state,
            config,
            stage_name=stage_name,
            agent=agent,
            initial_request=request,
            output_key="__specialist_result__",
            next_stage="specialist_dispatch", # doesn't matter for the map-reduce worker
        )
        
        answered_in_a_batch = bool((state.get("queued_decisions") or {}).get(stage_name))
        if "__specialist_result__" not in update:
            # Paused, waiting on a human for one of this task's writes. The pause
            # is recorded rather than returned: a pause update carries `stage`,
            # and `stage` has no reducer, so two workers pausing in one superstep
            # is `InvalidUpdateError: Can receive only one value per step` - the
            # fan-out dying instead of pausing. `specialist_gather` reads these
            # and surfaces them one at a time.
            return {"specialist_pauses": {stage_name: _as_a_queued_pause(
                state, stage_name, update, answered=answered_in_a_batch
            )}}

        # One key of a merged dictionary, so every worker's result survives the
        # superstep. Returning `stage` here instead is what made the fan-out
        # loop: the dispatcher left `stage` as `specialist_dispatch_parallel`,
        # the worker did not change it, and the router fanned the same tasks out
        # again on every pass until the recursion limit ended the run.
        finished: dict[str, Any] = {"specialist_outputs": {stage_name: update["__specialist_result__"]}}
        if answered_in_a_batch:
            # Its pause was answered in a batch and never surfaced, so its queue
            # entry is still there; left, `specialist_gather` would surface a
            # pause for a task that has finished.
            finished["specialist_pauses"] = {stage_name: None}
        return finished

    def specialist_gather_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:  # noqa: ARG001
        """Where the parallel fan-out joins, and the only writer of `stage` in it.

        Every worker converges here by a static edge, so this runs once after
        the whole fan-out regardless of how many tasks there were - which is
        what makes it safe to set `stage` at all.

        A worker that paused left its pause here instead of on `stage`. They are
        surfaced one at a time, the longest-waiting first (`_the_pause_to_surface`): the run pauses, a human
        answers, the dispatcher re-derives the fan-out, and the tasks that
        already have outputs are not re-sent. Several pauses therefore drain one
        after another rather than racing each other for one `stage` value.
        """
        pauses = _queued_pauses(state)
        if pauses:
            first = _the_pause_to_surface(pauses)
            # The pause update verbatim - not through `_handing_on`, which clears
            # exactly the pause fields this has to carry.
            #
            # Only the surfaced pause is drained. Emptying the whole queue threw
            # away the other workers' paused inner threads, and because
            # `pending_inner_thread_id` is a single field they then resumed the
            # surfaced stage's thread instead of their own and re-ran its gated
            # call - see `specialist_worker_node`. `_merge_or_reset` merges, so a
            # subset cannot remove a key and an empty dict would reset the lot;
            # one key set to `None` says "this one is answered" and leaves the
            # rest queued for the supersteps after it.
            surfaced = {key: value for key, value in pauses[first].items() if key != _QUEUED_AT}
            return {**surfaced, "specialist_pauses": {first: None}, "queued_decisions": {}}

        # Nothing is paused. A task the fan-out held back because it shares a
        # file with one that was running has not been dispatched yet, and this
        # is its next pass - `_that_do_not_share_a_file` promises one. Handing on
        # to the tests here skipped it: the deferred task was only ever run
        # because the resume path used to send the whole pending set at the
        # first approval, which also switched the staggering off. Now that a
        # resume staggers too, this is the only way a deferred task gets its
        # turn.
        #
        # No pause is outstanding at this point - any worker that paused in
        # this superstep left an entry in the queue above - so the decision and
        # thread from the last surfaced pause belong to a stage that has since
        # finished, and are cleared rather than carried into a fresh dispatch.
        if _tasks_without_an_output(state):
            return {
                "stage": "specialist_dispatch_parallel",
                "pending_decision": None,
                "pending_inner_thread_id": None,
                "pending_approval": None,
                "queued_decisions": {},
            }
        return _handing_on(stage="test_and_triage", specialist_pauses={}, queued_decisions={})

    def test_and_triage_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        missing = _missing_upstream(state, "milestone_plan")
        if missing is not None:
            return missing
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
        changed_files = _the_files_this_milestone_changed(state, outputs)

        agent = create_specialist_agent(
            "testing", model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories
        )
        request = build_test_run_request(
            milestone.selected_sprint_goal,
            changed_files,
            state["repository"].root_path,
            getattr(state.get("stack_selection"), "technology_stack", None),
            # The plan's own prose, so a file it named and nobody wrote is found
            # here rather than at the milestone review, where it costs a
            # revision. Both of the last two runs ended that way.
            planned=[
                *(getattr(milestone, "milestone_scope", None) or ()),
                *(
                    getattr(task, "task_description", "")
                    for task in (getattr(milestone, "delegated_tasks", None) or ())
                ),
            ],
            later_sprints=_what_later_sprints_build(state),
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
                charge_the_budget=_a_round_that_found_a_product_defect(new_defects),
            )
        except RemediationLimitExceeded as exc:
            return _escalate_to_a_human(
                state,
                error=str(exc),
                remediation=cycle,
                test_round=test_round + 1,
            )

        base_update: dict[str, Any] = {
            "remediation": cycle,
            "test_round": test_round + 1,
            "pending_approval": None,
            "pending_inner_thread_id": None,
            "pending_decision": None,
        }

        if cycle.escalated:
            return _replan_or_escalate(
                state, base_update, cycle, "exhausted remediation attempts"
            )

        if any(defect.status == "open" for defect in cycle.defects):
            return _handing_on(**base_update, stage="defect_remediation", defect_cursor=0)

        # Tests pass and nothing is open. The acceptance gate is still the
        # authority on whether this sprint may be accepted - it also refuses a
        # fix with missing regression coverage or an undocumented accepted risk.
        if not is_sprint_acceptable(cycle):
            return _replan_or_escalate(
                state, base_update, cycle,
                "missing regression coverage or an unaccepted risk",
            )

        return _handing_on(**base_update, stage="security_review")

    def _replan_or_escalate(
        state: WorkflowGraphState,
        base_update: dict[str, Any],
        cycle: Any,
        why: str,
    ) -> dict[str, Any]:
        """Hand a failed sprint back to be planned again, but only so often.

        `baf753d` changed both of these paths from `stage="failed"` to
        `stage="technical_lead"`, so a sprint that exhausts its remediation
        attempts is planned again instead of ending the run. That is a better
        default and it is kept.

        What it did not add is a bound. `milestone_revision_count` was
        incremented on the way out, and the only place that compares it to
        `MAX_MILESTONE_REVISIONS` is `milestone_review_node` - which this path
        never reaches: `technical_lead` leads to `specialist_dispatch` and back
        to `test_and_triage`, and an unfixable defect exhausts a fresh cycle
        every time. `test_a_defect_that_never_gets_fixed_escalates_instead_of_looping`
        is the test that says so, and it is right.

        So the re-plan is bounded by the same limit as every other revision, and
        past it the run escalates to a human carrying the defect report - which
        is what it did before the feature, at the first failure instead of the
        last.
        """
        revision_count = state.get("milestone_revision_count", 0) + 1
        if revision_count > MAX_MILESTONE_REVISIONS:
            summary = _record_sprint_summary(
                state, "Failed", f"{why}; revision limit reached"
            )
            # Failed, not parked at the sprint review. `_escalate_to_a_human`
            # sends a run to `user_review_sprint` when that review is switched
            # on, and that gate asks one question - accept this sprint? - whose
            # approve path is `sprint_advance`. Offering it a sprint whose tests
            # never passed invites a human to accept, in one click, work that
            # was never shown to work; it also drops `error` on that branch, so
            # the reviewer is asked without being told what is unresolved.
            # `test_a_blocked_sprint_never_reaches_its_optional_review` is the
            # test that says so. The cycle stays on the state either way: it is
            # the evidence for whoever reads the failure. Only the re-plan below
            # clears it, because the next attempt needs a fresh one.
            return _handing_on(
                **{**base_update, **summary},
                stage="failed",
                error=(
                    f"Sprint '{getattr(cycle, 'sprint_goal', '?')}' was re-planned "
                    f"{MAX_MILESTONE_REVISIONS} times and still could not be "
                    f"accepted: {why}.\n\n{build_defect_report(cycle)}"
                ),
            )
        summary = _record_sprint_summary(state, "Failed", why)
        # Merged, not passed twice. `base_update` already carries
        # `remediation` and `test_round`, and naming them again beside
        # `**base_update` is a TypeError - "got multiple values for keyword
        # argument 'remediation'" - raised inside the node, which took the run
        # down on the one path that exists to rescue it.
        return _handing_on(
            **{**base_update, **summary, "remediation": None, "test_round": 0},
            stage="technical_lead",
            milestone_plan=None,
            specialist_outputs={},
            defect_cursor=0,
            milestone_revision_count=revision_count,
        )

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
            getattr(state.get("stack_selection"), "technology_stack", None),
            # What the failing command actually printed, alongside the prose
            # description of it. See `build_defect_fix_request`.
            _what_the_last_failure_printed(config["configurable"].get(APP_RUN_ID_KEY)),
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
        # What the execution ledger confirms actually ran and passed for this
        # fix, or "". `VerificationRun` has always said a claim there is checked
        # against the ledger; until now it never was, and "fixed" meant the
        # specialist had named a test. It does not gate the transition - see
        # `mark_defect_fixed` for why that would cost more than it saves.
        verified_by = _what_the_ledger_confirms(
            state["repository"].root_path, fix_result.verification
        )
        if defect.regression_test_required and not regression_test:
            # No named regression test: the defect stays open on purpose. The
            # next test round will count this as another failed attempt, so the
            # bounded loop still terminates.
            update["remediation"] = cycle
        else:
            if not verified_by:
                logger.info(
                    "Stage %s reported a fix for '%s' with no command the ledger "
                    "records as having run and passed",
                    stage_name, defect.description[:80],
                )
            # How it was fixed, for the Sprint Record's defect log: the fixer's
            # own decisions and the files it changed.
            resolution = "; ".join(
                [" ".join(str(d).split()) for d in fix_result.decisions if str(d).strip()]
                + ([f"changed {', '.join(fix_result.changed_files)}"] if fix_result.changed_files else [])
            )[:600]
            update["remediation"] = mark_defect_fixed(
                cycle, defect_index, regression_test=regression_test, verified_by=verified_by,
                resolution=resolution,
            )

        update["specialist_outputs"] = outputs
        # Advance past this defect whether or not it closed. A defect left open
        # (no regression test named) must not be retried inside this round; the
        # next test round counts it as another failed attempt, keeping the loop
        # bounded by MAX_REMEDIATION_ATTEMPTS.
        update["defect_cursor"] = defect_index + 1
        return update

    def security_review_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        outputs = state.get("specialist_outputs", {})
        changed_files = _the_files_this_milestone_changed(state, outputs)
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

        # Rendered from the decision, like the architecture and milestone
        # reviews. This was the last reviewer still holding a write tool with
        # no document of its own to render - the same latent shape that ended
        # one run at stage three when the stack selector finally used it.
        # It had never misbehaved; neither had the stack selector, until it did.
        _record_document(
            state,
            "docs/security_review.md",
            render_security_review(review),
        )
        from app.sprint.record import findings_of

        return _handing_on(
            stage="milestone_review",
            security_review=review,
            sprint_findings=list(state.get("sprint_findings") or [])
            + findings_of(review, "security", state.get("milestone_revision_count", 0) + 1),
        )

    def milestone_review_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        """Review the milestone, and keep its findings for the Sprint Record.

        Every exit that produced a verdict carries it as `milestone_review`; its
        findings join the sprint's history here, once, not at each exit.
        """
        missing = _missing_upstream(state, "milestone_plan")
        if missing is not None:
            return missing
        result = _review_the_milestone(state, config)
        review = result.get("milestone_review") if isinstance(result, dict) else None
        if review is not None and review is not state.get("milestone_review"):
            from app.sprint.record import findings_of

            result["sprint_findings"] = list(state.get("sprint_findings") or []) + findings_of(
                review, "milestone", state.get("milestone_revision_count", 0) + 1
            )
        return result

    def _review_the_milestone(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        missing = _missing_upstream(state, "milestone_plan")
        if missing is not None:
            return missing
        milestone = state["milestone_plan"]
        outputs = state.get("specialist_outputs", {})
        changed_files = _the_files_this_milestone_changed(state, outputs)
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
            getattr(state.get("stack_selection"), "technology_stack", None),
            getattr(state.get("document"), "text", "") or "",
            # The blockers, risks and decisions the specialists recorded. They
            # were written into state and read by nothing - see
            # `what_the_specialists_reported`.
            outputs,
            # And what this reviewer itself said last round. Without it every
            # review is a fresh opinion of the same code, and two runs died at
            # the revision limit chasing one - see `what_you_said_last_time`.
            # Only on a re-review of the same milestone. `sprint_advance_node`
            # resets `milestone_revision_count` but leaves `milestone_review`
            # in state, so on the first review of a new sprint that field
            # still holds the last sprint's verdict - and handing a reviewer
            # another milestone's findings as "what you found last time" is
            # worse than handing it nothing.
            previous_review=(
                state.get("milestone_review")
                if state.get("milestone_revision_count", 0)
                else None
            ),
            revisions_used=state.get("milestone_revision_count", 0),
            revisions_allowed=MAX_MILESTONE_REVISIONS,
            sprint_scope=_this_sprint_s_scope_for_review(state),
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
            
        review: MilestoneReviewOutput = _a_pass_over_its_own_findings(
            _findings_a_later_sprint_builds(update.pop("__milestone_review__"), state),
            state["repository"].root_path,
            "accepted",
            "milestone_review",
        )
        # This round's findings, in the state the sprint record below reads, so
        # a sprint that ends on this review records the review that ended it.
        from app.sprint.record import findings_of

        state = {
            **state,
            "sprint_findings": list(state.get("sprint_findings") or [])
            + findings_of(review, "milestone", state.get("milestone_revision_count", 0) + 1),
        }

        # The document is rendered here, from the decision the workflow routes
        # on, rather than written by the reviewer as a second copy that can
        # disagree with it. See `app.agents.review_document`.
        _record_review_document(state, review, milestone.selected_sprint_goal)
        
        if review.status == "blocked":
            summary = _record_sprint_summary(state, "Failed", "Blocked by review")
            return _handing_on(
                **summary,
                stage="technical_lead",
                milestone_review=review,
                milestone_plan=None,
                specialist_outputs={},
                remediation=None,
                test_round=0,
                defect_cursor=0,
                milestone_revision_count=state.get("milestone_revision_count", 0) + 1,
            )
        elif review.status == "changes_required" and (
            not review.findings
            or _findings_that_block(review, state["repository"].root_path)
        ):
            # A `changes_required` carrying nothing above the gating severities
            # falls through to the accepted path below - the same hole that
            # cost one run six architecture rounds, fixed for every
            # reviewer rather than the one that happened to fail. An empty
            # `findings` still enters here, because the branch below has its
            # own message for a review that asked for changes and said nothing.
            findings_text = _milestone_changes_requested(review)
            if findings_text is None:
                return _handing_on(
                    stage="failed",
                    error=(
                        "The milestone review asked for changes but did not say what "
                        "to change: `findings` was empty and it recorded no evidence "
                        "either. Resume to re-run the review."
                    ),
                    milestone_review=review,
                )
            if not review.findings:
                # The reviewer described a defect only in `acceptance_evidence`.
                # `_findings_that_block` reads `findings`, so gating would be
                # bypassed and the lead would be handed prose it cannot act on
                # deterministically - the failure behind one run, where a
                # browser-breaking defect survived three revisions because it was
                # never turned into a task. Ask the reviewer again on a fresh
                # conversation before falling back to the evidence below.
                retries = dict(state.get("structured_retries", {}))
                attempted = retries.get("milestone_review:findings", 0) + 1
                retries["milestone_review:findings"] = attempted
                if attempted < _max_structured_retries():
                    logger.warning(
                        "Milestone review requested changes with no structured "
                        "findings; re-reviewing on a fresh conversation "
                        "(attempt %d of %d)",
                        attempted + 1,
                        _max_structured_retries(),
                    )
                    return _handing_on(
                        stage="milestone_review",
                        structured_retries=retries,
                        milestone_review=review,
                    )
                logger.warning(
                    "Milestone review still has no structured findings after %d "
                    "attempts; raising the ones the checks can prove",
                    attempted,
                )
                # Two fresh conversations have now declined to structure this
                # review, so stop asking a model for something the workspace
                # already answers. The cross-file checks decide these by reading
                # the files, and `summarise_integration` has already told this
                # reviewer that each one "means a feature DOES NOT WORK".
                #
                # Measured on one run: three proven defects, including an
                # `index.html` linking a `style.css` that was not there, went in
                # as evidence and came back as prose with `findings: []`. Prose
                # is not a task, so the lead was handed a paragraph three times
                # and the run failed with all three defects still in place.
                proven = findings_for_what_the_checks_proved(
                    state["repository"].root_path,
                    getattr(state.get("stack_selection"), "technology_stack", None),
                    getattr(state.get("document"), "text", "") or "",
                )
                if proven:
                    logger.info(
                        "Raising %d milestone finding(s) the cross-file checks "
                        "proved: %s",
                        len(proven),
                        "; ".join(finding.description[:80] for finding in proven),
                    )
                    review = review.model_copy(update={"findings": proven})
                    # Re-rendered so the revision request the lead receives names
                    # the findings rather than the prose they replaced.
                    findings_text = _milestone_changes_requested(review) or findings_text
                else:
                    logger.warning(
                        "Nothing the checks can prove either; falling back to the "
                        "recorded evidence"
                    )
            revision_count = state.get("milestone_revision_count", 0) + 1
            if revision_count >= MAX_MILESTONE_REVISIONS:
                # This sprint ends here, so it gets a summary like every other
                # ending. Measured on one run, which failed exactly here:
                # `docs/` held the plan, the review and the specification, and no
                # `sprint_1_summary.md` at all - the one document a reader opens
                # to ask what the sprint did and why it stopped. The four paths
                # that record a summary are the ones that go through
                # `_replan_or_escalate`, a blocked review, a sprint advance or
                # completion; a review that runs out of revisions is a fifth, and
                # it is the one this run took.
                summary = _record_sprint_summary(
                    state,
                    "Failed",
                    f"the milestone review still required changes after "
                    f"{MAX_MILESTONE_REVISIONS} revisions",
                )
                return _escalate_to_a_human(
                    state,
                    error=(
                        f"The milestone review still required changes after "
                        f"{MAX_MILESTONE_REVISIONS} revisions, so the run stopped "
                        f"rather than revising indefinitely.\n\n{findings_text}"
                    ),
                    milestone_revision_count=revision_count,
                    milestone_review=review,
                    **summary,
                )
            return _handing_on(
                stage="technical_lead",
                revision_comments=state.get("revision_comments", []) + [findings_text],
                milestone_revision_count=revision_count,
                milestone_review=review,
            )
        
        if review.status != "accepted" and review.findings:
            logger.info(
                "Stage milestone_review asked for changes over %d finding(s), none "
                "above %s; recorded and continuing",
                len(review.findings),
                "/".join(sorted(_GATING_SEVERITIES)),
            )

        # Before anything is accepted: the ledger's own count of the suite. A
        # review that reports a passing suite over a measured failing one is the
        # worst outcome in this pipeline, because nothing after it looks again.
        # See `_a_red_suite_the_review_called_green` for the run this is measured
        # on. Bounded by the same revision limit as every other send-back, so a
        # suite that cannot be made to pass ends the run rather than looping.
        red = _a_red_suite_the_review_called_green(state)
        if red:
            revision_count = state.get("milestone_revision_count", 0) + 1
            if revision_count < MAX_MILESTONE_REVISIONS:
                logger.warning(
                    "Milestone review accepted a sprint whose measured suite is "
                    "failing; sending it back: %s",
                    red[:160],
                )
                return _handing_on(
                    stage="technical_lead",
                    revision_comments=state.get("revision_comments", []) + [red],
                    milestone_revision_count=revision_count,
                    milestone_review=review,
                )
            summary = _record_sprint_summary(
                state,
                "Failed",
                f"the suite was still failing after {MAX_MILESTONE_REVISIONS} revisions",
            )
            return _escalate_to_a_human(
                state,
                error=(
                    f"The sprint's own test suite was still failing after "
                    f"{MAX_MILESTONE_REVISIONS} revisions.\n\n{red}"
                ),
                milestone_revision_count=revision_count,
                milestone_review=review,
                **summary,
            )

        sprint_index = state.get("current_sprint_index", 0)
        sprints = state.get("sprint_plan").sprints if state.get("sprint_plan") else []
        has_more_sprints = sprint_index < len(sprints) - 1

        # The definition of done: the part of "finished" that needs no judgement.
        # A sprint with a work order that never returned, or a defect still
        # open, is not finished however the review read it, and the next sprint
        # must not start on top of it. Bounded like every other send-back.
        from app.sprint.record import definition_of_done_gaps

        gaps = definition_of_done_gaps(milestone, outputs, cycle)
        if gaps:
            gaps_text = "The sprint is not done:\n" + "\n".join(f"- {gap}" for gap in gaps)
            revision_count = state.get("milestone_revision_count", 0) + 1
            if revision_count < MAX_MILESTONE_REVISIONS:
                logger.warning("Milestone accepted but not done; sending it back: %s", gaps_text[:200])
                return _handing_on(
                    stage="technical_lead",
                    revision_comments=state.get("revision_comments", []) + [gaps_text],
                    milestone_revision_count=revision_count,
                    milestone_review=review,
                )
            summary = _record_sprint_summary(state, "Failed", "the sprint was not done: " + "; ".join(gaps))
            return _escalate_to_a_human(
                state,
                error=f"The sprint was accepted but is not done after {MAX_MILESTONE_REVISIONS} revisions.\n\n{gaps_text}",
                milestone_revision_count=revision_count,
                milestone_review=review,
                **summary,
            )

        # Accepted: the tests ran, the reviewer read them and said yes. This is
        # the only point in a sprint where the workflow has an opinion that the
        # work is sound, so it is the only sensible thing to record as a state
        # worth returning to. Never fails the sprint that has just passed.
        try:
            from app.tools.version_control import commit_milestone

            commit_milestone(
                state["repository"].root_path,
                sprint=sprint_index + 1,
                goal=milestone.selected_sprint_goal,
                summary=_as_text(review.acceptance_evidence),
            )
        except Exception:  # noqa: BLE001 - history is a convenience, not the run
            logger.warning("Could not record a commit for this sprint", exc_info=True)

        # The last sprint is the only place the whole brief is the question.
        # Every milestone review before this one is scoped to its own
        # milestone, and deferring a requirement out of one is legitimate -
        # that is what a sprint plan is for. Nothing asked the other question,
        # and `complete_node` returns `{"stage": "complete"}` and nothing else,
        # so a requirement deferred out of every milestone in turn was never
        # checked at all. Three completed runs shipped with no way to edit a
        # task that way: three runs.
        if not has_more_sprints:
            unbuilt = _a_brief_requirement_the_run_never_built(state)
            if unbuilt:
                revision_count = state.get("milestone_revision_count", 0) + 1
                if revision_count < MAX_MILESTONE_REVISIONS:
                    logger.warning(
                        "The last sprint was accepted with a brief requirement "
                        "unbuilt; sending it back rather than completing: %s",
                        unbuilt[:160],
                    )
                    return _handing_on(
                        stage="technical_lead",
                        revision_comments=state.get("revision_comments", []) + [unbuilt],
                        milestone_revision_count=revision_count,
                        milestone_review=review,
                    )
                return _escalate_to_a_human(
                    state,
                    error=(
                        "The last sprint was accepted, but the brief has a "
                        f"requirement this run never built.\n\n{unbuilt}"
                    ),
                    milestone_revision_count=revision_count,
                    milestone_review=review,
                )

        if _review_enabled(state, SPRINT_REVIEW):
            next_stage = "user_review_sprint"
        elif has_more_sprints:
            next_stage = "sprint_advance"
        else:
            next_stage = "complete"

        return _handing_on(stage=next_stage, milestone_review=review)

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
        summary = _record_sprint_summary(state, "Completed")
        # What this sprint hands the next one's lead: findings it neither fixed
        # nor was blocked by, and what failed repeatedly. See `app.sprint.record`.
        latest = (summary.get("sprint_attempts") or [{}])[-1]
        return {
            **summary,
            "carried_forward": list(latest.get("carried_forward") or []),
            "lessons": list(latest.get("lessons") or []),
            "sprint_findings": [],
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
        """The run is done - and the sprint that finished it needs its summary.

        Only `sprint_advance_node` recorded one, and the last sprint never
        advances: it routes straight here. So a three-sprint plan wrote
        `sprint_1` and `sprint_2` and stopped, and the sprint that actually
        delivered the product was the one with nothing to show for it.
        """
        if _sprint_already_summarised(state):
            return {"stage": "complete"}
        return {**_record_sprint_summary(state, "Completed"), "stage": "complete"}

    def failed_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:  # noqa: ARG001
        """Terminal failure - always with a reason, even when nothing set one.

        Every deliberate route to this node carries an `error`. One route does
        not, and cannot: `_owning_node` answers `"failed"` for a stage no node
        owns, which is what stops an unrecognised stage raising `KeyError` inside
        LangGraph and taking the run down. It is a router. It has no state to
        write a reason to.

        So the run arrived here with `error` unset, and the runner records
        `record.error = state.get("error")` - leaving a row that says `failed`
        and nothing else. One run is one of those: 73 minutes of work,
        approvals answered every 30 seconds, then `failed` at 11:53 with a null
        error, no event and no way to tell what had happened. Diagnosing it
        started by ruling out the three causes it was not.

        `stage` still holds whatever routed here - nothing has overwritten it yet
        - so the reason can name it.
        """
        if str(state.get("error") or "").strip():
            return {"stage": "failed"}

        routed_from = str(state.get("stage") or "").strip()
        if routed_from and routed_from != "failed":
            reason = (
                f"The run was routed to failure from stage '{routed_from}', which no "
                "node owns, so nothing recorded why.\n\n"
                "A stage value is set either by a node handing on or by a resume "
                "reading the checkpoint. One that no node answers for means a stage "
                "name was written that the graph has no node for - check "
                "`_NODE_NAMES`, `_ITERATED_STAGE_OWNERS` and whatever last set "
                "`stage`. The work already done is on disk and the checkpoint is "
                "intact."
            )
        else:
            reason = (
                "The run reached its failure state without recording a reason. "
                "Every deliberate failure names one, so this is a route that does "
                "not - the stage it came from is in the run's events and its "
                "transcript."
            )
        logger.error("Run failed with no reason recorded; routed from %r", routed_from)
        return {"stage": "failed", "error": reason}

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
    graph.add_node("specialist_worker", specialist_worker_node, retry_policy=agent_retry_policy)
    graph.add_node("specialist_gather", specialist_gather_node)
    # A static edge, not the shared router: every `Send` branch converges
    # here and LangGraph runs the target once for the whole superstep,
    # which is what gives the fan-out a single writer for `stage`.
    graph.add_edge("specialist_worker", "specialist_gather")
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
        "specialist_gather",
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


def _run_config(
    thread_id: str,
    recursion_limit: int,
    metadata: dict | None = None,
    run_id: str | None = None,
) -> RunnableConfig:
    """Build the per-invoke config every entry point below shares.

    The run id rides in `configurable` rather than `metadata` because metadata
    is only populated when LangSmith tracing is enabled, and the activity stream
    must work whether or not anyone is tracing.

    It is keyed `APP_RUN_ID_KEY`, never `run_id`: LangGraph reserves that name
    and silently discards the input of any invoke whose `run_id` matches the one
    already in the checkpoint. See the constant's docstring.
    """
    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id, APP_RUN_ID_KEY: run_id},
        "recursion_limit": recursion_limit,
    }
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
    run_id: str | None = None,
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
        config=_run_config(thread_id, recursion_limit, metadata=metadata, run_id=run_id),
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
    run_id: str | None = None,
) -> dict[str, Any]:
    """Resume a failed run from its last checkpoint.
    
    If the run explicitly entered a terminal 'failed' state due to business logic
    (e.g., reaching max revisions), this rewinds the state to act as a retry.
    """
    config = _run_config(thread_id, recursion_limit, metadata=metadata, run_id=run_id)
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
    run_id: str | None = None,
    queued_decisions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resume a run paused on a mandatory artifact-write approval.

    Call this (instead of `start_workflow` or a raw `invoke`) whenever
    `state["stage"]` starts with `awaiting_approval:`. Setting `pending_decision`
    is what tells the paused node to resume its inner agent with this decision
    instead of starting a new inner conversation.

    Build `decision` with the helpers in `app.agents.approval`:
    `approve_write_decision()`, `edit_write_decision(...)`, or
    `reject_write_decision(...)`.

    `queued_decisions`: decisions for parallel pauses queued behind this one,
    by stage name (see `queued_parallel_pauses`). Each queued worker resumes
    its own paused thread with its own decision in the same superstep.
    """
    update: dict[str, Any] = {"pending_decision": decision}
    if queued_decisions:
        update["queued_decisions"] = dict(queued_decisions)
    return graph.invoke(update, config=_run_config(thread_id, recursion_limit, metadata=metadata, run_id=run_id))


def queued_parallel_pauses(state: Any) -> dict[str, dict[str, Any]]:
    """The parallel pauses queued behind the surfaced one, by stage name.

    For the runner, which under auto-approve answers all of them in the same
    resume (`resume_pending_approval(..., queued_decisions=...)`). Each value
    carries the pause's `pending_approval`, `pending_inner_thread_id` and when
    it joined the queue. Empty outside a parallel fan-out.
    """
    surfaced = _the_stage_that_paused(state)
    return {
        stage: {
            "pending_approval": pause.get("pending_approval"),
            "pending_inner_thread_id": pause.get("pending_inner_thread_id"),
            "queued_at": pause.get(_QUEUED_AT),
        }
        for stage, pause in _queued_pauses(state).items()
        if stage != surfaced
    }


def resume_pending_review(
    graph: Any,
    thread_id: str,
    decision: dict[str, Any],
    *,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
    metadata: dict | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Resume a run paused on an optional human review session.

    Call this (instead of `start_workflow` or a raw `invoke`) whenever
    `state["stage"]` starts with `awaiting_review:`.

    Build `decision` with the helpers in `app.graph.workflow`:
    `approve_decision()`, `request_changes_decision(...)`, or
    `skip_decision()`.
    """
    return graph.invoke({"pending_review_decision": decision}, config=_run_config(thread_id, recursion_limit, metadata=metadata, run_id=run_id))


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
    "queued_parallel_pauses",
    "build_workflow_graph",
    "request_changes_decision",
    "resume_failed_run",
    "resume_pending_approval",
    "resume_pending_review",
    "skip_decision",
    "start_workflow",
]
