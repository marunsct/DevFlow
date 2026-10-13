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
from pathlib import Path, PurePosixPath
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
from app.agents.stack_selector import (
    the_browser_runner_this_stack_forgot,
    the_rationale_for_the_corrected_runner,
)
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
    how_much_a_plan_leaves_out,
    unaccounted_success_measures,
    with_setup_folded_into_the_sprint_that_needs_it,
)
from app.agents.sprint_summary import (
    a_suite_that_did_not_pass,
    count_test_cases,
    last_test_run,
    render_sprint_summary,
)
from app.agents.stack_selector import StackSelectorOutput, create_stack_selector_agent
from app.agents.specialist_advice import create_specialist_advice_agent
from app.agents.advice_review import create_advice_reviewer_agent
from app.agents.suite_dispute import create_suite_dispute_agent
from app.agents.specialists import (
    ReportedDefect,
    SpecialistOutput,
    build_defect_fix_request,
    build_specialist_task_request,
    build_test_run_request,
    create_specialist_agent,
    raised_by,
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

from app.graph.acceptance_nodes import ACCEPTANCE_REVIEW  # noqa: E402 - beside its siblings
from app.graph.delivery import RELEASE_REVIEW  # noqa: E402 - beside its siblings
from app.graph.escalation import ESCALATION_REVIEW  # noqa: E402 - beside its siblings

_REVIEW_NODES = {
    SPECIFICATION_REVIEW: "user_review_specification",
    SPRINT_REVIEW: "user_review_sprint",
    PRODUCT_INTAKE_REVIEW: "user_review_product_intake",
    ACCEPTANCE_REVIEW: "user_review_acceptance",
    RELEASE_REVIEW: "user_review_release",
    ESCALATION_REVIEW: "user_review_escalation",
}
"""Maps a review point to the node that owns its gate, so the entry router can
re-enter the right node when a paused review is resumed."""

_REVIEW_STAGES = {
    SPECIFICATION_REVIEW: WorkflowStage.ARCHITECTURE,
    SPRINT_REVIEW: WorkflowStage.IMPLEMENTATION,
    PRODUCT_INTAKE_REVIEW: WorkflowStage.INTAKE,
    ACCEPTANCE_REVIEW: WorkflowStage.VALIDATION,
    RELEASE_REVIEW: WorkflowStage.COMPLETE,
    ESCALATION_REVIEW: WorkflowStage.IMPLEMENTATION,
}
"""Maps a review point to the `WorkflowStage` recorded on its `ReviewStatus`,
so an auditor can tell which lifecycle stage a review decision belongs to."""

_NODE_NAMES = frozenset(
    {
        "product_manager",
        "user_review_product_intake",
        "tools_models",
        "stack_selector",
        "specialist_consultation",
        "principal_architect",
        "architecture_review",
        "user_review_specification",
        "scaffold",
        "acceptance_author",
        "acceptance_review",
        "user_review_acceptance",
        "scrum_master",
        "technical_lead",
        "specialist_dispatch",
        # Parallel mode's fan-out target. `graph.add_node` registers it and
        # routers reference it, but it was absent here - and every conditional
        # edge map, including the entry router's, is built from this set. So no
        # edge map contained it and a resume parked on it had no target.
        "specialist_worker",
        "specialist_gather",
        "ci_gate",
        "code_review",
        "test_and_triage",
        "defect_remediation",
        "security_review",
        "advice_review",
        "milestone_review",
        "acceptance_dispute",
        "user_review_sprint",
        "sprint_advance",
        "change_request",
        "release",
        "user_review_release",
        "escalation",
        "user_review_escalation",
        "escalation_accept",
        "escalation_retry",
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
    "acceptance_author_": "acceptance_author",
    "stack_setup_": "scaffold",
    "acceptance_review_": "acceptance_review",
    "code_review_": "code_review",
    "consult_": "specialist_consultation",
    "advice_review_": "advice_review",
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
    # The specialists asked before the specification, and what each advised.
    # See `app.agents.specialist_advice`.
    consultation_roles: list[str]
    specialist_advice: dict[str, list[str]]
    # What each consulted specialist found of its adopted advice not built,
    # this sprint, and which review it belongs to. See `app.agents.advice_review`.
    advice_findings: dict[str, list[str]]
    advice_review_cycle: str
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
    # How often this sprint was planned again because its tests could not be
    # made to pass. Counted apart from `milestone_revision_count`, which is the
    # milestone review's: see `_replan_or_escalate`.
    sprint_replan_count: int
    sprint_plan: SprintPlanOutput
    # Success measures a sprint plan left unassigned or only partly delivered,
    # as {"measure": n, "missing": [items]}, carried into the one re-plan that
    # asks for them. See `unaccounted_success_measures` and
    # `capabilities_the_plan_never_names`.
    sprint_plan_gaps: list[dict[str, Any]]
    sprint_plan_built_ahead: list[str]
    current_sprint_index: int
    # Every attempt at every sprint, oldest first, each one a mapping of the
    # shape `sprint_summary.render_sprint_summary` documents. A sprint that
    # fails is re-planned and attempted again, and without this the second
    # attempt's summary overwrote the first - so the failure that caused the
    # re-run left no record, and the extra milestone it cost looked like an
    # extra sprint. Appended to, never rewritten.
    sprint_attempts: list[dict[str, Any]]
    # The work orders and defects of each plan a milestone review sent back in
    # the current attempt at a sprint - replaced by the revision, and kept so
    # the sprint's summary describes all of it. See `_record_sprint_summary`.
    sprint_earlier_plans: list[dict[str, Any]]
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
    nothing_left_but_carried: str | None
    # The failed attempts ("sprint index:attempts") whose locked tests the QA lead has judged.
    disputed_sprints: list[str]
    dispute_returns_to: str | None
    dispute_reason: str | None
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

    # The redesign (docs/redesign-software-company.md). `stack_pack` names the
    # pack `stack_selector` chose; `acceptance_*` carry the QA stage's rounds;
    # `decisions` is the decision log (`app.decisions`).
    stack_pack: str | None
    scaffold_result: dict[str, Any]
    acceptance_round: int
    acceptance_feedback: list[str]
    acceptance_open_problems: list[str]
    acceptance_result: dict[str, Any]
    # Where the acceptance stages go after a change request's test is locked:
    # back to the sprint, not to the sprint plan. See `app.graph.delivery`.
    acceptance_return_to: str | None
    # How often this run has reopened its locked suite to repair tests that
    # cannot pass. See `acceptance_nodes.reopen_the_suite_for`.
    suite_repairs: int
    release_attempts: int
    # The last rung: a stuck sprint's decision. See `app.graph.escalation`.
    escalation: dict[str, Any] | None
    escalation_count: int
    known_issues: list[str]
    # CI and code review between a batch and its test rounds, and the guard
    # around each fix. See `app.graph.engineering`.
    ci_report: str
    ci_batch_commit: str
    review_defects: list[Any]
    review_advice: list[str]
    fix_base_commit: str
    decisions: list[dict[str, Any]]


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
    manifests_present: set[str] | frozenset = frozenset(),
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
            _as_compared(str(path))
            for path in (getattr(task, "files", None) or ())
            if str(path).strip()
        }
        try:
            return declared | {
                _as_compared(path)
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
    # Only a manifest the project does not have yet: one the scaffold already
    # wrote is built on, not made. Measured on one run: the service's work
    # order listed `requirements.txt`, which the scaffold had written, and the
    # database, interface, tests and documentation all waited for it.
    missing = manifests - {name.lower() for name in manifests_present}
    first_the_manifest = {
        index for index, task in pending
        if {name.rsplit("/", 1)[-1] for name in (named_by(task) or set())} & missing
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
            # A bare name meets any path ending in it: one task writes
            # `app/app.js` and another `app.js`, and the plan's prose spells the
            # same file both ways. Paths with directories meet only the same
            # path - two `__init__.py` in two packages are two files, and one
            # run's database work order waited the whole of the service's for it.
            if _any_the_same_file(named, claimed):
                continue
        going.append((index, task))
        claimed |= named
        unknown_going = unknown_going or not named
    return going or pending


def _manifests_the_project_has(state: Any) -> set[str]:
    """The package manifests already at the top of the run's project directory. Never raises."""
    try:
        from app.tools.repository import PACKAGE_MANIFESTS, pinned_project_directory

        root = Path(state["repository"].root_path)
        project = root / (pinned_project_directory(root) or "")
        return {name for name in PACKAGE_MANIFESTS if (project / name).is_file()}
    except Exception:  # noqa: BLE001 - then every manifest counts as missing, as before
        return set()


def _as_compared(path: str) -> str:
    """A planned path as the stagger compares it: lower case, no leading `./` or `/`."""
    text = str(path).strip().rstrip("/").lower()
    while text.startswith(("./", "/")):
        text = text[2:] if text.startswith("./") else text[1:]
    return text


def _the_same_file(one: str, other: str) -> bool:
    """Whether two planned paths may be one file: equal, or one a bare name or tail of the other."""
    if one == other:
        return True
    shorter, longer = sorted((one, other), key=len)
    return longer.endswith("/" + shorter)


def _any_the_same_file(named: set[str], claimed: set[str]) -> bool:
    return any(_the_same_file(one, other) for one in named for other in claimed)


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
        going = _that_do_not_share_a_file(
            pending, already_going=must_go, manifests_present=_manifests_the_project_has(state)
        )
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

    Fewer readiness problems per work order wins, then more work orders. When the attempts ran
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

    # Problems per work order, then more work orders. A count of problems
    # alone preferred a plan for less: measured on one run, the last attempt
    # was four work orders - the database, the service and its tests - with two
    # problems, and an earlier single work order with one problem ("No
    # `testing` work order") was dispatched instead; the sprint built one.
    def rank(candidate: Any, found: list[str]) -> tuple[float, int]:
        orders = len(getattr(candidate, "delegated_tasks", None) or [])
        if not orders:
            return (float("inf"), 0)
        return (len(found) / orders, -orders)

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
    text: str | None = None,
    out_result: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Ask the same conversation for the answer it already worked out.

    `text`, when given, is what to ask instead of the reminder of the schema -
    see `_ask_about_the_files_it_never_wrote`.

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
                {"messages": [{"role": "user", "content": text or _nudge_text(previous, schema)}]},
                config=_inner_agent_config(inner_thread_id, run_id, callbacks, stage=stage),
            )
            if out_result is not None:
                out_result.append(result)
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


#: The tools whose success means a file now holds what the stage put there.
_FILE_WRITES = frozenset({"write_artifact", "edit_artifact", "replace_lines", "delete_artifact", "move_artifact"})


def _a_tool_result_that_succeeded(content: Any) -> bool:
    """Whether a write tool's result says it did what it was asked."""
    text = str(content or "").strip()
    if not text or text.lower().startswith("error"):
        return False
    try:
        parsed = json.loads(text)
    except ValueError:
        try:
            import ast

            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return True
    return not (isinstance(parsed, dict) and parsed.get("error"))


def _without_a_leading_dot_slash(path: str) -> str:
    """`./a/b` and `/a/b` as `a/b`; `.gitignore` stays as it is."""
    plain = path.strip()
    while plain.startswith("./"):
        plain = plain[2:]
    return plain.lstrip("/")


def _files_it_claims_but_never_wrote(result: Mapping[str, Any], answer: Any) -> list[str]:
    """The files an answer's `changed_files` names that nothing in its conversation wrote.

    Measured on one run: asked by a re-planned milestone to cut a file it
    owned, a stage read that file once and answered that it had removed a
    30-line block, replaced inline styles with classes, edited with
    `replace_lines` and run the tests - none of which it did. The file was
    unchanged, the milestone review blocked on the same size again, and the
    record said the work order was delivered.

    A file a terminal command names may have been changed by it, and is not
    judged.
    """
    claimed = [str(name).strip() for name in (getattr(answer, "changed_files", None) or ()) if str(name).strip()]
    if not claimed:
        return []
    messages = list(result.get("messages") or [])
    results = {
        str(getattr(message, "tool_call_id", "")): getattr(message, "content", "")
        for message in messages if getattr(message, "type", None) == "tool"
    }
    written: set[str] = set()
    commands: list[str] = []
    for message in messages:
        for call in getattr(message, "tool_calls", None) or ():
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
            args = (call.get("args") if isinstance(call, dict) else getattr(call, "args", None)) or {}
            call_id = str(call.get("id") if isinstance(call, dict) else getattr(call, "id", ""))
            if name == "run_terminal_command":
                commands.append(json.dumps(args))
            if name in _FILE_WRITES and _a_tool_result_that_succeeded(results.get(call_id)):
                for key in ("relative_path", "destination"):
                    if args.get(key):
                        written.add(_without_a_leading_dot_slash(str(args[key])))

    def _was_written(name: str) -> bool:
        plain = _without_a_leading_dot_slash(name)
        if any(plain == path or plain.endswith("/" + path) or path.endswith("/" + plain) for path in written):
            return True
        return any(plain.rsplit("/", 1)[-1] in command for command in commands)

    return [name for name in claimed if not _was_written(name)]


def _ask_about_the_files_it_never_wrote(
    agent: Any, inner_thread_id: str, callbacks: Any, files: list[str], run_id: str | None, stage: str,
    schema: Any = None,
) -> dict[str, Any] | None:
    """Ask the same conversation once to make the change it reported, or to report what it did.

    Returns the new result when it produced an answer or an approval pause,
    and None when the follow-up failed - the first answer then stands.
    """
    named = ", ".join(f"`{name}`" for name in files)
    text = (
        f"Your answer lists {named} under `changed_files`, but nothing in this conversation "
        f"wrote {'it' if len(files) == 1 else 'them'}: no write, edit, move or delete of "
        f"{'that file' if len(files) == 1 else 'those files'} succeeded. Work is done when the "
        "files hold it. Make the changes your work order asks for now, then answer again. If you "
        "made no change, answer with `changed_files` naming only what you wrote, and say under "
        "`blockers` what was not done and why."
    )
    return _nudge_for_the_structured_response(
        agent, inner_thread_id, callbacks, None, schema, run_id, stage, text=text,
    )


def _ask_about_high_confidence_diagnostics(
    agent: Any, inner_thread_id: str, callbacks: Any, diagnostics: list[str], run_id: str | None, stage: str,
    schema: Any = None,
) -> dict[str, Any] | None:
    """Ask the conversation once to fix high-confidence errors in modified files before exiting."""
    bullet_points = "\n".join(diagnostics[:4])
    text = (
        "The language service detected errors in the files modified in this stage:\n"
        f"{bullet_points}\n"
        "Fix these errors now before completing your work."
    )
    return _nudge_for_the_structured_response(
        agent, inner_thread_id, callbacks, None, schema, run_id, stage, text=text,
    )


#: Language-service findings about an import, by their code: TypeScript's
#: numbered ones and Pyright's named rules.
_AN_IMPORT_FINDING = frozenset({2305, 2614, 1192, 2306, 2307, "reportMissingImports",
                                "reportMissingModuleSource", "reportAttributeAccessIssue"})
_A_RELATIVE_SPECIFIER = re.compile(r"""['"](\.{1,2}/[^'"]+)['"]""")
_A_PYTHON_IMPORT = re.compile(r"^\s*(?:from\s+(\.*[\w.]*)\s+import|import\s+([\w.]+))")


def _files_an_import_names(importer: str, finding: dict, project: str) -> list[str]:
    """Workspace-relative paths the import a finding is about could name."""
    import posixpath

    text = f"{finding.get('text', '')} {finding.get('message', '')}"
    folder = posixpath.dirname(importer)
    candidates: list[str] = []
    for spec in _A_RELATIVE_SPECIFIER.findall(text):
        base = posixpath.normpath(posixpath.join(folder, spec))
        candidates.append(base)
        candidates += [f"{base}{ext}" for ext in (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx")]
        candidates += [f"{base}/index{ext}" for ext in (".js", ".ts", ".tsx", ".jsx")]
    python = _A_PYTHON_IMPORT.match(str(finding.get("text", "")))
    if python:
        module = python.group(1) or python.group(2) or ""
        dots = len(module) - len(module.lstrip("."))
        parts = [part for part in module.lstrip(".").split(".") if part]
        if dots:
            start = folder
            for _ in range(dots - 1):
                start = posixpath.dirname(start)
        else:
            start = project
        if parts:
            base = posixpath.join(start, *parts) if start else posixpath.join(*parts)
            candidates += [f"{base}.py", f"{base}/__init__.py"]
    return candidates


def _another_work_order_writes_it(root: str, importer: str, finding: dict, stage_name: str, project: str) -> bool:
    """Whether a finding is an import of a file another work order of this milestone owns.

    That file may not be written yet - work orders run side by side, or one
    after another - so the import is no error of this stage's. Only a
    specialist building a work order is told this: by the time a fix stage
    runs, every work order is done.
    """
    if not str(stage_name or "").startswith("specialist_") or finding.get("code") not in _AN_IMPORT_FINDING:
        return False
    try:
        import json

        from app.tools.repository import WORK_ORDER_FILES

        table = json.loads((Path(root) / WORK_ORDER_FILES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(table, dict):
        return False
    return any(
        table.get(candidate) not in (None, stage_name)
        for candidate in _files_an_import_names(importer, finding, project)
    )


def _diagnostics_in_files_touched(
    state: Any, result: dict[str, Any], structured_response: Any, stage_name: str = "",
) -> list[str]:
    """High-confidence syntax or reference diagnostics in files modified by this stage.

    Runs what an IDE would underline (via `language_service.underlined_any`) over the
    files touched by this stage. Only certain errors (ReferenceError, missing exports,
    undeclared names) are reported, bounded to a maximum of 4 items - and not an
    import of a file another work order owns (`_another_work_order_writes_it`).
    """
    from app.analysis.file_kinds import is_scratch
    from app.analysis.language_service import ALL_SUFFIXES, underlined_any

    repo = state.get("repository") if isinstance(state, dict) else None
    root = getattr(repo, "root_path", None)
    if not root or not Path(root).is_dir():
        return []

    try:
        from app.tools.repository import pinned_project_directory

        pinned = pinned_project_directory(Path(root))
    except Exception:  # noqa: BLE001
        pinned = None
    project = Path(root) / pinned if pinned else None

    files_to_check: set[str] = set()
    for file_name in getattr(structured_response, "changed_files", None) or ():
        files_to_check.add(_without_a_leading_dot_slash(str(file_name)))

    for message in result.get("messages") or ():
        for call in getattr(message, "tool_calls", None) or ():
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
            args = (call.get("args") if isinstance(call, dict) else getattr(call, "args", None)) or {}
            if name in _FILE_WRITES:
                for key in ("relative_path", "destination"):
                    if args.get(key):
                        files_to_check.add(_without_a_leading_dot_slash(str(args[key])))

    diagnostics: list[str] = []
    for relative in sorted(files_to_check):
        if not relative.lower().endswith(ALL_SUFFIXES) or is_scratch(Path(relative).name):
            continue
        target = Path(root) / relative
        if not target.is_file():
            continue
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            found = underlined_any(root, target, content, project)
            if found and getattr(found, "here", None):
                for finding in found.here:
                    if _another_work_order_writes_it(root, relative, finding, stage_name, pinned or ""):
                        continue
                    line = finding.get("line", "?")
                    msg = finding.get("message", "")
                    diagnostics.append(f"- In `{relative}` line {line}: {msg}")
                    if len(diagnostics) >= 4:
                        return diagnostics
        except Exception:  # noqa: BLE001
            continue

    return diagnostics


def _run_unit_tests_procedurally(repo_root: str) -> tuple[bool | None, str]:
    """Run the contract's unit test command: (whether it passed, its output).

    (None, why) when there is no command to run: unknown is not passed. It
    returned True there, and a test round on a project with no contract was
    skipped as "all tests passed" with nothing run.
    """
    try:
        from app.stacks import contract
        from app.stacks.scaffold import sandbox_runner

        found = contract.read(repo_root)
        if not found or not found.get("unit_test"):
            return None, "no unit test command is recorded for this project"

        cmd = found.get("unit_test")
        project = str(found.get("project") or "")
        if not isinstance(cmd, list) or not cmd:
            return None, "no unit test command is recorded for this project"

        runner = sandbox_runner(repo_root)
        outcome = runner(cmd, "test", project)
        rc = outcome.get("returncode", 1)
        output = str(outcome.get("stdout") or "") + str(outcome.get("stderr") or "")
        return rc == 0, output
    except Exception:  # noqa: BLE001 - procedural test failure falls back to agent triage
        return False, ""


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


#: Stages whose "could not do it" the workflow already has an outcome for: a
#: defect left open for the next round, a work order returned with blockers.
_STAGES_THAT_MAY_RETURN_BLOCKED = ("defect_fix_", "specialist_", "test_round_")

_CUT_OFF_BLOCKER = (
    "Every reply of this stage was cut off at the model's output limit before it wrote "
    "anything, so nothing was done here; the harness recorded this answer in its place."
)


def _blocked_for_want_of_room(stage_name: str) -> Any | None:
    """A structured answer saying the stage could not reply, where the workflow handles one; else None.

    Measured on one run: a defect-fix stage's first reply was 25,000 tokens of
    reasoning, the reply after it - thinking off - was 25,000 tokens with
    nothing in them, and the run failed 4 h 45 min in on that one stage. A fix
    not made has an outcome - the defect stays open and the next round
    measures it - so one fix or work-order stage that cannot reply does not
    end the run. Every other stage still fails it, as before.
    """
    if not str(stage_name or "").startswith(_STAGES_THAT_MAY_RETURN_BLOCKED):
        return None
    try:
        from app.agents.specialists import SpecialistOutput

        return SpecialistOutput(blockers=[_CUT_OFF_BLOCKER])
    except Exception:  # noqa: BLE001 - then the run fails, as before
        return None


#: Stages that can continue with procedural evidence or blockers when structured
#: retries are spent, rather than failing the run: every stage whose "could not
#: do it" the workflow already has an outcome for. Measured on one run: a
#: defect-fix stage spent its 40 calls three times over on one defect - the
#: third attempt found the cause on its last call - and the run failed at
#: 9 h 52 min, though a fix not made leaves its defect open for the next round.
_STAGES_THAT_MAY_FALLBACK_ON_EXHAUSTION = _STAGES_THAT_MAY_RETURN_BLOCKED

#: How much of the last attempt's final message the blocker keeps.
_LAST_WORDS_CHARS = 600

_EXHAUSTED_BLOCKER = (
    "This stage produced no structured response across all retry attempts; "
    "the harness recorded this answer so procedural checks and remaining defects can proceed."
)


def _blocked_when_retries_exhausted(stage_name: str, result: dict[str, Any] | None = None) -> Any | None:
    """A structured answer when retries are spent, where procedural steps follow; else None.

    With what the last attempt's final message said, when it said anything: it
    is where the stage's own investigation ended, and the defect it leaves open
    carries it to whoever picks it up next.
    """
    if not str(stage_name or "").startswith(_STAGES_THAT_MAY_FALLBACK_ON_EXHAUSTION):
        return None
    last = next(
        (m for m in reversed((result or {}).get("messages") or []) if getattr(m, "type", None) == "ai"),
        None,
    )
    words = " ".join(str(getattr(last, "content", "") or "").split())[:_LAST_WORDS_CHARS]
    try:
        from app.agents.specialists import SpecialistOutput

        return SpecialistOutput(blockers=[
            _EXHAUSTED_BLOCKER + (f" Where its last attempt ended: {words}" if words else "")
        ])
    except Exception:  # noqa: BLE001 - then the run fails, as before
        return None


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

    Item 7 of Part III of the hardening plan (`docs/harness-improvement-plan.md`). Cancelling a run did two
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
        nudge_result_box: list[dict[str, Any]] = []
        if not was_stopped_by_the_budget(result):
            nudged = _nudge_for_the_structured_response(
                agent,
                inner_thread_id,
                activity,
                result,
                getattr(agent, "workflow_response_format", None),
                config["configurable"].get(APP_RUN_ID_KEY),
                stage_name,
                out_result=nudge_result_box,
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
        elif nudge_result_box:
            # The nudge ran but did not return a structured response. Keep its
            # reply in `result` so the diagnosis below evaluates the messages
            # the stage actually ended on, not the pre-nudge turn.
            result = nudge_result_box[0]

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
        blocked = _blocked_for_want_of_room(stage_name) if out_of_room else None
        if blocked is None:
            blocked = _blocked_when_retries_exhausted(stage_name, result)
        if blocked is None:
            attempted = (state.get("structured_retries") or {}).get(stage_name, 0)
            raise ValueError(
                _missing_structured_response(stage_name, result, attempts=attempted + 1)
            )
        logger.warning(
            "Stage %s recorded as blocked rather than failing the run: %s",
            stage_name,
            "; ".join(getattr(blocked, "blockers", []) or []),
        )
        structured_response = blocked

    # An answer is cleaned, a file is refused: see `app.agents.model_output`.
    from app.agents.model_output import answer_without_leaked_turns

    structured_response = answer_without_leaked_turns(structured_response)

    # Reported changes nothing made: asked once, on the stage's own thread,
    # while it still holds what it read. See `_files_it_claims_but_never_wrote`.
    from app.agents.settled_answer import was_stopped_by_the_budget as _stopped_by_the_budget

    never_wrote = _files_it_claims_but_never_wrote(result, structured_response)
    if never_wrote and not _stopped_by_the_budget(result):
        logger.warning(
            "Stage %s reported changing %s, which nothing in it wrote; asking it once to make "
            "the change or say what it did", stage_name, ", ".join(never_wrote),
        )
        followed = _ask_about_the_files_it_never_wrote(
            agent, inner_thread_id, activity, never_wrote,
            config["configurable"].get(APP_RUN_ID_KEY), stage_name,
            getattr(agent, "workflow_response_format", None),
        )
        if followed is not None and followed.get("__interrupt__"):
            approval = extract_pending_approval(
                followed, state["repository"].root_path, requested_by=stage_name, stage=stage_name,
            )
            return {
                "stage": f"{APPROVAL_PAUSE_PREFIX}{stage_name}",
                "pending_approval": approval,
                "pending_inner_thread_id": inner_thread_id,
                "pending_decision": None,
                "inner_thread_ids": [*state.get("inner_thread_ids", []), inner_thread_id],
            }
        if followed is not None:
            result = followed
            structured_response = answer_without_leaked_turns(followed["structured_response"])
            never_wrote = _files_it_claims_but_never_wrote(result, structured_response)
    # Asked and still claimed, or not asked because the stage was out of
    # calls: the record keeps only what changed. Measured on the first stage
    # asked: one call from its budget, its tools withheld, it named the same
    # file again.
    if never_wrote and hasattr(structured_response, "model_copy"):
        logger.warning(
            "Stage %s still reports changing %s, which nothing in it wrote; recorded without them",
            stage_name, ", ".join(never_wrote),
        )
        structured_response = structured_response.model_copy(update={"changed_files": [
            name for name in structured_response.changed_files if str(name).strip() not in never_wrote
        ]})

    if not never_wrote and not _stopped_by_the_budget(result):
        diagnostics = _diagnostics_in_files_touched(state, result, structured_response, stage_name)
        if diagnostics:
            logger.warning(
                "Stage %s touched files with high-confidence diagnostics: %s; asking once to fix before exit",
                stage_name, "; ".join(diagnostics),
            )
            followed = _ask_about_high_confidence_diagnostics(
                agent, inner_thread_id, activity, diagnostics,
                config["configurable"].get(APP_RUN_ID_KEY), stage_name,
                getattr(agent, "workflow_response_format", None),
            )
            if followed is not None and followed.get("__interrupt__"):
                approval = extract_pending_approval(
                    followed, state["repository"].root_path, requested_by=stage_name, stage=stage_name,
                )
                return {
                    "stage": f"{APPROVAL_PAUSE_PREFIX}{stage_name}",
                    "pending_approval": approval,
                    "pending_inner_thread_id": inner_thread_id,
                    "pending_decision": None,
                    "inner_thread_ids": [*state.get("inner_thread_ids", []), inner_thread_id],
                }
            if followed is not None:
                result = followed
                structured_response = answer_without_leaked_turns(followed["structured_response"])

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


def _with_the_sections_it_dropped(revised: Any, previous: Any) -> Any:
    """A repaired specification, with any section it left empty taken from the one before.

    A repair asks for one section to be corrected and nothing else changed, and
    a model answering it can return only what it corrected. Measured on one
    run: asked to correct `testing`, the architect returned `testing` - two
    entries where there had been nine - and left `deployment` and
    `acceptance_criteria` empty, which the previous answer had filled. A
    section the repair left empty was not a section it was asked to remove.
    """
    if revised is None or previous is None or not hasattr(revised, "model_copy"):
        return revised
    kept = {
        section: getattr(previous, section)
        # And the sections answering the specialists, which only some products
        # have: a repair of `testing` is not a reason to lose the interface design.
        for section in (*_REQUIRED_SPECIFICATION_SECTIONS, "interface_design", "specialist_advice_decisions")
        if not getattr(revised, section, None) and getattr(previous, section, None)
    }
    if kept:
        logger.info("The repaired specification left %s empty; kept them from the previous answer", ", ".join(kept))
    return revised.model_copy(update=kept) if kept else revised


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


def _deferred_in_this_attempt(state: Any, since: str | None) -> list[str]:
    """The criteria an escalation deferred since `since`, so this sprint went on without them.

    One run's sprint 4 could not be finished, its two failing criteria were
    deferred by an automatic decision, and its record read "Status: Completed"
    with nothing to say the sprint had not delivered them.
    """
    deferred: list[str] = []
    for record in state.get("decisions") or []:
        if record.get("point") != "escalation" or not record.get("affects"):
            continue
        if since and str(record.get("decided_at") or "") <= since:
            continue
        deferred += [str(item) for item in record.get("affects") or [] if str(item) not in deferred]
    return deferred


def _the_accepted_counts(root: str, which: str = "accepted") -> dict[str, int] | None:
    """Tests, passed and failed in the state the last sprint was accepted in, or None.

    `which="latest"` for the harness's most recent measurement instead.
    """
    try:
        from app import ci

        snapshot = ci.load(root, which)
    except Exception:  # noqa: BLE001
        return None
    if snapshot is None:
        return None
    outcomes = [*snapshot.unit.values(), *snapshot.acceptance.values()]
    if not outcomes:
        return None
    passed = sum(1 for outcome in outcomes if outcome == "passed")
    failed = sum(1 for outcome in outcomes if outcome == "failed")
    return {"tests": len(outcomes), "passed": passed, "failed": failed}


def _what_a_plan_did(plan: Any, cycle: Any) -> dict[str, Any]:
    """A plan's work orders, as feature lines, and its cycle's defects, as the summary keeps them."""
    return {
        "features": [
            (getattr(task, "title", "") or "").strip() or getattr(task, "task_description", str(task))
            for task in (getattr(plan, "delegated_tasks", None) or [])
        ],
        "defects": [
            {
                "status": getattr(defect, "status", "open"),
                "description": getattr(defect, "description", ""),
                "owner": getattr(defect, "owner", "unassigned"),
                "source": getattr(defect, "source", "") or "",
                "resolution": getattr(defect, "resolution", "") or "",
            }
            for defect in (getattr(cycle, "defects", None) or [])
        ],
    }


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
    #
    # Every plan of this attempt, not only the last. A milestone review that
    # sends a sprint back replaces its plan and starts a new defect cycle, and
    # the summary used to read only those: one run's sprint 1 built the whole
    # page, was sent back over one XSS finding, and its summary listed only the
    # XSS fix under "Features Implemented" with "Total Bugs Found: 0" - for a
    # sprint whose fix rounds had found and fixed four defects.
    earlier = list(state.get("sprint_earlier_plans") or [])
    now = _what_a_plan_did(plan, cycle)
    features = [feature for done in earlier for feature in done.get("features") or []] + now["features"]
    defects = [defect for done in earlier for defect in done.get("defects") or []] + now["defects"]

    recorded = [dict(entry) for entry in (state.get("sprint_attempts") or [])]
    # A failed attempt an escalation accepted is closed here, not followed by
    # one more: the sprint goes on from it as it stands. See
    # `escalation._the_failed_attempt_accepted`.
    accepted_at_escalation = ""
    if status == "Completed":
        mine = [at for at, entry in enumerate(recorded) if entry.get("sprint_index") == sprint_index]
        if mine and recorded[mine[-1]].get("accepted_at_escalation"):
            accepted_at_escalation = str(recorded.pop(mine[-1])["accepted_at_escalation"])
    already = [entry for entry in recorded if entry.get("sprint_index") == sprint_index]
    # Counts belong to this attempt alone, so the window opens where the last
    # recorded attempt closed. Summing every test run in the sprint would count
    # one suite once per round.
    since = max((str(entry.get("ended_at")) for entry in recorded if entry.get("ended_at")), default=None)

    cases = None
    try:
        from app.tools.sandbox import read_execution_ledger

        cases = count_test_cases(
            _the_ledger(state["repository"].root_path, 1000), since=since
        )
    except Exception:  # noqa: BLE001 - a summary without counts beats no summary
        logger.debug("Could not read test counts for the sprint summary", exc_info=True)
    if status == "Completed":
        # The harness's own measurement of the state the sprint was accepted
        # in - every unit and acceptance test, from their JUnit reports - over
        # whatever a stage's last command printed. A sprint closed without new
        # work runs no stage's tests at all, and one run's records read
        # "Passed: 0, Failed: 0" for twelve passing unit tests and nine
        # passing acceptance tests.
        cases = _the_accepted_counts(state["repository"].root_path) or cases
    else:
        # Not the last command a stage happened to run. One run's sprint 2
        # failed on an acceptance criterion and its record read "17 tests, 16
        # passed, 0 failed" - a unit run, the acceptance suite not counted.
        cases = _the_accepted_counts(state["repository"].root_path, "latest") or cases

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
        "deferred": _deferred_in_this_attempt(state, since),
        "reason": failure_reason or "",
        **({"accepted_at_escalation": accepted_at_escalation} if accepted_at_escalation else {}),
        "cases": cases,
        "rounds": state.get("test_round", 0),
        "revisions": len(earlier),
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
    # The attempt is recorded; the next one starts with no earlier plans.
    return {"sprint_attempts": attempts, "sprint_earlier_plans": []}


def _accepted_when_nothing_in_it_gates(review: Any, repo_root: str) -> Any:
    """`review` recorded as accepted, when that is how it is about to be routed.

    A `changes_required` whose findings are all below the gating severities
    goes down the accepted path, and has since one run lost six rounds to the
    alternative. The record did not follow: the review document and the Sprint
    Record are written from `review.status`, so a sprint the workflow accepted
    was filed under "Status: changes_required". Measured on one run, after its
    one gating finding was contradicted by the command record and made minor.

    Only a review that has findings and none that block. One with no findings
    at all is a different case with its own handling, and is left alone.
    """
    try:
        if (
            getattr(review, "status", "") == "changes_required"
            and getattr(review, "findings", None)
            and not _findings_that_block(review, repo_root)
        ):
            return review.model_copy(update={"status": "accepted"})
    except Exception:  # noqa: BLE001 - the review as written stands
        pass
    return review


def _ran_no_test_that_passed(entry: Any) -> bool:
    """Whether a test command's own totals say nothing in it passed.

    Exit 0 is not a pass when every test was skipped. One run's stage replaced
    its suite with a single `skip(...)`, and `npm test` answered "# tests 1,
    # pass 0, # skipped 1" and exited 0; the ledger recorded a passing command
    and a fix stage returned "All good".

    Only when the run reported totals at all. A command whose output this
    cannot count is judged by its exit code, as before.
    """
    try:
        return "passed" in entry and int(entry.get("passed") or 0) == 0
    except (TypeError, ValueError):
        return False


def _the_test_command_this_stage_left_failing(repo_root: str, stage: str) -> tuple[str, str]:
    """`(command, how)` for a stage whose last run of a test command failed, or `("", "")`.

    Read from the execution ledger: the last command this stage ran in the
    `test` category. Only that one - a suite that failed and was then run again
    and passed has been dealt with. Never raises.
    """
    try:
        from app.tools.sandbox import _ran_and_answered, read_execution_ledger

        mine = [
            entry for entry in _the_ledger(repo_root, 2000)
            if entry.get("stage") == stage and entry.get("category") == "test"
        ]
        if not mine:
            return "", ""
        last = mine[-1]
        argv = [str(part) for part in last.get("command") or []]
        code = last.get("returncode")
        timed_out = str(last.get("error") or "").lstrip().startswith("Command timed out")
        if not argv:
            return "", ""
        if code == 0 and _ran_no_test_that_passed(last):
            return " ".join(argv), "exited 0 without a single test passing"
        if code in (0, None) and not timed_out:
            return "", ""
        if code is not None and _ran_and_answered(argv, code):
            return "", ""
        return " ".join(argv), "timed out" if timed_out else f"exited {code}"
    except Exception:  # noqa: BLE001 - the round as reported stands
        logger.debug("Could not check the stage's last run of the suite", exc_info=True)
        return "", ""


def _each_defect_once(reported: list[Any]) -> list[Any]:
    """`reported` with repeats removed, first occurrence kept, in order.

    Measured on one run: a test round returned 71 defects with two distinct
    descriptions - one line repeated as the model's output ran on - and the
    workflow dispatched a fix stage per entry. Twenty-five fix stages in a row,
    over 35 minutes, were each handed the same defect before the run was
    stopped; the round would have taken 71. A defect is the same one when its
    description, owner and affected files are, ignoring case and spacing.
    """
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    kept: list[Any] = []
    for defect in reported:
        owner = getattr(defect, "owner", "")
        key = (
            " ".join(str(getattr(defect, "description", "") or "").lower().split()),
            str(getattr(owner, "value", owner) or ""),
            tuple(sorted(str(f) for f in (getattr(defect, "affected_files", None) or ()))),
        )
        if key in seen:
            continue
        seen.add(key)
        kept.append(defect)
    return kept


#: What names the thing a defect is about: a quoted name, a selector, a code
#: identifier, a criterion. File names are not among them: a file is what two
#: defects share when they are in one place, not what makes them one problem.
_A_NAME = re.compile(
    r"`([^`\n]{2,120})`"
    r"|(?<![\w/.])([#.][A-Za-z][\w-]*[A-Za-z0-9])"
    r"|\b([a-z]+(?:[A-Z][a-z0-9]+)+)\b"
    r"|\b([a-z][a-z0-9]*(?:[-_][a-z0-9]+)+)\b"
    r"|\b((?:AC|CR)-\d+)\b"
)
_A_FILE_NAME = re.compile(r"^[\w./-]+\.[a-z][a-z0-9]{0,5}$", re.I)
_SEVERITY_RANK = {"blocking": 0, "major": 1, "minor": 2}


#: The label a check puts before what it found - "Code review (the work
#: order's title): ..." - which names who found it, not what was found.
_A_LABEL = re.compile(r"^[A-Z][\w ]{0,30}\([^()\n]*(?:\([^()\n]*\)[^()\n]*)*\):\s*")


def _names_in(text: str) -> set[str]:
    """The names a defect's text gives, lower-cased: what it is about."""
    names: set[str] = set()
    for match in _A_NAME.finditer(_A_LABEL.sub("", text or "", count=1)):
        name = next(group for group in match.groups() if group).strip().lower()
        if _A_FILE_NAME.match(name) and not name.startswith(("#", ".")):
            continue
        names.add(name)
        # A name inside a quoted test name counts on its own as well.
        if match.group(1):
            names.update(_names_in(match.group(1)) - {name})
    return names


def _the_same_cause(one: Any, other: Any) -> bool:
    """Whether two defects describe one problem: in one place, about one named thing.

    In one place: they name a file in common, or one names none. About one
    thing: a name in common, or a compound name of one - a check's rule, like
    `color-contrast` - whose words both appear in the other.
    """
    files = {PurePosixPath(str(f)).name.lower() for f in getattr(one, "affected_files", None) or []}
    theirs = {PurePosixPath(str(f)).name.lower() for f in getattr(other, "affected_files", None) or []}
    if files and theirs and not files & theirs:
        return False
    text, other_text = str(getattr(one, "description", "") or ""), str(getattr(other, "description", "") or "")
    names, other_names = _names_in(text), _names_in(other_text)
    if names & other_names:
        return True

    def spelled_out(compounds: set[str], prose: str, whole_page: bool) -> bool:
        # A check of the whole product - one that names no file, like a page's
        # accessibility rule `color-contrast` - is matched by any long word of
        # its rule; anything else by every word of its name, so that a defect
        # about `empty-state` is not matched by any text that says "state".
        words = set(re.findall(r"[a-z0-9]+", _A_LABEL.sub("", prose, count=1).lower()))
        for name in compounds:
            parts = [part for part in re.split(r"[-_]", name.lstrip("#.")) if part]
            if len(parts) < 2:
                continue
            if whole_page and any(len(part) >= 5 and part in words for part in parts):
                return True
            if all(len(part) >= 3 and part in words for part in parts):
                return True
        return False

    return spelled_out(names, other_text, not files) or spelled_out(other_names, text, not theirs)


def _one_defect_per_cause(reported: list[Any]) -> list[Any]:
    """`reported` with the defects that describe one problem merged into one, in order.

    Measured on one run: one colour that a sprint's restyle had put back was
    reported by the test round, the regression check, the code review and the
    page check - five defects, five fix stages, the first of which fixed it and
    the rest of which found nothing to do. Merged, the first such defect keeps
    its place and owner, and carries what every other check said about it, so
    its one fixer sees every symptom; its files are all of theirs, and it is as
    severe as the most severe of them.
    """
    if len(reported) < 2:
        return list(reported)
    parent = list(range(len(reported)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for i in range(len(reported)):
        for j in range(i + 1, len(reported)):
            if root(i) != root(j) and _the_same_cause(reported[i], reported[j]):
                parent[root(j)] = root(i)
    groups: dict[int, list[int]] = {}
    for index in range(len(reported)):
        groups.setdefault(root(index), []).append(index)
    merged: list[Any] = []
    for index, item in enumerate(reported):
        group = groups[root(index)]
        if group[0] != index:
            continue
        if len(group) == 1:
            merged.append(item)
            continue
        others = [reported[i] for i in group[1:]]
        files = list(dict.fromkeys(
            str(f) for member in (item, *others) for f in getattr(member, "affected_files", None) or []
        ))
        severity = min(
            (str(getattr(member, "severity", "major") or "major") for member in (item, *others)),
            key=lambda value: _SEVERITY_RANK.get(value, 1),
        )
        also = "\n".join(
            f"- [{getattr(other, 'source', '') or 'reported'}] {' '.join(str(other.description).split())[:400]}"
            for other in others
        )
        merged.append(item.model_copy(update={
            "description": f"{item.description}\n\nThe same problem, as other checks reported it:\n{also}",
            "affected_files": files,
            "severity": severity,
        }))
        logger.warning(
            "%d defects describe one problem; merged into one: %s",
            len(group), " ".join(str(item.description).split())[:100],
        )
    return merged


def _proven_problems_the_round_left_out(
    proven: list[str], reported: list[Any], milestone: Any
) -> list[Any]:
    """A defect for each proven problem no reported defect names, or [].

    The round is handed these as "already proven by reading the files ...
    Report every one as a defect". Measured on one run: every round was told
    the page `index.html` its plan named was missing, and rounds 0, 1 and 2
    each reported one defect - the first proven item - and left the rest. The
    page that made every browser test fail waited three rounds to be anyone's
    task, while the remediation budget ran down on the others.

    A proven problem counts as reported when one reported defect names at
    least half of the files it names; one that names no file, when a reported
    defect shares its opening words. Half, not one: a problem naming
    `package.json`, `app.js` and three test files - CommonJS in an ES-module
    package - was counted as reported by "ReferenceError: st is not defined in
    app.js", a typo, because `app.js` is in nearly every defect. It went
    unrecorded for three rounds and the run failed on it. It is owned by the
    work order whose files it names, as the plan assigns them; with none, by
    testing, which ran into it.
    """
    from app.analysis.integration_checks import files_named_in

    def said(defect: Any) -> str:
        parts = [
            getattr(defect, "description", ""),
            getattr(defect, "actual_behavior", ""),
            " ".join(getattr(defect, "affected_files", None) or ()),
        ]
        return " ".join(str(part or "") for part in parts)

    told = [said(defect) for defect in reported]
    owners: dict[str, str] = {}
    for task in getattr(milestone, "delegated_tasks", None) or ():
        role = str(getattr(getattr(task, "specialist_role", ""), "value", None) or getattr(task, "specialist_role", ""))
        for name in getattr(task, "files", None) or ():
            owners.setdefault(PurePosixPath(str(name)).name, role)

    left_out: list[Any] = []
    for problem in proven:
        named = files_named_in(problem)
        if named:
            needed = max(1, (len(named) + 1) // 2)
            if any(sum(1 for name in named if name in text) >= needed for text in told):
                continue
        else:
            opening = " ".join(problem.lower().split()[:6])
            if any(opening and opening in text.lower() for text in told):
                continue
        owner = next((owners[name] for name in sorted(named) if name in owners), "testing")
        try:
            left_out.append(ReportedDefect(
                description=problem,
                severity="major",
                reproduction_steps="Read the files it names; this was decided by comparing them.",
                expected_behavior="The two files agree.",
                actual_behavior=problem,
                affected_files=[],
                owner=owner,
            ))
        except Exception:  # noqa: BLE001 - an owner the model type refuses
            left_out.append(ReportedDefect(
                description=problem,
                severity="major",
                reproduction_steps="Read the files it names; this was decided by comparing them.",
                expected_behavior="The two files agree.",
                actual_behavior=problem,
                affected_files=[],
                owner="testing",
            ))
    return left_out


def _a_suite_failure_the_round_did_not_report(
    repo_root: str, stage: str, *, but_the_acceptance_suite: bool = False
) -> Any | None:
    """A defect for a test round whose own last run of the suite failed, or None.

    A round with no defects sends the sprint on to its reviews. Measured on one
    run: two rounds in a row ran `npm test`, were answered with exit 134 and a
    heap-exhaustion trace, and returned an empty defect list. The sprint went
    to its milestone review as passing, the review found the suite failing, and
    the run ended on its last revision - with nobody ever asked to fix it.

    `but_the_acceptance_suite`: not when that run was of the locked acceptance
    suite, whose failures the round's defects were set aside for (locked tests
    that cannot pass and may not be repaired again).
    """
    command, how = _the_test_command_this_stage_left_failing(repo_root, stage)
    if not command:
        return None
    if but_the_acceptance_suite and _runs_the_acceptance_suite(repo_root, command):
        return None
    try:
        from app.acceptance import sprint_scope

        if sprint_scope.only_later_sprints_fail(repo_root):
            # A later sprint's tests failing is what a sprint before it expects.
            # See `sprint_scope.only_later_sprints_fail`.
            logger.info("`%s` failed only on tests a later sprint makes pass; not a defect", command)
            return None
    except Exception:  # noqa: BLE001 - unreadable reports leave the defect as before
        pass
    return ReportedDefect(
        description=(
            f"The suite does not pass: `{command}` {how} on this round's last run "
            "of it, and the round reported no defect for that."
        ),
        severity="major",
        reproduction_steps=f"Run `{command}` in the project directory.",
        expected_behavior=f"`{command}` exits 0.",
        actual_behavior=f"`{command}` {how}.",
        affected_files=[],
        owner="testing",
    )


def _runs_the_acceptance_suite(repo_root: str, command: str) -> bool:
    """Whether `command` (as `_the_test_command_this_stage_left_failing` gives it) runs the acceptance suite."""
    try:
        from app.acceptance import suite

        found = suite._command(repo_root)
    except Exception:  # noqa: BLE001 - unknown is not the acceptance suite
        return False
    if not found or not found[0]:
        return False
    return command.split()[: len(found[0])] == list(found[0])


def _the_plan_assigns_nothing(unassigned: Any, measures: Any) -> bool:
    """Whether a sprint plan left every one of the release's deliverables unassigned."""
    try:
        return bool(measures) and len(set(unassigned or ())) >= len(measures)
    except TypeError:
        return False


def _clear_the_throwaways(repo_root: str) -> None:
    """See `repository.clear_the_throwaways_left_behind`. Never raises."""
    try:
        from app.tools.repository import clear_the_throwaways_left_behind

        removed = clear_the_throwaways_left_behind(repo_root)
        if removed:
            logger.warning(
                "Removed %d debugging script(s) finished stages left in the project: %s",
                len(removed), ", ".join(removed[:8]),
            )
    except Exception:  # noqa: BLE001 - tidying must never fail a test round
        logger.debug("Could not clear throwaway scripts", exc_info=True)


def _the_last_failed_attempt_at_this_sprint(state: Any) -> dict | None:
    """The sprint record's entry for the current sprint's last attempt, when it
    was not accepted; None on a first attempt or after an accepted one."""
    try:
        sprint_index = state.get("current_sprint_index", 0)
        mine = [
            entry for entry in (state.get("sprint_attempts") or [])
            if isinstance(entry, dict) and entry.get("sprint_index") == sprint_index
        ]
        if not mine or mine[-1].get("status") == "Completed":
            return None
        return mine[-1]
    except Exception:  # noqa: BLE001 - a plan without it beats no plan
        return None


def _commit_the_last_records(repo_root: str) -> None:
    """Commit what a completed run wrote after its last commit. Never raises.

    The release decision, its evidence and the last sprint's record are written
    after the release's own commit. Measured on three finished runs: each
    repository's last commit was the release's CI files, with
    `docs/decision_log.md`, `docs/reviews/release-evidence.md` and the last
    sprint's summary left uncommitted - a history whose release was never
    decided. Throwaway files go first, as before every test round.
    """
    try:
        from app.tools.version_control import commit_all, is_repository

        if not is_repository(repo_root):
            return
        _clear_the_throwaways(repo_root)
        commit_all(repo_root, "Run complete: the release decision, its evidence and the last sprint's record")
    except Exception:  # noqa: BLE001 - the run is complete either way
        logger.warning("Could not commit the run's last records", exc_info=True)


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


def _this_review_s_advice_findings(state: Any) -> dict[str, list[str]]:
    """The specialists' findings for the review under way, or {} when they belong to another."""
    cycle = f"{state.get('current_sprint_index', 0)}:{state.get('milestone_revision_count', 0)}"
    if state.get("advice_review_cycle") != cycle:
        return {}
    return dict(state.get("advice_findings") or {})


def _the_interface_design_for(state: Any, task: Any) -> list[str]:
    """The specification's interface design, for a task that builds the interface; else []."""
    if str(getattr(task, "specialist_role", "") or "") != "ui_ux":
        return []
    return [
        str(line) for line in getattr(state.get("technical_specification"), "interface_design", None) or []
        if str(line).strip()
    ]


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
    if not defects:
        return True
    return not all(
        _only_tests_or_scratch(getattr(defect, "affected_files", None)) for defect in defects
    )


def _only_tests_or_scratch(files: Any) -> bool:
    """Whether every file a defect names is a test or a throwaway script.

    False when it names none: an unlocated defect is not known to be anything.
    A debugging script is no more the product than a test is - one run's
    sprint spent four rounds on `play_debug_e2e.js` and the tests written
    about it.
    """
    from app.analysis.file_kinds import is_scratch, is_test

    names = [str(name) for name in (files or []) if str(name).strip()]
    return bool(names) and all(is_test(name) or is_scratch(name) for name in names)


def _needs_a_regression_test(reported: Any) -> bool:
    """Whether closing this reported defect should wait for a new regression test.

    Not when the defect is in the tests or a throwaway script itself. A
    regression test exists to prove a change to the product; for a defect in a
    test, the corrected test is its own proof, and demanding another is a test
    of a test. Measured on one run: `test_round_2` reported that
    `play_debug_e2e_regression.test.js` asserted nothing, and the fix stage -
    told it MUST add a regression test - wrote
    `play_debug_e2e_regression_test_has_expect.test.js`, a suite that reads the
    first one and checks it contains `expect`. The suite before it had been
    written as the "regression test" for a debugging script.
    """
    if not getattr(reported, "regression_test_required", True):
        return False
    return not _only_tests_or_scratch(getattr(reported, "affected_files", None))


#: The test a regression defect names: "Regression: `unit: <key>` passed before ...".
#: See `app.graph.engineering.regression_defects`.
_A_REGRESSED_TEST = re.compile(r"^Regression: `((?:unit|acceptance): .+?)` passed before")


def _a_regressed_test_passing_since(state: Any, defect: Any) -> str:
    """The test a regression defect names, when a measurement since shows it passing; else "".

    Since means by one of this round's fixes - `before` or `after` it - as for
    a defect's criteria (`acceptance_nodes.passing_since_reported`). A
    regression defect names one test and no criterion, so that check never
    reached it. Measured on one run: a sprint's restyle undid an earlier
    contrast fix, four checks raised it, and the first fixer restored it. The
    regression defect - its test passing again in every measurement after - went
    to two fixers in turn, each of which changed nothing and said it did not
    reproduce; it stayed open, and the sprint's attempt was spent on it.
    """
    match = _A_REGRESSED_TEST.match(str(getattr(defect, "description", "") or ""))
    if not match:
        return ""
    from app import ci

    latest = ci.load(state["repository"].root_path, "latest")
    since = rf"(?:before|after) defect_fix_{int(state.get('test_round', 0) or 0)}_\d+"
    if latest is None or not re.fullmatch(since, str(latest.label or "")):
        return ""
    name = match.group(1)
    kind, _, key = name.partition(": ")
    ran = latest.unit_ran if kind == "unit" else latest.acceptance_ran
    now = latest.unit if kind == "unit" else latest.acceptance
    return name if ran and ci._outcome_now(now, key) == "passed" else ""


def _the_kind_of_page_finding(description: str) -> str:
    """A page check's finding without its counts and details: what it is about."""
    return re.split(r"[\d:]", " ".join(str(description or "").split()), maxsplit=1)[0].strip().lower()


def _a_page_check_that_passes_now(state: Any, defect: Any, *, measured_since: bool = True) -> str:
    """Why a page-check defect is resolved - its kind of finding gone from the page now - or "".

    The page check reads the harness's last run of the suite, which every fix's
    measurement saves. `measured_since` asks, as for a regression, that the last
    measurement was one of this round's fixes, so the run read is later than
    the report; the round's own run of the suite is, by definition.

    Measured on one run: sprint 4's page check raised a contrast finding, the
    contrast defects beside it were fixed, and the page-check defect still went
    to a fixer in each of two rounds. The second spent fifteen minutes and every
    reply's reasoning budget re-reading a stylesheet that already passed.
    """
    if str(getattr(defect, "source", "") or "") != "page check":
        return ""
    if measured_since:
        from app import ci

        latest = ci.load(state["repository"].root_path, "latest")
        since = rf"(?:before|after) defect_fix_{int(state.get('test_round', 0) or 0)}_\d+"
        if latest is None or not re.fullmatch(since, str(latest.label or "")):
            return ""
    from app.graph import acceptance_nodes

    saved = acceptance_nodes.suite.last_result(state["repository"].root_path) or {}
    if not saved.get("ran"):
        return ""
    kind = _the_kind_of_page_finding(getattr(defect, "description", ""))
    still = [
        found for found in acceptance_nodes.interface_defects(state)
        if _the_kind_of_page_finding(getattr(found, "description", "")) == kind
    ]
    return "" if still or not kind else "the page check no longer finds it"


def _resolved_by_a_measurement(state: Any, defect: Any, *, measured_since: bool = True) -> tuple[str, str]:
    """(what proves it, why it is resolved) for a defect a measurement shows resolved; else ("", "")."""
    regressed = _a_regressed_test_passing_since(state, defect)
    if regressed:
        return regressed, f"{regressed} passes again"
    page = _a_page_check_that_passes_now(state, defect, measured_since=measured_since)
    if page:
        return "the harness's page check", page
    return "", ""


def _closed_if_an_earlier_fix_resolved_it(
    state: Any, cycle: Any, defect_index: int
) -> dict[str, Any] | None:
    """The update closing this defect when a fix earlier in its round resolved it, else None.

    Resolved means every criterion it named that was failing when it was
    reported passes in a measurement taken since. See
    `acceptance_nodes.passing_since_reported`. Never for a stage paused or under
    way, whose fixer has already begun; never raises.
    """
    try:
        if state.get("pending_inner_thread_id"):
            return None
        from app.acceptance import suite as acceptance_suite
        from app.graph import acceptance_nodes

        defect = cycle.defects[defect_index]
        root = state["repository"].root_path
        resolved = acceptance_nodes.passing_since_reported(state, list(defect.failing_criteria or []))
        proof, why = ("", "") if resolved else _resolved_by_a_measurement(state, defect)
        if proof:
            logger.warning(
                "Defect '%s' is already fixed: %s; closed without a fixer", defect.description[:80], why,
            )
            from app.observability import defect_ledger

            defect_ledger.note(
                "closed without a fixer", f"defect_fix_{state.get('test_round', 0)}_{defect_index}",
                defect=defect, round_=state.get("test_round", 0), index=defect_index,
                detail=f"{why}, in a measurement taken since it was reported",
                sprint=state.get("current_sprint_index", 0),
            )
            return _handing_on(
                stage="defect_remediation",
                defect_cursor=defect_index + 1,
                fix_base_commit="",
                remediation=mark_defect_fixed(
                    cycle, defect_index,
                    regression_test=proof,
                    verified_by="the harness's measurement after this round's fixes",
                    resolution=f"Fixed by an earlier fix in the same round: {why}.",
                ),
            )
        if not resolved:
            from app.graph.engineering import no_longer_underlined

            why = no_longer_underlined(root, defect.description)
            if not why:
                return None
            logger.warning("Defect '%s' is already fixed: %s Closed without a fixer", defect.description[:80], why)
            from app.observability import defect_ledger

            defect_ledger.note(
                "closed without a fixer", f"defect_fix_{state.get('test_round', 0)}_{defect_index}",
                defect=defect, round_=state.get("test_round", 0), index=defect_index, detail=why,
                sprint=state.get("current_sprint_index", 0),
            )
            return _handing_on(
                stage="defect_remediation",
                defect_cursor=defect_index + 1,
                fix_base_commit="",
                remediation=mark_defect_fixed(
                    cycle, defect_index,
                    regression_test="the language service's check of the file",
                    verified_by="the TypeScript language service",
                    resolution=f"Fixed by an earlier fix in the same round: {why}",
                ),
            )
        named = ", ".join(resolved)
        logger.warning(
            "Defect '%s' is already fixed: %s, failing when it was reported, now "
            "pass(es); closed without a fixer",
            defect.description[:80], named,
        )
        from app.observability import defect_ledger

        defect_ledger.note(
            "closed without a fixer", f"defect_fix_{state.get('test_round', 0)}_{defect_index}",
            defect=defect, round_=state.get("test_round", 0), index=defect_index,
            detail=f"{named} failing when it was reported, passing since",
            sprint=state.get("current_sprint_index", 0),
        )
        return _handing_on(
            stage="defect_remediation",
            defect_cursor=defect_index + 1,
            fix_base_commit="",
            remediation=mark_defect_fixed(
                cycle, defect_index,
                regression_test=f"the locked acceptance tests of {named}",
                verified_by=str(acceptance_suite.last_result(root).get("command") or ""),
                resolution=(
                    f"Fixed by an earlier fix in the same round: {named} failed when "
                    "this was reported and pass since."
                ),
            ),
        )
    except Exception:  # noqa: BLE001 - a defect not closed here goes to a fixer as before
        logger.debug("Could not tell whether an earlier fix resolved a defect", exc_info=True)
        return None


def _closed_by_this_round_s_measurement(state: Any, cycle: Any, test_round: int) -> Any:
    """`cycle` with every open defect this round's run of the suite shows resolved marked fixed.

    See `acceptance_nodes.passing_in_the_round`. Never raises: a defect left
    open here is counted as before.
    """
    try:
        from app.acceptance import suite as acceptance_suite
        from app.graph import acceptance_nodes

        command = str(acceptance_suite.last_result(state["repository"].root_path).get("command") or "")
        for index, defect in enumerate(list(cycle.defects)):
            if defect.status != "open":
                continue
            resolved = acceptance_nodes.passing_in_the_round(state, list(defect.failing_criteria or []))
            if not resolved:
                proof, why = _resolved_by_a_measurement(state, defect, measured_since=False)
                if proof:
                    logger.warning(
                        "Defect '%s' is fixed: %s, measured after this round's fixes",
                        defect.description[:80], why,
                    )
                    from app.observability import defect_ledger

                    defect_ledger.note(
                        "closed by the round's measurement", f"test_round_{test_round}", defect=defect,
                        round_=test_round, index=index, detail=why,
                        sprint=state.get("current_sprint_index", 0),
                    )
                    cycle = mark_defect_fixed(
                        cycle, index,
                        regression_test=proof,
                        verified_by="the harness's measurement after this round's fixes",
                        resolution=f"{why}, measured after test round {test_round}'s fixes.",
                    )
                continue
            named = ", ".join(resolved)
            logger.warning(
                "Defect '%s' is fixed: %s, failing when it was reported, pass in "
                "test_round_%d's run of the suite",
                defect.description[:80], named, test_round,
            )
            from app.observability import defect_ledger

            defect_ledger.note(
                "closed by the round's measurement", f"test_round_{test_round}", defect=defect,
                round_=test_round, index=index, detail=f"{named} pass in this round's run of the suite",
                sprint=state.get("current_sprint_index", 0),
            )
            cycle = mark_defect_fixed(
                cycle, index,
                regression_test=f"the locked acceptance tests of {named}",
                verified_by=command,
                resolution=(
                    f"{named} failed when this was reported and pass in the harness's "
                    f"run of the suite for test round {test_round}."
                ),
            )
    except Exception:  # noqa: BLE001
        logger.debug("Could not compare open defects with the round's measurement", exc_info=True)
    return cycle


def _a_measurement_can_close(defect: Any) -> bool:
    """Whether the measurement taken after every fix can show this defect resolved.

    The kinds `_closed_if_an_earlier_fix_resolved_it` closes without a fixer:
    criteria failing when it was reported, a regressed test, a page-check
    finding, what an IDE underlines.
    """
    return bool(
        list(getattr(defect, "failing_criteria", None) or [])
        or _A_REGRESSED_TEST.match(str(getattr(defect, "description", "") or ""))
        or str(getattr(defect, "source", "") or "") in {"page check", "language service"}
    )


#: Files that hold neither code nor configuration: prose, styles, images,
#: fonts. A sprint that changed only these gives a security review, or the
#: review of how data is kept, nothing to read.
_HOLDS_NO_CODE = frozenset({
    ".md", ".markdown", ".txt", ".rst", ".adoc",
    ".css", ".scss", ".sass", ".less",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".pdf",
})


def _changes_any_code(changed_files: Any) -> bool:
    """Whether any changed file holds code or configuration, in any language.

    The reviews were skipped unless a JavaScript, Python, HTML or JSON file
    changed: a product in any other language - or a sprint that changed only a
    container definition, a shell script or a CI pipeline - was never reviewed
    at all, and the review of how data is kept ran only when a file's name
    happened to contain a word like "db" or "store". Only a sprint that changed
    nothing but prose, styles and images skips them now.
    """
    return any(
        PurePosixPath(str(name).strip()).suffix.lower() not in _HOLDS_NO_CODE
        for name in changed_files or ()
        if str(name).strip()
    )


def _bundle_co_defects(cycle: RemediationCycle, defect_index: int) -> list[tuple[int, Any]]:
    """The open defects after this one that its fixer is shown too, to fix in the same stage.

    Same owner, and only kinds a measurement can close. Each stays open: the
    fix is measured (`engineering.after_a_fix`), and when the cursor reaches a
    bundled defect, `_closed_if_an_earlier_fix_resolved_it` closes it if that
    measurement shows it resolved - with no fixer - or sends it to its own
    fixer if not. A batch used to mark every bundled defect fixed on the
    strength of the first one's answer, whether the stage had touched it or
    not, and with "verified by <command>" standing in for a regression test.
    A defect no measurement can show resolved is not bundled: a fixer sent it
    after a batch had fixed it would find nothing to change and leave it open.
    """
    defect = cycle.defects[defect_index]
    return [
        (pos, d) for pos, d in enumerate(cycle.defects[defect_index + 1:], start=defect_index + 1)
        if d.status == "open" and d.owner == defect.owner and _a_measurement_can_close(d)
    ]


def _note_the_bundled(co_defects: list[tuple[int, Any]], *, defect_index: int, stage_name: str,
                      round_: int, sprint: int) -> None:
    """Record, for each bundled defect, which stage worked on it. It stays open."""
    from app.observability import defect_ledger

    for pos, co_d in co_defects:
        defect_ledger.note(
            "bundled", stage_name, defect=co_d, round_=round_, index=pos, sprint=sprint,
            detail=(
                f"shown to the fixer of defect {defect_index} too; closed only when a "
                "measurement shows it resolved"
            ),
        )


def _failing_criteria_it_names(state: Any, reported: Any) -> list[str]:
    """The criteria a reported defect names that fail now. See `Defect.failing_criteria`."""
    try:
        from app.graph import acceptance_nodes

        return acceptance_nodes.criteria_failing_now(state, str(getattr(reported, "description", "") or ""))
    except Exception:  # noqa: BLE001 - a defect without them is dispatched as before
        return []


def _needs_a_new_test(reported: Any, caught_by: str) -> bool:
    """Whether a fix for this defect has to come with a test nobody has written yet.

    Not when a test command is already failing. A regression test is one that
    fails while the defect is there and passes once it is gone, and the round
    that reported this one ended with exactly that in hand: the suite, red.
    Demanding another on top is how one run's first sprint grew nine "regression"
    files in three hours - five that could not run at all, one asserting that
    the failure *happens* - each of which the next round then reported as the
    defect, to be fixed with one more.

    A defect found with the suite passing is the case the rule was written for:
    nothing catches it, so the fix brings the test that will.
    """
    return _needs_a_regression_test(reported) and not caught_by


#: How an MVP feature is told apart from a success measure in the planner's
#: checklist. Free of list words, so `capabilities_never_named` reads only the
#: feature's own text.
MVP_FEATURE_LABEL = " (an MVP feature the product intake selected)"


def _what_the_sprints_must_deliver(intake: Any) -> list[str]:
    """The intake's success measures, then each MVP feature they do not repeat.

    The sprint plan is checked line by line against this list, and it was the
    success measures alone. Measured on one run: the intake's MVP candidates
    held "Toggle complete/incomplete with visual cue", the specification
    specified `toggleComplete(id)` and a `task:toggled` event, and no sprint
    planned either - the brief's acceptance criteria never said "complete", so
    nothing asked. The last sprint's milestone plan then "declined to add ...
    complete toggle functionality (future work)" with no sprint after it, and
    the run was accepted with a Completed filter that could never show a task.

    The MVP candidates are the intake's own choice of what this release
    contains - for a large brief, the part it did not defer - so assigning
    each to a sprint asks for nothing the intake did not already commit to.
    """
    measures = [
        str(m).strip() for m in (getattr(intake, "success_measures", None) or []) if str(m).strip()
    ]
    already = {m.lower() for m in measures}
    features = []
    for candidate in getattr(intake, "mvp_candidates", None) or []:
        text = str(candidate).strip()
        if text and text.lower() not in already:
            already.add(text.lower())
            features.append(f"{text}{MVP_FEATURE_LABEL}")
    return [*measures, *features]


def _without_the_mvp_features(checklist: list[str]) -> list[str]:
    """The checklist with each MVP feature blanked, numbering kept.

    An MVP feature has to be assigned to a sprint; its words are not checked
    against the plan. The word check reads the lists inside a short success
    measure, and an intake's feature lines are sentences: one run's "One HTML
    file with embedded or sibling CSS/JS ..." and "reject empty titles, ignore
    no-op toggles, and confirm deletion acts on the selected task only" handed
    a complete plan back for not delivering "embedded", "sibling" and "confirm".
    """
    return ["" if item.endswith(MVP_FEATURE_LABEL) else item for item in checklist]


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


def _the_fixes_to_keep(state: Any, task: Any = None) -> list[str]:
    """The defects earlier attempts fixed - in `task`'s files or role, or all. [] on any failure."""
    try:
        from app.sprint import record as sprint_record

        attempts = list(state.get("sprint_attempts") or [])
        if task is None:
            return sprint_record.fixes_to_keep(attempts)
        return sprint_record.fixes_to_keep(
            attempts,
            files=[str(f) for f in getattr(task, "files", None) or []],
            role=str(getattr(task, "specialist_role", "") or ""),
        )
    except Exception:  # noqa: BLE001 - a request without them is the one before this
        logger.debug("Could not list the fixes to keep", exc_info=True)
        return []


def _what_a_fix_stage_must_leave_alone(state: Any, defect: Any) -> str:
    """What later sprints build, and the fixes earlier ones made in the defect's files, for a fix stage.

    The builders and the lead were told both; a fix stage was told neither.
    Measured on one run: sprint 1's first fix stage, sent a code-review defect
    about the unit test command, ran the whole acceptance suite, saw its failures
    - nearly all later sprints' - and began building filtering, completion and
    deletion into sprint 1's module "to fix the 6 failing tests". Never raises.
    """
    try:
        from app.agents.specialists import fixes_to_keep_section
        from app.sprint import record as sprint_record

        later = _the_later_sprints_brief(state)
        kept = fixes_to_keep_section(sprint_record.fixes_to_keep(
            list(state.get("sprint_attempts") or []),
            files=[str(f) for f in getattr(defect, "affected_files", None) or []],
            role=str(getattr(defect, "owner", "") or ""),
        ))
    except Exception:  # noqa: BLE001 - a request without them is the one before this
        return ""
    if not (later or kept):
        return ""
    return (
        "\n\n" + later + kept
        + ("Fix this defect only. A failing test of a later criterion is not this defect.\n" if later else "")
    )


def _the_code_review_s_advice(state: Any) -> str:
    """The code review's findings no test or check shows, for the milestone review; or "".

    They were defects, each with a fixer; now they are advice. See
    `app.graph.engineering.what_shows_it` for the finding that made a bug of
    a non-problem.
    """
    advice = [" ".join(str(item).split()) for item in state.get("review_advice") or [] if str(item).strip()]
    if not advice:
        return ""
    return (
        "\n\n--- The code review's advice: no test or check shows these ---\n"
        + "\n".join(f"- {item}" for item in advice)
        + "\nAdvice, not defects. Send the sprint back over one only if you can name what "
        "fails because of it.\n"
    )


def _fixes_a_review_must_not_undo(state: Any) -> str:
    """The defects earlier attempts fixed, for a reviewer: a difference they made is no finding.

    Measured on one run: with the builders and the lead told to keep them
    (`_the_fixes_to_keep`), the colours sprint 1 had fixed for contrast survived
    sprint 4's revision - and its UI advice review reported both as departures
    from the adopted advice ("#empty-state color is #666666, spec requires
    #999999"), which the milestone review carried as findings. A review that asks
    for a fix to be undone is the specification's mistake made a third time.
    """
    try:
        from app.agents.specialists import fixes_to_keep_section

        kept = fixes_to_keep_section(_the_fixes_to_keep(state))
    except Exception:  # noqa: BLE001 - a review without them is the one before this
        return ""
    if not kept:
        return ""
    return (
        "\n\n" + kept + "A difference from the specification or from adopted advice that "
        "one of these fixes made is not a finding: both were written before the defect "
        "was found.\n"
    )


def _the_later_sprints_brief(state: Any) -> str:
    """Record what this sprint does not owe, and tell its builders. "" on any failure.

    The record is what the workspace listing, a stage's opening snapshot and a
    test command's result read to tell a later sprint's tests from this
    sprint's. See `app.acceptance.sprint_scope`.
    """
    try:
        from app.acceptance import sprint_scope, suite
        from app.graph import acceptance_nodes

        root = state["repository"].root_path
        sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
        index = int(state.get("current_sprint_index", 0) or 0)
        if not sprints or index >= len(sprints):
            return ""
        due = acceptance_nodes.criteria_due(state)
        later = [] if due is None else [c.id for c in suite.criteria(root) if c.id not in due]
        sprint_scope.record(root, sprint=index + 1, of=len(sprints), not_yet_due=later)
        return sprint_scope.brief(root, deferred=getattr(sprints[index], "out_of_scope", None) or ())
    except Exception:  # noqa: BLE001 - see docstring
        logger.debug("Could not record the sprint scope", exc_info=True)
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


def _defects_only_about(reported: list[Any], criteria: list[str]) -> tuple[list[Any], list[Any]]:
    """(the reported defects a fix can close, those naming only `criteria`).

    `criteria` are those whose locked tests cannot pass and may not be
    repaired again (`acceptance_nodes.beyond_repair`): a defect about them
    alone has nothing a fix stage can change.
    """
    if not criteria:
        return reported, []
    from app.acceptance.junit import tags_in

    kept: list[Any] = []
    set_aside: list[Any] = []
    for item in reported:
        text = " ".join(
            str(getattr(item, name, "") or "")
            for name in ("description", "reproduction_steps", "expected_behavior", "actual_behavior")
        )
        named = {tag for tag in tags_in(text) if tag.startswith("AC-")}
        (set_aside if named and named <= set(criteria) else kept).append(item)
    return kept, set_aside


def _defects_a_later_sprint_builds(reported: list[Any], state: Any) -> tuple[list[Any], list[Any]]:
    """(the reported defects this sprint fixes, those about work a later sprint builds).

    A test round runs the whole acceptance suite, and every criterion a later
    sprint delivers fails in it. Showing the round only the criteria due
    (`acceptance_for_round`) was not enough: one run's sprint 1, which owned
    AC-1 and passed it, had its round report ten defects - "Missing Done
    checkbox", "Missing Edit button", "Missing filter buttons" - each a later
    sprint's work, five of them blocking, and its fix stages set about building
    sprints 2 to 4 inside sprint 1.

    The same test the milestone review applies to its findings
    (`_findings_a_later_sprint_builds`): the criteria a defect cites are all due
    later, or the actions or files it names are only later sprints'. Nothing
    due is lost by it - `acceptance_nodes.failing_due_defects` still adds a
    defect for every due criterion that fails and no kept defect names.
    """
    try:
        from app.analysis.integration_checks import later_sprint_files_in, later_sprint_work_in
        from app.graph.acceptance_nodes import criteria_only_later

        later = _what_later_sprints_build(state)
        if not later:
            return reported, []
        now = _what_this_sprint_builds(state)
        kept: list[Any] = []
        moved: list[Any] = []
        for item in reported:
            description = str(getattr(item, "description", "") or "")
            text = " ".join(
                str(getattr(item, name, "") or "")
                for name in ("description", "reproduction_steps", "expected_behavior", "actual_behavior")
            )
            if (
                criteria_only_later(state, text)
                or later_sprint_work_in(description, now, later)
                or later_sprint_files_in(description, now, later)
            ):
                moved.append(item)
            else:
                kept.append(item)
        return kept, moved
    except Exception:  # noqa: BLE001 - the round's report as written stands
        logger.debug("Could not compare the round's defects with the sprint plan", exc_info=True)
        return reported, []


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
        from app.graph.acceptance_nodes import criteria_only_later

        for finding in getattr(review, "findings", None) or []:
            description = getattr(finding, "description", "")
            actions = (
                criteria_only_later(state, f"{description} {getattr(finding, 'evidence', '')}")
                or later_sprint_work_in(description, now, later)
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


_SAYS_IT_FAILS = re.compile(
    r"\b(?:fail\w*|block\w*|broken|invalid|cannot|can't|unable|exit(?:s|ed)?|error\w*"
    r"|non[- ]?existent|does not (?:run|work|pass)|never (?:runs?|passes))\b",
    re.I,
)
_SAYS_IT_PASSES = re.compile(r"\b(?:pass\w*|succeed\w*|green|exits? 0|works)\b", re.I)
_A_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")


def _where_each_command_stands(repo_root: str) -> dict[str, bool]:
    """Each command of two words or more in the ledger, by whether its most
    recent run passed. One-word commands are left out: `node` or `jest` in a
    sentence is not a claim about a command that was run."""
    from app.tools.sandbox import read_execution_ledger

    latest: dict[str, bool] = {}
    for entry in _the_ledger(repo_root, 10_000):
        argv = [str(part) for part in entry.get("command") or []]
        if len(argv) >= 2 and entry.get("returncode") is not None:
            latest[" ".join(argv)] = (
                entry.get("returncode") == 0 and not _ran_no_test_that_passed(entry)
            )
    return latest


def _the_passing_command_it_says_fails(description: str, standing: dict[str, bool]) -> str:
    """A command this finding says fails whose most recent run passed, or "".

    Narrow on purpose, because the answer takes a finding out of the gate. The
    command must be named in a sentence that says it fails and does not also
    say something passes; and the finding must name no command that is still
    failing - then it has a failure of its own to stand on.
    """
    def names(command: str, text: str) -> bool:
        # The whole command, not the start of a longer one: `npm test` is not
        # named by "npm test:e2e".
        return re.search(rf"(?<![\w:-]){re.escape(command)}(?![\w:-])", text) is not None

    named = [command for command in standing if names(command, description)]
    if not named or any(not standing[command] for command in named):
        return ""
    for sentence in _A_SENTENCE_END.split(description):
        for command in named:
            if (
                names(command, sentence)
                and _SAYS_IT_FAILS.search(sentence)
                and not _SAYS_IT_PASSES.search(sentence)
            ):
                return command
    return ""


_SAYS_THE_TESTS_FAIL = re.compile(
    r"\b(?:tests?|test suites?|suites?|specs?)\b[^.\n]{0,80}?"
    r"\b(?:fail\w*|cannot run|can't run|do(?:es)? not run|never runs?|crash\w*"
    r"|throws?|referenceerror|typeerror|syntaxerror)\b",
    re.I,
)

#: Kinds of test a finding can be about that one command's passing says
#: nothing of. A unit suite passing does not answer "the browser tests fail".
_A_KIND_OF_TEST = re.compile(
    r"\b(e2e|end[- ]to[- ]end|playwright|cypress|selenium|browser|integration|ui tests?)\b", re.I
)


def _where_each_test_command_stands(repo_root: str) -> dict[str, bool]:
    """Each command the ledger ran as a test, by whether its last run passed."""
    from app.tools.sandbox import read_execution_ledger

    latest: dict[str, bool] = {}
    for entry in _the_ledger(repo_root, 10_000):
        argv = [str(part) for part in entry.get("command") or []]
        if entry.get("category") != "test" or not argv:
            continue
        timed_out = str(entry.get("error") or "").lstrip().startswith("Command timed out")
        if entry.get("returncode") is None and not timed_out:
            continue
        latest[" ".join(argv)] = (
            entry.get("returncode") == 0 and not _ran_no_test_that_passed(entry)
        )
    return latest


def _the_passing_suite_it_says_fails(description: str, tests: dict[str, bool]) -> str:
    """The test command whose last run passed, when a finding says the tests
    fail and names no command at all; or "".

    One run's reviewer read a setup file, saw `require` in a project declared
    as ES modules, and wrote "this causes test suites to fail with
    ReferenceError before any tests run". The suite's last run had passed -
    nine suites, eighteen tests - and that was in front of it. It was the
    last revision allowed, and the run ended on it.

    Narrower than it looks. Every test command the ledger holds must have
    passed on its last run. The sentence must say the tests fail and not that
    anything passes. And a finding about a kind of test - browser, end-to-end -
    is left alone unless a command that passed is of that kind: a unit suite
    passing does not answer it.
    """
    if not tests or not all(tests.values()):
        return ""
    commands = " ".join(tests).lower()
    for sentence in _A_SENTENCE_END.split(description):
        if not _SAYS_THE_TESTS_FAIL.search(sentence) or _SAYS_IT_PASSES.search(sentence):
            continue
        kinds = {kind.lower() for kind in _A_KIND_OF_TEST.findall(description)}
        if any(kind.split()[0].replace("-", "") not in commands.replace("-", "") for kind in kinds):
            return ""
        return list(tests)[-1]
    return ""


def _findings_the_command_record_contradicts(review: Any, repo_root: str) -> Any:
    """`review` with each gating finding the command record contradicts made minor.

    Measured on one run. Its milestone reviewer found, correctly, that
    `npm test` could not run. A fix stage repaired it and the ledger recorded
    `npm test` passing - the request said so, under "where each distinct
    command stands now". The reviewer was also shown its own finding from last
    time, and returned it again word for word on the last revision allowed. The
    run ended with nothing delivered, on a claim the record beside it disproved.

    Kept, not dropped, like a finding about a later sprint's work: it stays in
    the review and the Sprint Record with what the record shows, and stops
    being a reason to send the sprint back.
    """
    try:
        standing = _where_each_command_stands(repo_root)
        if not standing:
            return review
        tests = _where_each_test_command_stands(repo_root)
        findings = []
        moved = 0
        for finding in getattr(review, "findings", None) or []:
            described = getattr(finding, "description", "")
            command = (
                _the_passing_command_it_says_fails(described, standing)
                or _the_passing_suite_it_says_fails(described, tests)
                if _severity_gates(getattr(finding, "severity", ""))
                else ""
            )
            if command:
                moved += 1
                finding = finding.model_copy(update={
                    "severity": "minor",
                    "description": (
                        f"The most recent run of `{command}` in this workspace passed, "
                        f"so this does not hold as written: {finding.description}"
                    ),
                })
            findings.append(finding)
        if not moved:
            return review
        logger.warning(
            "Milestone review raised %d gating finding(s) that a command fails when "
            "its most recent run passed; recorded as minor",
            moved,
        )
        return review.model_copy(update={"findings": findings})
    except Exception:  # noqa: BLE001 - the review as written stands
        return review


#: A finding that the product's packages break the brief.
_SAYS_A_DEPENDENCY_BREAKS_THE_BRIEF = re.compile(
    r"\b(?:dev)?dependenc(?:y|ies)\b[^.\n]{0,160}\b(?:violat\w*|forbid\w*|not allowed|prohibit\w*"
    r"|break\w*|against|contradict\w*|rules? out)\b"
    r"|\b(?:violat\w*|forbid\w*|prohibit\w*|break\w*|contradict\w*)\b[^.\n]{0,160}"
    r"\b(?:no|without) (?:external |third[- ]party )?dependenc",
    re.I,
)


def _findings_the_dependency_check_contradicts(review: Any, state: Any) -> Any:
    """`review` with each gating finding about dependencies the check on disk disproves made minor.

    Whether a product breaks a brief's rule on dependencies is decided, not
    read: `what_the_brief_forbids_that_is_there` compares the manifest with
    what the product's own code imports, and its answer goes into the review
    request as a fact. Measured on one run: the request said "declares no
    product dependencies; `@playwright/test`, `jest` are devDependencies used
    for testing only and are not shipped ... it is not a finding", and the
    reviewer returned "[blocking] package.json declares devDependencies (jsdom,
    jest, @playwright/test) which violate the brief ... Remove all
    devDependencies". They were the test runners this run's own stack had
    chosen. It was the last revision allowed, and the run ended on it.

    Only when the check found no violation at all. One it did find is the
    reviewer's to raise, and it is left exactly as written.
    """
    try:
        brief = getattr(state.get("document"), "text", "") or ""
        if not brief:
            return review
        from app.agents.brief_constraints import what_the_brief_forbids_that_is_there
        from app.agents.milestone_reviewer import _is_only_a_note

        checked = what_the_brief_forbids_that_is_there(brief, state["repository"].root_path)
        if any(not _is_only_a_note(item) for item in checked):
            return review
        findings = []
        moved = 0
        for finding in getattr(review, "findings", None) or []:
            if _severity_gates(getattr(finding, "severity", "")) and (
                _SAYS_A_DEPENDENCY_BREAKS_THE_BRIEF.search(getattr(finding, "description", ""))
            ):
                moved += 1
                finding = finding.model_copy(update={
                    "severity": "minor",
                    "description": (
                        "Checked against the manifest and the product's own imports: the "
                        "product ships no dependency, and packages used only to test it "
                        "are not what the brief's constraint is about. So this does not "
                        f"hold as written: {finding.description}"
                    ),
                })
            findings.append(finding)
        if not moved:
            return review
        logger.warning(
            "Milestone review raised %d gating finding(s) that test-only packages break "
            "the brief, which the check on disk disproves; recorded as minor",
            moved,
        )
        return review.model_copy(update={"findings": findings})
    except Exception:  # noqa: BLE001 - the review as written stands
        return review


#: The security review's grades that may hold a sprint. Everything below them
#: is the security reviewer saying "worth fixing, not urgent".
_SECURITY_GRADES_THAT_GATE = frozenset({"critical", "high"})


def _security_graded_by_its_own_review(review: Any, security_review: Any) -> Any:
    """`review` with its gating security findings made minor when the security review gated none.

    The security reviewer is the one asked to grade security, and the milestone
    reviewer is shown its findings. Measured on one run, twice in one sprint:
    the security review rated records in the user's own browser "readable via
    devtools" medium and the milestone review made it major; once the sprint
    had answered with an XOR cipher, the security review rated that low and
    medium and the milestone review again made it major - three attempts at a
    sprint spent on encryption the brief never mentions, and a real bug added
    (`btoa` refuses text outside Latin-1).

    Kept, as minor, with the security review's own word on it. Never raises.
    """
    try:
        if security_review is None:
            return review
        graded = {
            str(getattr(finding, "severity", "") or "").lower()
            for finding in getattr(security_review, "findings", None) or []
        }
        if graded & _SECURITY_GRADES_THAT_GATE:
            return review
        findings, moved = [], 0
        for finding in getattr(review, "findings", None) or []:
            if (
                str(getattr(finding, "category", "") or "").lower() == "security"
                and _severity_gates(getattr(finding, "severity", ""))
            ):
                moved += 1
                finding = finding.model_copy(update={"severity": "minor"})
            findings.append(finding)
        if not moved:
            return review
        logger.warning(
            "Milestone review raised %d security finding(s) above what the security "
            "review graded; recorded as minor",
            moved,
        )
        return review.model_copy(update={"findings": findings})
    except Exception:  # noqa: BLE001 - the review as written stands
        return review


def _findings_about_a_server_only_the_tests_start(review: Any, repo_root: str) -> Any:
    """`review` with each gating finding about a test runner's own server made minor.

    The pipeline asks for that server: a product with a page is tested in a
    browser, the browser needs the page served, and the test runner's
    configuration starts something to serve it. It ships to nobody and stops
    when the suite ends - `integration_checks._servers_started_by_a_test_runner`
    already keeps it from being read as a product server.

    Measured on one run. A fix stage wrote `serve.js` because the browser suite
    had nothing to start; the security review found, correctly, that it joined
    the request path to its root without checking it, and the milestone review
    made that blocking on the last revision allowed. The brief was a static
    page with no server at all.

    Kept, with what the file is: a traversal in a file server is worth fixing.
    It is not a reason to send back a sprint whose product has no server.
    Only when every file the finding names is one a test runner starts.
    """
    try:
        from pathlib import Path as _Path

        from app.analysis.integration_checks import (
            _servers_started_by_a_test_runner,
            _source_files,
            files_named_in,
        )

        root = _Path(repo_root).resolve()
        files = _source_files(root)
        started = {path.name for path in _servers_started_by_a_test_runner(files, root)}
        if not started:
            return review
        findings = []
        moved = 0
        for finding in getattr(review, "findings", None) or []:
            named = files_named_in(getattr(finding, "description", ""))
            if (
                _severity_gates(getattr(finding, "severity", ""))
                and named and named <= started
            ):
                moved += 1
                finding = finding.model_copy(update={
                    "severity": "minor",
                    "description": (
                        f"{', '.join(sorted(named))} is started by the test runner's own "
                        "configuration to serve the page to the browser suite; it is not "
                        "part of the product and does not ship. Worth fixing, and not a "
                        f"reason to send the sprint back: {finding.description}"
                    ),
                })
            findings.append(finding)
        if not moved:
            return review
        logger.warning(
            "Milestone review raised %d gating finding(s) about a server only the test "
            "runner starts; recorded as minor",
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


def _the_ledger(repo_root: str, limit: int) -> list[dict[str, Any]]:
    """The execution ledger without the locked acceptance suite's runs.

    Every check that reads "the suite's last run" from the ledger measures the
    developers' own tests. The acceptance suite holds every criterion and runs
    red until the last sprint, so its runs belong to the acceptance gate (see
    `app.acceptance.suite.is_an_acceptance_run`).
    """
    from app.tools.sandbox import read_execution_ledger

    entries = read_execution_ledger(repo_root, limit=limit)
    try:
        from app.acceptance.suite import is_an_acceptance_run

        return [entry for entry in entries if not is_an_acceptance_run(repo_root, entry)]
    except Exception:  # noqa: BLE001 - the whole ledger is still a ledger
        return list(entries)


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
        entries = _the_ledger(state["repository"].root_path, 1000)
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


def _about_the_harness_s_files_only(finding: Any, repo_root: str) -> bool:
    """Whether every file a finding names is one the harness keeps, and it names one."""
    from pathlib import PurePosixPath

    from app.analysis.integration_checks import files_named_in
    from app.stacks.contract import kept_paths

    kept = {PurePosixPath(path).name for path in kept_paths(repo_root)}
    if not kept:
        return False
    named = {PurePosixPath(str(path)).name for path in getattr(finding, "affected_files", None) or []}
    named |= files_named_in(
        f"{getattr(finding, 'description', '')} {getattr(finding, 'remediation', '')}"
    )
    return bool(named) and named <= kept


def _without_findings_about_the_harness_s_files(review: Any, repo_root: str) -> Any:
    """The security review without findings about the harness's own test setup. Never raises.

    No work order may change those files, and a change is put back. Measured
    on one run: the security review found that the harness's own test server
    serves any file under the project, the milestone review copied it as a
    major finding with the file's name dropped, and the last sprint was sent
    back for it - work nobody was allowed to do.
    """
    try:
        findings = list(getattr(review, "findings", None) or [])
        kept = [f for f in findings if not _about_the_harness_s_files_only(f, repo_root)]
        if len(kept) == len(findings):
            return review
        logger.info(
            "Left %d security finding(s) about the harness's own files out of the review",
            len(findings) - len(kept),
        )
        return review.model_copy(
            update={"findings": kept, **({} if kept else {"status": "passed"})}
        )
    except Exception:  # noqa: BLE001 - a filter must never lose the review
        return review


def _carried_to_this_plan(state: Any) -> list[str]:
    """What this plan must take or decline: the carried items, on a sprint's first plan only.

    A plan that finishes a sprint after a failed attempt answers that attempt's
    open defects; the sprint's first plan already took or declined what was
    carried to it, and what it took is in the workspace. Measured on one run:
    each re-plan of a failing last sprint was sent back twice for not
    recording a decision on each of fifteen carried items, and dispatched with
    the problem noted - three lead calls a plan, spent on items decided before.
    """
    if _the_last_failed_attempt_at_this_sprint(state) is not None:
        return []
    return _carried_here(state)


#: The `structured_retries` key, with the sprint's index after it, for a lead
#: asked again about carried work it declined only because no test requires it.
_UNTESTED_DECLINES = "technical_lead:untested_declines"


def _the_locked_tests_still_failing(state: Any) -> list[tuple[str, str, str]]:
    """(test name, criterion, failure) for each locked test the last measurement shows failing."""
    from app.acceptance import suite as acceptance_suite

    try:
        root = state["repository"].root_path
        if not acceptance_suite.is_locked(root):
            return []
        saved = acceptance_suite.last_result(root) or {}
    except Exception:  # noqa: BLE001 - nothing readable, nothing to judge
        return []
    deferred = set(acceptance_suite.deferred(root) or {})
    # Only what this sprint answers for. A later sprint's test fails because
    # nothing is built yet, not because it is wrong: one run's first dispute
    # was shown every failing test, and the QA lead named eight of the next
    # sprint's as unpassable - QA then rewrote nine valid tests.
    from app.graph.acceptance_nodes import criteria_due

    due = set(criteria_due(state) or [])
    failing: list[tuple[str, str, str]] = []
    seen: dict[str, int] = {}
    for cid, criterion in (saved.get("criteria") or {}).items():
        if not isinstance(criterion, dict) or cid in deferred or cid not in due:
            continue
        status = str(criterion.get("status") or "")
        tests = criterion.get("tests") or []
        if status == "untested" or not tests:
            # Only a suite that ran can show a criterion has no test: when the
            # runner wrote no report, every criterion reads "untested", and
            # QA would be sent to add tests that are there.
            if not saved.get("ran"):
                continue
            name = f"[{cid}] (missing from locked suite)"
            text = f"{cid}: {criterion.get('text', '')}"
            message = "The locked acceptance suite has no test for this due criterion."
            seen[name] = len(failing)
            failing.append((name, text, message))
            continue
        for test in tests:
            if isinstance(test, dict) and test.get("outcome") == "failed":
                name = str(test.get("name") or "")
                if not name:
                    continue
                text = f"{cid}: {criterion.get('text', '')}"
                message = str(test.get("message") or "")
                if name not in seen:
                    seen[name] = len(failing)
                    failing.append((name, text, message))
                    continue
                # One test carrying several criteria is listed under each, with
                # one failure: name every criterion, and its message once. Two
                # tests of one name (in two files) failing differently keep both.
                old_name, old_text, old_message = failing[seen[name]]
                if text not in old_text:
                    old_text = f"{old_text}; {text}"
                if message and message not in old_message:
                    old_message = f"{old_message}\n\n--- Also failed with ---\n\n{message}"
                failing[seen[name]] = (old_name, old_text, old_message)
    return failing


def _this_attempt(state: Any) -> str:
    """The sprint and how many attempts at it have been recorded: "4:2" for sprint 5's third.

    A dispute is judged once per failed attempt, not once per sprint: one run's
    first dispute named all three tests that could not pass, a fault in the
    harness dropped the answer, and the sprint spent two more attempts on them
    with its one dispute spent. The suite's repairs still bound how often it is
    reopened.
    """
    index = int(state.get("current_sprint_index") or 0)
    attempts = [
        entry for entry in state.get("sprint_attempts") or []
        if isinstance(entry, dict) and entry.get("sprint_index") == index
    ]
    return f"{index}:{len(attempts)}"


def _a_dispute_is_due(state: Any) -> bool:
    """Whether this re-plan of a failed attempt should first have its failing locked tests judged."""
    from app.graph.acceptance_nodes import MAX_SUITE_REPAIRS

    if _the_last_failed_attempt_at_this_sprint(state) is None:
        return False
    if [c for c in state.get("revision_comments") or [] if str(c).strip()]:
        return False
    if _this_attempt(state) in (state.get("disputed_sprints") or []):
        return False
    if int(state.get("suite_repairs") or 0) >= MAX_SUITE_REPAIRS:
        return False
    return bool(_the_locked_tests_still_failing(state))


def _blames_a_locked_test(state: Any, blockers: list[str]) -> bool:
    """Whether a fix stage's blockers name a file of the locked acceptance suite. Never raises."""
    try:
        from app.acceptance import suite as acceptance_suite

        root = state["repository"].root_path
        if not acceptance_suite.is_locked(root):
            return False
        names = {path.name for path in acceptance_suite.suite_files(root)}
        text = " ".join(map(str, blockers or []))
        return any(name and name in text for name in names)
    except Exception:  # noqa: BLE001 - not blamed is how it was before
        return False


def _a_dispute_may_be_held_now(state: Any) -> bool:
    """Whether this attempt may have its failing locked tests judged before it ends.

    Measured on one run: sprint 4's locked responsive test had a logic error -
    it switched to the "Active" view and expected no items, though the item it
    had added was active. Every fix stage in two rounds - three of them sent to
    defects already fixed - changed nothing and named that test as the reason,
    and each defect was left open. A dispute waited for the attempt to fail,
    which cost the attempt's remaining rounds first. Once per attempt, as at a
    re-plan, and only while the suite may still be repaired.
    """
    from app.graph.acceptance_nodes import MAX_SUITE_REPAIRS

    if _this_attempt(state) in (state.get("disputed_sprints") or []):
        return False
    if int(state.get("suite_repairs") or 0) >= MAX_SUITE_REPAIRS:
        return False
    return bool(_the_locked_tests_still_failing(state))


#: What a reverted fix leaves on its defect's actual behaviour. See the
#: `broke` branch of `defect_remediation_node`.
_REVERTED_FOR = re.compile(r"A fix was tried and reverted, because it broke what passed before it: (.+?)\.(?:\n|$)")


def _a_locked_test_two_fixes_broke(cycle: Any) -> str:
    """A locked acceptance test that two fixes in this attempt were reverted for breaking, or "".

    Measured on one run: the locked delete test added "Task one" then "Task two"
    and expected "Task two" to remain after deleting the first item - new
    items last - while the locked list test expected the second item added to
    come first. Each fix that made one pass broke the other and was reverted,
    twice in one round; the attempt would have spent its rounds on it before the
    QA lead saw it. One revert is a bad fix; two for the same locked test is two
    locked tests asking for opposite things.
    """
    from collections import Counter

    counts: Counter[str] = Counter()
    for defect in getattr(cycle, "defects", None) or []:
        for match in _REVERTED_FOR.finditer(str(getattr(defect, "actual_behavior", "") or "")):
            for name in match.group(1).split("; "):
                if name.strip().startswith("acceptance:"):
                    counts[name.strip()] += 1
    return next((name for name, count in counts.most_common() if count >= 2), "")


def _with_the_reason(request: dict, reason: str) -> dict:
    """A dispute request with why it is being held now, when there is a reason to give."""
    if reason.strip():
        request["messages"][-1]["content"] += f"\n\n--- Why this is judged now ---\n{reason.strip()}\n"
    return request


def _carried_here(state: Any) -> list[str]:
    """What earlier sprints carried to this one's lead to take or decline."""
    return [str(item) for item in state.get("carried_forward") or [] if str(item).strip()]


def _only_what_was_carried(why: str) -> str:
    """The lead's brief for a sprint whose criteria pass but that was carried work.

    A sprint closed with nothing to build was closed before its lead saw what
    the sprint before carried to it, so a finding that did not gate - a
    review's minor one, an adopted item a specialist found not built - was
    dropped rather than taken or declined. Measured on one run: thirteen
    adopted UI/UX and database items reported not built after sprint 1, and
    sprints 2 and 3 closed with nothing to build without anyone reading them.
    """
    first = next((line for line in why.splitlines() if line.strip()), why)
    return (
        "\n\n--- Every criterion due by this sprint already passes ---\n"
        f"{first}\n"
        "So this sprint's only work is what earlier sprints carried to it, listed above. Take "
        "each item that still holds as a work order to the role that owns it, and decline the "
        "rest in `carried_forward_decisions` with the reason. That no test checks an item is "
        "not a reason to decline it. Keep every name the brief gives and every test passing. If you take none, hand out no work orders: the sprint then "
        "closes with nothing to build."
    )


def _close_a_sprint_with_nothing_to_build(state: WorkflowGraphState, why: str) -> dict[str, Any]:
    """Accept a sprint whose criteria already pass, the way an accepted sprint is closed.

    See `acceptance_nodes.sprint_already_done`. The same decision record,
    evidence and accepted baseline as a sprint the milestone review accepted,
    and the same route on: the person's own sprint review if they asked for
    it, the next sprint, or the release.
    """
    from app.decisions import record_decision
    from app.graph import delivery, engineering

    sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
    index = int(state.get("current_sprint_index") or 0)
    goal = str(getattr(sprints[index], "goal", "") or "") if index < len(sprints) else ""
    accepted: dict[str, Any] = {}
    record_decision(
        state, accepted, point="sprint",
        question=f"Is sprint {index + 1} done?",
        options=["accept without new work", "plan work for it"],
        decision="accept without new work",
        rationale=why,
    )
    logger.info("Sprint %d needs no new work: its criteria already pass", index + 1)
    delivery.write_evidence({**state, **accepted}, index + 1, goal)
    engineering.accepted_state(state["repository"].root_path)
    if _review_enabled(state, SPRINT_REVIEW):
        next_stage = "user_review_sprint"
    elif index < len(sprints) - 1:
        next_stage = "sprint_advance"
    else:
        next_stage = "release"
    return _handing_on(**accepted, stage=next_stage, nothing_left_but_carried=None)


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
    # The last rung of the ladder decides rather than simply stopping: see
    # `app.graph.escalation`. It still stops a run that cannot ship most of
    # its criteria, or has nothing to measure them with.
    return _handing_on(stage="escalation", escalation={"error": error}, error=None, **fields)


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
    from app.decisions import record_decision

    record_decision(
        state, update, point=review_point,
        question=f"Does the reviewer accept the {review_point.replace('_', ' ')}?",
        options=["approve", "request changes", "skip"],
        decision={"approve": "approve", "skip": "skip", "request_changes": "request changes"}.get(
            decision_type, str(decision_type)
        ),
        rationale="Decided by the reviewer at the review gate.",
        decided_by="user",
        comment=str(comment or ""),
    )
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


def _the_stack_pack_for(state: Any, update: dict[str, Any]) -> dict[str, Any]:
    """The stack pack this run will be scaffolded from, and the stack aligned with it.

    Chosen when the stack is, so the stack document - and every review that
    reads it - describes what will actually be built and tested. A stack no pack
    fits is set up by the agents, as every run was before packs existed. See
    `app.stacks`.
    """
    from app.decisions import record_decision
    from app.stacks import aligned_stack, choose_pack, support_tier

    chosen = update.get("stack_selection")
    stack = getattr(chosen, "technology_stack", None)
    if stack is None:
        return {}
    brief = getattr(state.get("document"), "text", "") or ""
    pack = choose_pack(
        stack, f"{brief}\n{_as_text(state.get('product_intake'))}",
        rationale=str(getattr(chosen, "rationale", "") or ""),
    )
    out: dict[str, Any] = {"stack_pack": pack.name if pack else None}
    if pack is not None:
        aligned = aligned_stack(stack, pack)
        if aligned != stack:
            logger.info("Stack pack %s chosen; recording its framework and test runners in the stack", pack.name)
            out["stack_selection"] = chosen.model_copy(update={"technology_stack": aligned})
    else:
        logger.info("No stack pack fits this stack; the agents will set the project up")
    final = getattr(out.get("stack_selection", chosen), "technology_stack", stack)
    record_decision(
        state, out, point="stack",
        question="What is the product built with?",
        options=[pack.title] if pack else [],
        decision=(
            f"{getattr(final, 'language', '')} / {getattr(final, 'framework', '')}"
            + (f" - {pack.title}" if pack else " - no stack pack fits; the agents set the project up")
        ),
        rationale=support_tier(pack) + "\n" + str(getattr(chosen, "rationale", "") or ""),
    )
    return out


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

    # The model for judgement: the architect, QA, the reviews, the test rounds
    # and the fixes. The default model unless one is configured - see
    # `app.models.roles`. Built when the run supplies no model (the stages
    # then build the default one themselves) or a real one; a test's model
    # name or fake comes back unchanged.
    from app.models.roles import build_judgement_model

    judgement_model = (
        build_judgement_model(model) if model is None or isinstance(model, BaseChatModel) else model
    )

    def _the_model_for_this_attempt(state: Any) -> Any:
        """A rung of the escalation ladder: a sprint being tried again after a
        re-plan, a sent-back review, a held release or an escalation is built on
        the judgement model, not the default one."""
        retried = (
            int(state.get("sprint_replan_count") or 0) >= 1
            or int(state.get("milestone_revision_count") or 0) >= 2
            or int(state.get("release_attempts") or 0) >= 1
            or int(state.get("escalation_count") or 0) >= 1
        )
        return judgement_model if retried else model

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
        from app.stacks import supported_stacks_note

        document = state.get("document")
        constraints = constraints_note(getattr(document, "text", "") or "")
        request = {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"{constraints}"
                        f"{supported_stacks_note()}"
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
            next_stage="specialist_consultation",
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
                    ),
                    # The prose with it, or the document argues against its
                    # own field. See `the_rationale_for_the_corrected_runner`.
                    "rationale": the_rationale_for_the_corrected_runner(
                        getattr(chosen, "rationale", ""), corrected
                    ),
                }
            )

        # Rendered from the decision, like every other document the workflow
        # keeps. On one run this stage still wrote its own: it printed the
        # selection into the conversation, wrote `docs/technology_stack.md`,
        # printed it again, wrote again - five identical writes, and the repeat
        # guard ended the run at stage three. The same shape had already cost
        # earlier runs their technical lead and their architecture reviewer,
        # in the one stage that had not been converted.
        update.update(_the_stack_pack_for(state, update))
        _record_document(
            state,
            "docs/technology_stack.md",
            render_document("technology_stack", o=update["stack_selection"]),
        )
        return update

    def specialist_consultation_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        """Ask each specialist this product needs for advice, one per entry. See `app.agents.specialist_advice`."""
        from app.agents.specialist_advice import advice_from, build_advice_request, roles_to_consult

        brief = getattr(state.get("document"), "text", "") or ""
        roles = list(state.get("consultation_roles") or roles_to_consult(
            getattr(state.get("stack_selection"), "technology_stack", None), brief
        ))
        advice = dict(state.get("specialist_advice") or {})
        pending = [role for role in roles if role not in advice]
        if not pending:
            return _handing_on(stage="principal_architect", consultation_roles=roles, specialist_advice=advice)
        role = pending[0]
        agent = create_specialist_advice_agent(
            role, model=judgement_model, checkpointer=shared_checkpointer,
            repo_root=repo_root, allow_subdirectories=allow_subdirectories,
        )
        update = _run_gated_agent(
            state,
            config,
            stage_name=f"consult_{role}",
            agent=agent,
            initial_request=build_advice_request(
                role, brief, _as_text(state.get("product_intake")), _as_text(state.get("stack_selection"))
            ),
            output_key="__advice__",
            next_stage="specialist_consultation",
        )
        if _hand_back(update, "__advice__"):
            return update
        advice[role] = advice_from(update.pop("__advice__"))
        logger.info(
            "Consulted the %s specialist before the specification: %d recommendation(s)",
            role, len(advice[role]),
        )
        return _handing_on(**{
            **update,
            "consultation_roles": roles,
            "specialist_advice": advice,
            "stage": "specialist_consultation" if len(pending) > 1 else "principal_architect",
        })

    def principal_architect_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        missing = _missing_upstream(state, "product_intake", "tools_models")
        if missing is not None:
            return missing
        agent = create_principal_architect_agent(model=judgement_model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)

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
                advice=state.get("specialist_advice"),
            )
        else:
            request = build_architecture_request(
                _as_text(state.get("product_intake")),
                _as_text(state.get("tools_models")),
                _as_text(state.get("stack_selection")),
                state["repository"],
                state["document"],
                advice=state.get("specialist_advice"),
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

            if state.get("specification_repair_count", 0) and previous_specification is not None:
                update["technical_specification"] = _with_the_sections_it_dropped(
                    update.get("technical_specification"), previous_specification
                )

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

                from app.agents.specialist_advice import what_the_specification_owes

                unrunnable = testing_nobody_can_run(update.get("technical_specification"))
                owed = what_the_specification_owes(
                    update.get("technical_specification"), state.get("specialist_advice")
                )
                if owed and not unrunnable and repairs < MAX_SPECIFICATION_REPAIRS:
                    # The specialists were asked; an answer that ignores them
                    # leaves the advice where nobody reads it.
                    update["specification_repair_count"] = repairs + 1
                    update["stage"] = "principal_architect"
                    update["revision_comments"] = [
                        "The specification does not answer the specialists' advice:\n"
                        + "\n".join(f"- {problem}" for problem in owed)
                        + "\nReturn the whole specification with those sections completed; "
                        "change nothing else."
                    ]
                elif unrunnable and repairs < MAX_SPECIFICATION_REPAIRS:
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
        agent = create_architecture_reviewer_agent(model=judgement_model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
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
            from app.decisions import record_decision

            record_decision(
                state, update, point="technical_specification",
                question="Is the specification ready to build from?",
                options=["approve", "send it back to the architect"],
                decision="approve",
                rationale=(
                    "The architecture reviewer approved it."
                    if review.status == "approved"
                    else f"Approved with {len(review.findings)} finding(s), none of them blocking."
                ),
            )
            # The mandatory gate passed. Only now may an optional human review
            # session run; it can never substitute for this gate.
            update["stage"] = (
                "user_review_specification" if _review_enabled(state, SPECIFICATION_REVIEW) else "scaffold"
            )
        else:
            revision_count = state.get("architecture_revision_count", 0) + 1
            update["architecture_revision_count"] = revision_count
            if revision_count >= MAX_ARCHITECTURE_REVISIONS:
                # Decided, not stopped: see `app.graph.escalation`. The run used
                # to fail here - one stored run after six revisions - although
                # the acceptance suite, written from the brief, is what decides
                # whether the product works. Open design points are a risk to
                # record, or a question for the person who asked to be asked.
                outstanding = [_format_finding(f) for f in blocking]
                update["stage"] = "escalation"
                update["error"] = None
                update["escalation"] = {
                    "kind": "design",
                    "findings": outstanding,
                    "error": (
                        f"The architecture reviewer still asked for changes to the specification "
                        f"after {MAX_ARCHITECTURE_REVISIONS} revisions."
                    ),
                }
            else:
                update["stage"] = "principal_architect"
        return update

    def user_review_specification_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return _run_review_gate(
            state,
            config,
            review_point=SPECIFICATION_REVIEW,
            artifact_id="technical-specification",
            approved_next="scaffold",
            changes_next="principal_architect",
        )

    def scrum_master_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        missing = _missing_upstream(state, "technical_specification")
        if missing is not None:
            return missing
        agent = create_scrum_master_agent(model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
        spec_text = _as_text(state.get("technical_specification"))
        measures = _what_the_sprints_must_deliver(state.get("product_intake"))
        gaps_already_asked_about = list(state.get("sprint_plan_gaps") or [])
        built_ahead_asked_about = list(state.get("sprint_plan_built_ahead") or [])
        from app.acceptance import suite as acceptance_suite
        from app.acceptance.requests import criteria_text as numbered_criteria

        root_path = state["repository"].root_path
        request = build_sprint_planning_request(
            spec_text,
            root_path,
            success_measures=measures,
            gaps=gaps_already_asked_about,
            acceptance_criteria=(
                numbered_criteria(acceptance_suite.criteria(root_path), acceptance_suite.deferred(root_path))
                if acceptance_suite.is_locked(root_path)
                else ""
            ),
            built_ahead=built_ahead_asked_about,
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
            earlier = state.get("sprint_plan") if gaps_already_asked_about else None
            if earlier is not None and how_much_a_plan_leaves_out(
                update["sprint_plan"], measures
            ) > how_much_a_plan_leaves_out(earlier, measures):
                # Asked once more, and the answer leaves out more than the plan
                # it replaces. One run's second plan dropped its coverage lines
                # altogether, and the run was failed for a plan that "assigns
                # none" when the first had assigned all ten. The milestone plan
                # already keeps the better of its attempts; so does this.
                logger.warning(
                    "The re-planned sprint plan leaves out more than the plan it "
                    "replaces; keeping the earlier plan"
                )
                update["sprint_plan"] = earlier
            update["sprint_plan"], folded = with_setup_folded_into_the_sprint_that_needs_it(
                update["sprint_plan"], measures
            )
            if folded:
                logger.warning(
                    "Sprint plan held %d sprint(s) no success measure is assigned to; "
                    "folded into the next sprint: %s",
                    len(folded), "; ".join(goal[:80] for goal in folded),
                )
            from app.agents.scrum_master import with_capped_sprint_count
            criteria_count = len(acceptance_suite.criteria(root_path))
            update["sprint_plan"], capped_folded = with_capped_sprint_count(
                update["sprint_plan"], criteria_count
            )
            if capped_folded:
                logger.info(
                    "Sprint plan capped to lean sprint count for %d criteria; "
                    "folded trailing sprint(s): %s",
                    criteria_count, "; ".join(goal[:80] for goal in capped_folded),
                )
            unnamed = capabilities_the_plan_never_names(
                update["sprint_plan"], _without_the_mvp_features(measures)
            )
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
                # The plan is kept, so the answer to this can be compared with it.
                return _handing_on(
                    stage="scrum_master",
                    sprint_plan_gaps=missing,
                    sprint_plan=update["sprint_plan"],
                )
            criteria_to_assign = [
                c for c in acceptance_suite.criteria(root_path)
                if c.id not in acceptance_suite.deferred(root_path)
            ]
            if _the_plan_assigns_nothing(unassigned, measures) and not criteria_to_assign:
                # Not let through. A plan that leaves one measure out is judged
                # by the milestone review; a plan that assigns none has no
                # review that will ever look at the whole brief with a sprint
                # still to come. One run continued on such a plan - a single
                # foundation sprint - built it, and completed with a product
                # that could add a task and do nothing else that was asked for.
                #
                # Only when there are no acceptance criteria. With them, every
                # criterion is given to a sprint just below, whatever the plan
                # said, and each sprint is done only when its criteria pass -
                # so that product could no longer complete. Stopping here
                # threw away a plan the harness was about to complete itself.
                return _handing_on(
                    stage="failed",
                    error=(
                        f"The sprint plan assigns none of the {len(measures)} things the "
                        "release must deliver to any sprint, after being asked once "
                        "more. Building from it would deliver a product nothing was "
                        "planned to complete. Resume to plan the sprints again."
                    ),
                )
            if missing:
                logger.warning(
                    "Sprint plan still leaves success measures %s unassigned after one "
                    "re-plan; continuing, and the milestone review will judge it", missing
                )
            update["sprint_plan_gaps"] = []
            update["current_sprint_index"] = 0
            # Every criterion of the locked suite belongs to exactly one sprint.
            from app.agents.scrum_master import with_every_criterion_assigned

            numbered = criteria_to_assign
            update["sprint_plan"], assignment_notes = with_every_criterion_assigned(
                update["sprint_plan"], [c.id for c in numbered], {c.id: c.text for c in numbered}
            )
            if assignment_notes:
                logger.info("Sprint plan's criteria adjusted: %s", "; ".join(assignment_notes))
            # Once, as for the success measures: a sprint whose scope builds a
            # later sprint's criteria has its lead write work orders for them
            # and its builders build every sprint in the first. See
            # `scope_a_later_sprint_delivers`.
            from app.agents.scrum_master import scope_a_later_sprint_delivers

            ahead = scope_a_later_sprint_delivers(update["sprint_plan"], {c.id: c.text for c in numbered})
            if ahead and not built_ahead_asked_about:
                logger.warning("Sprint plan builds later sprints' work early; asking once more: %s", ahead)
                return _handing_on(
                    stage="scrum_master",
                    sprint_plan_built_ahead=ahead,
                    sprint_plan=update["sprint_plan"],
                )
            if ahead:
                logger.warning(
                    "Sprint plan still builds later sprints' work early after one re-plan; "
                    "continuing, and each sprint's lead and builders are told what later "
                    "sprints deliver: %s", ahead,
                )
            update["sprint_plan_built_ahead"] = []
            from app.decisions import record_decision

            planned = list(getattr(update["sprint_plan"], "sprints", None) or [])
            record_decision(
                state, update, point="sprint_plan",
                question="How is the work split into sprints?",
                decision=f"{len(planned)} sprint(s): " + "; ".join(
                    f"{number}. {getattr(sprint, 'goal', '')}"
                    + (f" ({', '.join(sprint.criteria)})" if getattr(sprint, "criteria", None) else "")
                    for number, sprint in enumerate(planned, 1)
                ),
                rationale=(
                    "Planned by the scrum master"
                    + (f"; still unassigned after one re-plan: {missing}" if missing else
                       "; every success measure is assigned a sprint")
                    + "."
                )[:1500],
            )
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

        # A failed attempt's locked tests are judged once before it is planned
        # again: one that no right product could pass goes back to QA. See
        # `app.agents.suite_dispute`.
        if _a_dispute_is_due(state):
            return _handing_on(stage="acceptance_dispute")

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
        # Every criterion due already passes, but an earlier sprint carried work
        # here: the lead takes or declines each item, and a plan that takes none
        # closes the sprint. See `_only_what_was_carried`.
        nothing_else = "" if revising else str(state.get("nothing_left_but_carried") or "")
        if not revising and not nothing_else:
            from app.graph import acceptance_nodes as nothing_left

            why = nothing_left.sprint_already_done(state)
            if why:
                if not _carried_here(state):
                    return _close_a_sprint_with_nothing_to_build(state, why)
                nothing_else = why
        if revising:
            request = build_milestone_revision_request(
                previous_milestone.model_dump_json(indent=2), revision_comments
            )
        else:
            request = build_milestone_planning_request(
                plan_text, current_goal, state["repository"].root_path,
                specification=state.get("technical_specification"),
                carried_forward=_carried_to_this_plan(state),
                lessons=state.get("lessons") or [],
                last_attempt=_the_last_failed_attempt_at_this_sprint(state),
            )
        # The previous answer was not ready to hand out: say exactly why, with
        # the plan it was, so this attempt fixes it rather than starting over.
        from app.graph import acceptance_nodes

        due_brief = acceptance_nodes.criteria_brief(state)
        if due_brief:
            request["messages"][-1]["content"] += due_brief
        # Recorded here too, not only when the builders start, so the lead's own
        # listing and snapshot tell a later sprint's tests from this one's.
        from app.agents.specialists import fixes_to_keep_section

        kept = fixes_to_keep_section(_the_fixes_to_keep(state))
        if kept:
            request["messages"][-1]["content"] += (
                "\n\n" + kept + "No work order undoes one of these, even to match the specification.\n"
            )
        later_brief = _the_later_sprints_brief(state)
        if later_brief:
            request["messages"][-1]["content"] += (
                "\n\n" + later_brief
                + "No work order builds what only those criteria need, even where this "
                "sprint's scope lists it: their sprint plans that work.\n"
            )
        if nothing_else:
            request["messages"][-1]["content"] += _only_what_was_carried(nothing_else)
        # What the harness set up and owns. Without it one run's lead wrote a
        # work order to edit the acceptance configuration, which the harness
        # put back - the whole work order wasted.
        from app.agents.specialists import project_contract

        owned = project_contract(state["repository"].root_path)
        if owned:
            request["messages"][-1]["content"] += (
                "\n\n" + owned
                + "No work order may target a file the harness keeps or the locked acceptance "
                "suite; a change to either is put back."
            )
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
        if nothing_else and not list(getattr(update["milestone_plan"], "delegated_tasks", None) or []):
            decisions = [
                str(line) for line in getattr(update["milestone_plan"], "carried_forward_decisions", None) or []
                if str(line).strip()
            ]
            # Once: a lead that declines only because no test asks for the
            # item is asked again with that reason ruled out.
            from app.analysis.work_orders import declined_because_untested, untested_is_no_reason

            untested = declined_because_untested(decisions)
            carried = _carried_to_this_plan(state)
            # Silence is no decision either: one run's lead returned no work
            # orders and no decisions on eight carried items, and the sprint
            # closed as if it had declined them.
            unanswered = len(decisions) < len(carried)
            retries = dict(state.get("structured_retries") or {})
            asked = f"{_UNTESTED_DECLINES}:{state.get('current_sprint_index', 0)}"
            if (untested or unanswered) and not retries.get(asked):
                retries[asked] = 1
                problems = [untested_is_no_reason(untested)] if untested else []
                if unanswered:
                    problems.append(
                        f"{len(carried)} item(s) were carried here and `carried_forward_decisions` "
                        f"records {len(decisions)}. Give one line per item: the work order that "
                        "takes it, or why it no longer holds."
                    )
                logger.warning(
                    "The lead answered %d of %d carried item(s), %d declined as untested; asking again",
                    len(decisions), len(carried), len(untested),
                )
                return _handing_on(
                    stage="technical_lead",
                    structured_retries=retries,
                    nothing_left_but_carried=nothing_else,
                    work_order_problems=problems,
                    unready_plan=update["milestone_plan"].model_dump_json(indent=2),
                )
            # The lead's decisions first: the record keeps the rationale's
            # first 1500 characters, and the suite's summary after them is long.
            return _close_a_sprint_with_nothing_to_build(
                state,
                "The lead took none of what earlier sprints carried here"
                + (": " + "; ".join(decisions) if decisions else ".")
                + "\n" + nothing_else,
            )
        # Only a readiness retry carries it on; a dispatched plan is a sprint's own.
        update["nothing_left_but_carried"] = None

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
            with_the_project_directory_cd_dropped,
        )

        update["milestone_plan"] = with_test_cases_from_its_criteria(
            with_the_project_directory_cd_dropped(
                with_paths_inside_the_project(update["milestone_plan"], state["repository"].root_path),
                state["repository"].root_path,
            )
        )
        problems = readiness_problems(
            update["milestone_plan"],
            state["repository"].root_path,
            carried_forward=[] if revising else _carried_to_this_plan(state),
            # A revision answers the review's findings; the sprint's first plan
            # was the one held to the files its scope names, and those were
            # built - under the names that plan chose. One run's revision was
            # sent back twice for `pure-functions.mjs`, a name from the scope
            # the first plan had built as `app.mjs`.
            sprint_scope="" if revising else _what_this_sprint_builds(state),
            sprint_goals=[
                str(getattr(sprint, "goal", "") or "")
                for sprint in (getattr(state.get("sprint_plan"), "sprints", None) or [])
            ],
            sprint_index=state.get("current_sprint_index", 0),
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
                    nothing_left_but_carried=nothing_else or None,
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
        from app.analysis.work_orders import with_the_harness_s_files_left_out

        update["milestone_plan"] = with_the_harness_s_files_left_out(
            update["milestone_plan"], state["repository"].root_path
        )
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
        # And a command whose file another work order writes - see
        # `app.analysis.work_orders.with_borrowed_files_noted`.
        from app.analysis.work_orders import with_borrowed_files_noted

        update["milestone_plan"] = with_borrowed_files_noted(update["milestone_plan"])

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
        if revising and previous_milestone is not None:
            update["sprint_earlier_plans"] = [
                *(state.get("sprint_earlier_plans") or []),
                _what_a_plan_did(previous_milestone, state.get("remediation")),
            ]
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
                task.specialist_role, model=_the_model_for_this_attempt(state), checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories
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
                interface_design=_the_interface_design_for(state, task),
                later_sprints_brief=_the_later_sprints_brief(state),
                earlier_fixes=_the_fixes_to_keep(state, task),
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

        # Every delegated task is done, so the increment is built. CI and a
        # code review read it first (`app.graph.engineering`); verification is
        # then its own stage (Step 5.4): the Test Engineer runs the tests and
        # turns failures into tracked, owned defects.
        return _handing_on(stage="ci_gate")

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
            task.specialist_role, model=_the_model_for_this_attempt(state), checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories
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
            interface_design=_the_interface_design_for(state, task),
            later_sprints_brief=_the_later_sprints_brief(state),
            earlier_fixes=_the_fixes_to_keep(state, task),
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
        return _handing_on(stage="ci_gate", specialist_pauses={}, queued_decisions={})

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
        # The harness runs the locked acceptance suite once per round, on the
        # round's first entry (a resume after an approval pause is the same
        # round), and hands the measured result to the test engineer.
        from app.graph import acceptance_nodes

        acceptance_text = ""
        beyond_repair: list[str] = []
        if not state.get("pending_inner_thread_id"):
            # Before the round, not after a pause inside it: the stages that
            # wrote these have all finished, and the round should measure the
            # product without them.
            _clear_the_throwaways(state["repository"].root_path)
            acceptance_text, cannot_pass = acceptance_nodes.acceptance_for_round(state)
            # A locked test that cannot pass whatever is built is not a
            # product defect: no fix can close it. Repaired by QA first.
            reopened = acceptance_nodes.reopen_the_suite_for(state, cannot_pass)
            if reopened is not None:
                return reopened
            # And once the suite may not be repaired again, the round is told,
            # and its defects about them go to no fixer.
            beyond_repair = acceptance_nodes.beyond_repair(state, cannot_pass)
            if beyond_repair:
                logger.warning(
                    "Locked tests of %s cannot pass and the suite's repairs are spent; "
                    "their failures are not product defects", ", ".join(beyond_repair),
                )
                acceptance_text = "\n\n".join(
                    part for part in (acceptance_text, acceptance_nodes.beyond_repair_note(cannot_pass, beyond_repair))
                    if part
                )
        failing_due, _ = acceptance_nodes._failing_due(state)
        # The round is the harness's own only on evidence: a locked suite whose
        # last run happened and passes everything due, the unit tests run and
        # passed, and nothing else proven wrong. Anything unknown - no locked
        # suite, a run that wrote no report, no unit command, a check that
        # failed to answer - is the testing specialist's round, as before.
        saved_run = acceptance_nodes.suite.last_result(state["repository"].root_path) or {}
        skip_agent = (
            not state.get("pending_inner_thread_id")
            and acceptance_nodes.suite.is_locked(state["repository"].root_path)
            and bool(saved_run.get("ran"))
            and not failing_due
            and not cannot_pass
            and not state.get("review_defects")
        )
        if skip_agent:
            unit_ok, _ = _run_unit_tests_procedurally(state["repository"].root_path)
            skip_agent = unit_ok is True
        still_proven: list[str] = []
        if skip_agent:
            try:
                from app.agents.specialists import what_the_files_already_prove

                still_proven = what_the_files_already_prove(
                    state["repository"].root_path,
                    getattr(state.get("stack_selection"), "technology_stack", None),
                    [
                        *(getattr(milestone, "milestone_scope", None) or ()),
                        *(
                            getattr(task, "task_description", "")
                            for task in (getattr(milestone, "delegated_tasks", None) or ())
                        ),
                    ],
                    _what_later_sprints_build(state),
                    getattr(state.get("document"), "text", "") or "",
                )
            except Exception:  # noqa: BLE001 - a check that cannot answer is no evidence
                logger.debug("Could not read what the files already prove", exc_info=True)
                skip_agent = False

        if skip_agent and not still_proven:
            logger.info(
                "test_round_%d: all acceptance criteria due and unit tests passed procedurally with 0 defects; skipping specialist LLM invocation",
                test_round,
            )
            update = {
                "__test_result__": SpecialistOutput(
                    changed_files=[],
                    defects=[],
                    decisions=[
                        "The harness ran this round itself: the locked suite passes every criterion "
                        "due, and the unit tests pass."
                    ],
                )
            }
        else:
            changed_files = _the_files_this_milestone_changed(state, outputs)

            agent = create_specialist_agent(
                "testing", model=judgement_model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories
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
                brief=getattr(state.get("document"), "text", "") or "",
                acceptance=acceptance_text,
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
        # CI's regressions and the code review's findings for this batch, once.
        reported: list[ReportedDefect] = _each_defect_once(
            [*raised_by("test round", test_result.defects), *(state.get("review_defects") or [])]
        )
        if len(reported) < len(test_result.defects):
            logger.warning(
                "test_round_%d reported %d defect(s), %d of them repeats; keeping %d",
                test_round, len(test_result.defects),
                len(test_result.defects) - len(reported), len(reported),
            )
        # Read after the round, so a problem it fixed - a test config is its to
        # change - is not reported back to it as still there.
        try:
            from app.agents.specialists import what_the_files_already_prove

            still_proven = what_the_files_already_prove(
                state["repository"].root_path,
                getattr(state.get("stack_selection"), "technology_stack", None),
                [
                    *(getattr(milestone, "milestone_scope", None) or ()),
                    *(
                        getattr(task, "task_description", "")
                        for task in (getattr(milestone, "delegated_tasks", None) or ())
                    ),
                ],
                _what_later_sprints_build(state),
                getattr(state.get("document"), "text", "") or "",
            )
            left_out = _proven_problems_the_round_left_out(still_proven, reported, milestone)
        except Exception:  # noqa: BLE001 - the round's own report stands
            logger.debug("Could not compare the round's report with what is proven", exc_info=True)
            left_out = []
        if left_out:
            logger.warning(
                "test_round_%d left out %d problem(s) it was handed as proven; recording them as defects",
                test_round, len(left_out),
            )
            reported = reported + raised_by("cross-file check", left_out)
        # How the page is presented, where a script can prove it: an interface
        # nothing styles, or a page that does not fit the phone the brief asks
        # for. Before the later-sprint filter, so a plan that styles later keeps
        # that work for the sprint that builds it.
        try:
            reported = reported + raised_by("page check", acceptance_nodes.interface_defects(state))
        except Exception:  # noqa: BLE001 - the round's own report stands
            logger.debug("Could not check how the page is presented", exc_info=True)
        reported, later_work = _defects_a_later_sprint_builds(reported, state)
        if later_work:
            logger.warning(
                "test_round_%d reported %d defect(s) about work a later sprint builds; "
                "left for that sprint, not fixed in this one: %s",
                test_round, len(later_work),
                "; ".join(str(getattr(item, "description", ""))[:60] for item in later_work[:4]),
            )
        reported, unfixable = _defects_only_about(reported, beyond_repair)
        if unfixable:
            logger.warning(
                "test_round_%d reported %d defect(s) only about locked tests that cannot pass and may "
                "not be repaired again; set aside: %s",
                test_round, len(unfixable),
                "; ".join(str(getattr(item, "description", ""))[:60] for item in unfixable[:4]),
            )
        try:
            unreported_criteria = acceptance_nodes.failing_due_defects(state, reported)
        except Exception:  # noqa: BLE001 - the round's own report stands
            logger.debug("Could not compare the round's report with the acceptance suite", exc_info=True)
            unreported_criteria = []
        if unreported_criteria:
            logger.warning(
                "test_round_%d did not report %d failing acceptance criteria; recording them as defects",
                test_round, len(unreported_criteria),
            )
            reported = reported + raised_by("acceptance suite", unreported_criteria)
        # One problem, one fixer. See `_one_defect_per_cause`.
        reported = _one_defect_per_cause(reported)
        if not reported:
            unreported = _a_suite_failure_the_round_did_not_report(
                state["repository"].root_path, f"test_round_{test_round}",
                but_the_acceptance_suite=bool(unfixable),
            )
            if unreported is not None:
                logger.warning(
                    "test_round_%d reported no defects, but its last run of the suite "
                    "failed; recording that as a defect", test_round,
                )
                reported = raised_by("test command", [unreported])
        cycle = state.get("remediation") or start_remediation(
            milestone.selected_sprint_goal, max_attempts=MAX_REMEDIATION_ATTEMPTS
        )
        # An earlier round's defect whose criteria this round's measurement
        # finds passing is fixed, whichever fix did it, and does not count
        # against the sprint as still open.
        cycle = _closed_by_this_round_s_measurement(state, cycle, test_round)
        # The test command this round left failing, if it left one. See
        # `_needs_a_new_test`.
        caught_by, _ = _the_test_command_this_stage_left_failing(
            state["repository"].root_path, f"test_round_{test_round}"
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
                regression_test_required=_needs_a_new_test(item, caught_by),
                caught_by=caught_by,
                source=str(getattr(item, "source", "") or ""),
                failing_criteria=_failing_criteria_it_names(state, item),
            )
            for item in reported
        ]

        from app.observability import defect_ledger

        for position, item in enumerate(new_defects, start=len(cycle.defects)):
            defect_ledger.note("raised", f"test_round_{test_round}", defect=item, round_=test_round, index=position,
                                sprint=state.get("current_sprint_index", 0))
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
            # The same exit as every other exhausted sprint: planned again,
            # as often as the revision limit allows, with this round on its
            # record. Failing the run from here skipped both.
            logger.warning("Sprint is out of remediation attempts: %s", exc)
            try:
                from app.sprint import TestRunRecord

                spent = cycle.model_copy(update={
                    "test_runs": [
                        *cycle.test_runs,
                        TestRunRecord(
                            command=["specialist", "testing", f"round-{test_round}"],
                            passed=not new_defects,
                            summary=f"{len(new_defects)} defect(s) found",
                        ),
                    ],
                    "defects": [*cycle.defects, *new_defects],
                    "escalated": True,
                })
            except Exception:  # noqa: BLE001 - the cycle as it stood is still evidence
                spent = cycle
            return _replan_or_escalate(
                state,
                {
                    "remediation": spent,
                    "test_round": test_round + 1,
                    "pending_approval": None,
                    "pending_inner_thread_id": None,
                    "pending_decision": None,
                },
                spent,
                "exhausted remediation attempts",
            )

        base_update: dict[str, Any] = {
            "remediation": cycle,
            "test_round": test_round + 1,
            "pending_approval": None,
            "pending_inner_thread_id": None,
            "pending_decision": None,
            "review_defects": [],
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

        The same limit, and a count of its own. It used to add to
        `milestone_revision_count`, the milestone review's, so a sprint whose
        tests took one re-plan reached its review with a revision already
        spent. Measured on one run: one re-plan, then two reviews - the first
        blocked on a `require` in an ES module, which was fixed; the second
        raised four findings, none of them the first's - and the run ended
        "after 3 revisions", ten minutes in, on the first review whose findings
        nobody had been given a chance to fix.
        """
        revision_count = state.get("sprint_replan_count", 0) + 1
        # Every defect still open ends its story here: the ledger had it
        # raised and nothing after, which reads like a round cut short.
        from app.observability import defect_ledger

        ending = "escalated to a person" if revision_count > MAX_MILESTONE_REVISIONS else "the sprint is planned again"
        for index, defect in enumerate(getattr(cycle, "defects", None) or []):
            if getattr(defect, "status", "") == "open":
                defect_ledger.note(
                    "left open", f"test_round_{state.get('test_round', 0)}", defect=defect,
                    round_=state.get("test_round", 0), index=index,
                    sprint=state.get("current_sprint_index", 0), detail=f"{why}; {ending}",
                )
        # The sprint as this round leaves it, not as it entered it. `state`
        # still holds the cycle from before the round just recorded, so a
        # summary written from it left out the round that ended the sprint and
        # the defect it found: one run's record read "Failed: exhausted
        # remediation attempts" over six of six tests passed, two bugs found,
        # two fixed, none open.
        state = {**state, **base_update, "remediation": cycle}  # type: ignore[assignment]
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
            return _escalate_to_a_human(
                state,
                error=(
                    f"Sprint '{getattr(cycle, 'sprint_goal', '?')}' was re-planned "
                    f"{MAX_MILESTONE_REVISIONS} times and still could not be "
                    f"accepted: {why}.\n\n{build_defect_report(cycle)}"
                ),
                **{**base_update, **summary},
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
            sprint_replan_count=revision_count,
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

        # Fixed already, by an earlier fix in this round: nothing for a fixer
        # to do, and a fixer told to fix what works finds other work.
        closed = _closed_if_an_earlier_fix_resolved_it(state, cycle, defect_index)
        if closed is not None:
            return closed

        agent = create_specialist_agent(
            defect.owner, model=judgement_model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories
        )
        from app.acceptance.junit import tags_in

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
            caught_by=getattr(defect, "caught_by", ""),
            # Only for a defect that is not itself a failing criterion.
            done_already=(
                []
                if [t for t in tags_in(str(defect.description or "")) if t.startswith(("AC-", "CR-"))]
                else acceptance_nodes.done_by_the_definition(state)
            ),
        )
        request["messages"][-1]["content"] += _what_a_fix_stage_must_leave_alone(state, defect)
        co_defects = _bundle_co_defects(cycle, defect_index)
        if co_defects:
            batch_lines = [
                "\n--- Related failures owned by your role to resolve in this same fix ---",
                "The harness measures each one after your fix; one still failing goes to its own fix.",
            ]
            for pos, co_d in co_defects:
                batch_lines.append(f"- Failure {pos + 1}: {co_d.description}")
                batch_lines.append(f"  Expected: {co_d.expected_behavior}")
                batch_lines.append(f"  Actual: {co_d.actual_behavior}")
            request["messages"][-1]["content"] += "\n".join(batch_lines) + "\n"
        # A fix that breaks what passed before it is reverted to exactly where
        # it started. The commit it starts from is taken on the stage's first
        # entry and carried across an approval pause. See `app.graph.engineering`.
        from app.graph import engineering

        fix_base = (
            str(state.get("fix_base_commit") or "")
            if state.get("pending_inner_thread_id")
            else engineering.before_a_fix(state["repository"].root_path, stage_name)
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
            update["fix_base_commit"] = fix_base
            return update  # paused waiting for approval on this fix

        fix_result: SpecialistOutput = update.pop("__fix_result__")
        broke = engineering.after_a_fix(
            state["repository"].root_path, fix_base, stage_name, defect.description
        )
        from app.observability import defect_ledger

        _note_the_bundled(
            co_defects, defect_index=defect_index, stage_name=stage_name,
            round_=state.get("test_round", 0), sprint=state.get("current_sprint_index", 0),
        )
        if broke:
            defect_ledger.note(
                "reverted", stage_name, defect=defect, round_=state.get("test_round", 0), index=defect_index,
                sprint=state.get("current_sprint_index", 0),
                detail=f"broke {len(broke)} test(s) that passed before it: {'; '.join(broke[:3])}",
            )
            noted = cycle.model_copy(update={"defects": [
                item.model_copy(update={
                    "actual_behavior": (
                        f"{item.actual_behavior}\nA fix was tried and reverted, because it broke "
                        f"what passed before it: {'; '.join(broke[:5])}."
                    )
                }) if position == defect_index else item
                for position, item in enumerate(cycle.defects)
            ]})
            contested = _a_locked_test_two_fixes_broke(noted)
            if contested and _a_dispute_may_be_held_now(state):
                logger.warning(
                    "Two fixes were reverted for breaking the locked test %s; the QA lead "
                    "judges the failing locked tests before the round goes on", contested,
                )
                return _handing_on(**{
                    **update,
                    "remediation": noted,
                    "defect_cursor": defect_index + 1,
                    "fix_base_commit": "",
                    "stage": "acceptance_dispute",
                    "dispute_returns_to": "test_and_triage",
                    "dispute_reason": (
                        f"Fixes for these failures were reverted, twice, because each broke "
                        f"`{contested}`, which passed before. Two locked tests may ask for "
                        "opposite things: a test that cannot pass while another one does is "
                        "one to name."
                    ),
                })
            return _handing_on(**{
                **update,
                "remediation": noted,
                "defect_cursor": defect_index + 1,
                "fix_base_commit": "",
            })
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
        if fix_result.blockers and not fix_result.changed_files:
            # Blocked and nothing changed: not a fix. Recorded as fixed, it was
            # closed with no change behind it, and a stage that could not
            # reply at all now answers this way (`_blocked_for_want_of_room`).
            # The next round measures it again.
            update["remediation"] = cycle
            defect_ledger.note(
                "left open", stage_name, defect=defect, round_=state.get("test_round", 0), index=defect_index,
                sprint=state.get("current_sprint_index", 0),
                detail="the fix stage changed nothing and reported: " + "; ".join(map(str, fix_result.blockers))[:300],
            )
        elif defect.regression_test_required and not regression_test:
            # No named regression test: the defect stays open on purpose. The
            # next test round will count this as another failed attempt, so the
            # bounded loop still terminates.
            update["remediation"] = cycle
            defect_ledger.note(
                "left open", stage_name, defect=defect, round_=state.get("test_round", 0), index=defect_index,
                sprint=state.get("current_sprint_index", 0),
                detail="the fix named no regression test",
            )
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
            defect_ledger.note(
                "fixed", stage_name, defect=defect, round_=state.get("test_round", 0), index=defect_index,
                sprint=state.get("current_sprint_index", 0),
                detail=(resolution or "") + (f" (verified by {verified_by})" if verified_by else " (no passing command recorded)"),
            )

        still_open = update["remediation"] is cycle
        if (
            still_open
            and _blames_a_locked_test(state, [*fix_result.blockers, *fix_result.decisions])
            and _a_dispute_may_be_held_now(state)
        ):
            # The fix stage left its defect open and says a locked test is
            # what cannot pass - in its blockers, or among its decisions beside
            # a change that did not make it pass. That is the QA lead's to
            # judge, now - not after the attempt has spent its rounds on it.
            # See `_a_dispute_may_be_held_now`.
            logger.warning(
                "Stage %s left its defect open and blames the locked suite; the QA lead "
                "judges its failing tests before the round goes on", stage_name,
            )
            update["specialist_outputs"] = outputs
            update["defect_cursor"] = defect_index + 1
            return _handing_on(**{**update, "stage": "acceptance_dispute", "dispute_returns_to": "test_and_triage"})
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
        if not _changes_any_code(changed_files) and not state.get("pending_inner_thread_id"):
            review = SecurityReviewOutput(status="passed", findings=[])
            from app.sprint.record import findings_of
            return _handing_on(
                stage="advice_review",
                security_review=review,
                sprint_findings=list(state.get("sprint_findings") or [])
                + findings_of(review, "security", state.get("milestone_revision_count", 0) + 1),
            )
        agent = create_security_reviewer_agent(model=judgement_model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
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
        review = _without_findings_about_the_harness_s_files(review, state["repository"].root_path)

        # Rendered from the decision, like the architecture and milestone
        # reviews. This was the last reviewer still holding a write tool with
        # no document of its own to render - the same latent shape that ended
        # one run at stage three when the stack selector finally used it.
        # It had never misbehaved; neither had the stack selector, until it did.
        from app.agents.security_reviewer import source_coverage

        shown, not_shown = source_coverage(changed_files, state["repository"].root_path)
        _record_document(
            state,
            "docs/security_review.md",
            render_security_review(review, shown, not_shown),
        )
        from app.sprint.record import findings_of

        return _handing_on(
            stage="advice_review",
            security_review=review,
            sprint_findings=list(state.get("sprint_findings") or [])
            + findings_of(review, "security", state.get("milestone_revision_count", 0) + 1),
        )

    def acceptance_dispute_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        """The QA lead judges a failed attempt's locked tests. See `app.agents.suite_dispute`."""
        from pathlib import Path

        from app.acceptance import suite as acceptance_suite
        from app.agents.suite_dispute import build_dispute_request, tests_it_names
        from app.graph.acceptance_nodes import SPRINT_REPLAN, reopen_the_suite_for

        disputed = sorted({*map(str, state.get("disputed_sprints") or []), _this_attempt(state)})
        # Held mid-attempt, it goes back to the attempt: a repaired suite to the
        # round, and nothing to repair to the remediation it interrupted.
        returns_to = state.get("dispute_returns_to")
        carry_on = "defect_remediation" if returns_to else "technical_lead"
        failing = _the_locked_tests_still_failing(state)
        if not failing:
            return _handing_on(stage=carry_on, disputed_sprints=disputed, dispute_returns_to=None, dispute_reason=None)
        root = state["repository"].root_path
        code = "\n\n".join(
            f"--- {path.relative_to(Path(root)).as_posix()} ---\n{path.read_text(encoding='utf-8', errors='replace')}"
            for path in acceptance_suite.suite_files(root)
        )[:16000]
        agent = create_suite_dispute_agent(
            model=judgement_model, checkpointer=shared_checkpointer,
            repo_root=repo_root, allow_subdirectories=allow_subdirectories,
        )
        update = _run_gated_agent(
            state,
            config,
            stage_name="acceptance_dispute",
            agent=agent,
            initial_request=_with_the_reason(
                build_dispute_request(failing, code, getattr(state.get("document"), "text", "") or ""),
                str(state.get("dispute_reason") or ""),
            ),
            output_key="__suite_dispute__",
            next_stage="acceptance_dispute",
        )
        if _hand_back(update, "__suite_dispute__"):
            return update
        named = tests_it_names(update.pop("__suite_dispute__"), [name for name, _, _ in failing])
        missing = [
            f"`{name}` is missing from the locked suite; no test checks what the criterion says. Add a test for `{name.split()[0]}` or tag an existing test that proves it."
            for name, _, _ in failing
            if "missing from locked suite" in name
        ]
        to_repair = [*named, *missing]
        update.pop("stage", None)
        if to_repair:
            logger.warning("The QA lead / harness identifies %d locked test(s)/missing criteria cannot pass; reopening the suite", len(to_repair))
            reopened = reopen_the_suite_for(state, to_repair, return_to=returns_to or SPRINT_REPLAN)
            if reopened is not None:
                return _handing_on(**{**update, **reopened, "disputed_sprints": disputed, "dispute_returns_to": None, "dispute_reason": None})
        return _handing_on(**update, stage=carry_on, disputed_sprints=disputed, dispute_returns_to=None, dispute_reason=None)

    def advice_review_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        """Each consulted specialist checks its adopted advice against this sprint. See `app.agents.advice_review`."""
        from app.agents.advice_review import build_advice_review_request, findings_from, roles_to_review
        from app.agents.specialist_advice import adopted

        # One review per sprint and per milestone revision: a revised sprint is
        # checked again, from nothing.
        cycle = f"{state.get('current_sprint_index', 0)}:{state.get('milestone_revision_count', 0)}"
        found = dict(state.get("advice_findings") or {}) if state.get("advice_review_cycle") == cycle else {}
        advice, specification = state.get("specialist_advice"), state.get("technical_specification")
        pending = [role for role in roles_to_review(advice, specification) if role not in found]
        if not pending:
            return _handing_on(stage="milestone_review", advice_findings=found, advice_review_cycle=cycle)
        role = pending[0]
        changed_files = _the_files_this_milestone_changed(state, state.get("specialist_outputs", {}))
        if role == "database" and not state.get("pending_inner_thread_id") and not _changes_any_code(changed_files):
            found[role] = []
            return _handing_on(stage="advice_review", advice_findings=found, advice_review_cycle=cycle)
        milestone = state.get("milestone_plan")
        request = build_advice_review_request(
            role,
            adopted(advice, specification, role),
            str(getattr(milestone, "selected_sprint_goal", "") or ""),
            _this_sprint_s_scope_for_review(state),
            changed_files,
        )
        request["messages"][-1]["content"] += _fixes_a_review_must_not_undo(state)
        if role == "ui_ux":
            # The design QA loop: the page as a person sees it, for a model that can see.
            from app.models.vision import the_reviewer_reads_images

            if the_reviewer_reads_images():
                from app.agents.page_screenshots import with_the_page_screenshots

                request = with_the_page_screenshots(
                    request,
                    state["repository"].root_path,
                    getattr(specification, "interface_design", None) or [],
                )
        agent = create_advice_reviewer_agent(
            role, model=judgement_model, checkpointer=shared_checkpointer,
            repo_root=repo_root, allow_subdirectories=allow_subdirectories,
        )
        update = _run_gated_agent(
            state,
            config,
            stage_name=f"advice_review_{role}",
            agent=agent,
            initial_request=request,
            output_key="__advice_review__",
            next_stage="advice_review",
        )
        if _hand_back(update, "__advice_review__"):
            return update
        found[role] = findings_from(role, update.pop("__advice_review__"))
        if found[role]:
            logger.info("The %s specialist found %d adopted item(s) not built", role, len(found[role]))
        from app.agents.advice_review import as_sprint_findings

        return _handing_on(**{
            **update,
            "advice_findings": found,
            "advice_review_cycle": cycle,
            "sprint_findings": list(state.get("sprint_findings") or [])
            + as_sprint_findings(found[role], state.get("milestone_revision_count", 0) + 1),
            "stage": "advice_review" if len(pending) > 1 else "milestone_review",
        })

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
        
        # The measured suite, run on the review's first entry only: a resume
        # after an approval pause is the same review of the same code.
        from app.graph import acceptance_nodes

        acceptance_text = (
            acceptance_nodes.acceptance_text_for(state)
            if not state.get("pending_inner_thread_id")
            else ""
        )
        agent = create_milestone_reviewer_agent(model=judgement_model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
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
            acceptance=acceptance_text,
            specialist_findings=_this_review_s_advice_findings(state),
        )
        request["messages"][-1]["content"] += _fixes_a_review_must_not_undo(state)
        request["messages"][-1]["content"] += _the_code_review_s_advice(state)
        # The page as a person sees it, for a reviewer whose model can see. See
        # `app.agents.page_screenshots`; a model that cannot is not sent them.
        from app.models.vision import the_reviewer_reads_images

        if the_reviewer_reads_images():
            from app.agents.page_screenshots import with_the_page_screenshots

            request = with_the_page_screenshots(
                request,
                state["repository"].root_path,
                getattr(state.get("technical_specification"), "interface_design", None) or [],
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
            _findings_the_command_record_contradicts(
                _findings_about_a_server_only_the_tests_start(
                    _findings_the_dependency_check_contradicts(
                        _security_graded_by_its_own_review(
                            _findings_a_later_sprint_builds(update.pop("__milestone_review__"), state),
                            state.get("security_review"),
                        ),
                        state,
                    ),
                    state["repository"].root_path,
                ),
                state["repository"].root_path,
            ),
            state["repository"].root_path,
            "accepted",
            "milestone_review",
        )
        review = _accepted_when_nothing_in_it_gates(review, state["repository"].root_path)
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

        # The acceptance suite is the definition of done: a sprint whose due
        # criteria fail is not accepted, whatever the review read. Measured by
        # the harness's run of the locked suite, not reported by a model.
        not_passing = acceptance_nodes.due_criteria_failing(state)
        if not_passing:
            revision_count = state.get("milestone_revision_count", 0) + 1
            if revision_count < MAX_MILESTONE_REVISIONS:
                logger.warning("Milestone review would accept failing acceptance criteria; sending it back")
                return _handing_on(
                    stage="technical_lead",
                    revision_comments=state.get("revision_comments", []) + [not_passing],
                    milestone_revision_count=revision_count,
                    milestone_review=review,
                )
            summary = _record_sprint_summary(
                state,
                "Failed",
                f"acceptance criteria still failing after {MAX_MILESTONE_REVISIONS} revisions",
            )
            return _escalate_to_a_human(
                state,
                error=(
                    f"Acceptance criteria were still failing after {MAX_MILESTONE_REVISIONS} "
                    f"revisions.\n\n{not_passing}"
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

        # A decision like any other, and the page the sprint's reviewer reads.
        from app.decisions import record_decision
        from app.graph import delivery

        accepted: dict[str, Any] = {}
        record_decision(
            state, accepted, point="sprint",
            question=f"Is sprint {sprint_index + 1} done?",
            options=["accept", "send it back"],
            decision="accept",
            rationale=(
                "The milestone review accepted it and every acceptance criterion due by "
                "this sprint passes. " + _as_text(review.acceptance_evidence)
            )[:1500],
        )
        delivery.write_evidence({**state, **accepted}, sprint_index + 1, milestone.selected_sprint_goal)
        from app.graph import engineering

        engineering.accepted_state(state["repository"].root_path)

        if _review_enabled(state, SPRINT_REVIEW):
            next_stage = "user_review_sprint"
        elif has_more_sprints:
            next_stage = "sprint_advance"
        else:
            next_stage = "release"

        return _handing_on(**accepted, stage=next_stage, milestone_review=review)

    def user_review_sprint_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        sprint_index = state.get("current_sprint_index", 0)
        sprints = state.get("sprint_plan").sprints if state.get("sprint_plan") else []
        has_more_sprints = sprint_index < len(sprints) - 1
        
        return _run_review_gate(
            state,
            config,
            review_point=SPRINT_REVIEW,
            artifact_id="sprint-milestone",
            approved_next="sprint_advance" if has_more_sprints else "release",
            # A requested change becomes a change request with its own
            # acceptance test before the sprint is planned again. See
            # `app.graph.delivery.change_request`.
            changes_next="change_request",
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
            "review_advice": [],
            "nothing_left_but_carried": None,
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
            "sprint_replan_count": 0,
        }

    def complete_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:  # noqa: ARG001
        """The run is done - and the sprint that finished it needs its summary.

        Only `sprint_advance_node` recorded one, and the last sprint never
        advances: it routes straight here. So a three-sprint plan wrote
        `sprint_1` and `sprint_2` and stopped, and the sprint that actually
        delivered the product was the one with nothing to show for it.
        """
        if _sprint_already_summarised(state):
            _commit_the_last_records(state["repository"].root_path)
            return {"stage": "complete"}
        summary = _record_sprint_summary(state, "Completed")
        _commit_the_last_records(state["repository"].root_path)
        return {**summary, "stage": "complete"}

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

    # The stages between an approved architecture and the sprint plan, and the
    # QA lead's review. See `app.graph.acceptance_nodes`.
    from app.graph import acceptance_nodes

    stage_context = acceptance_nodes.Context(
        model=model,
        judgement_model=judgement_model,
        checkpointer=shared_checkpointer,
        repo_root=repo_root,
        allow_subdirectories=allow_subdirectories,
    )

    def scaffold_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return acceptance_nodes.scaffold(state, config, stage_context)

    def acceptance_author_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return acceptance_nodes.acceptance_author(state, config, stage_context)

    def acceptance_review_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return acceptance_nodes.acceptance_review(state, config, stage_context)

    def user_review_acceptance_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return _run_review_gate(
            state,
            config,
            review_point=ACCEPTANCE_REVIEW,
            artifact_id="acceptance-tests",
            approved_next="scrum_master",
            changes_next="acceptance_author",
        )

    # Shipping: the release gate and change requests. See `app.graph.delivery`.
    from app.graph import delivery

    # CI and code review between a batch and its test rounds. See
    # `app.graph.engineering`.
    from app.graph import engineering

    def ci_gate_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return engineering.ci_gate(state, config, stage_context)

    def code_review_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return engineering.code_review(state, config, stage_context)

    # The last rung of the ladder. See `app.graph.escalation`.
    from app.graph import escalation as stuck

    def escalation_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return stuck.escalation(state, config, stage_context)

    def escalation_accept_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return stuck.accept(state, config, stage_context)

    def escalation_retry_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return stuck.retry(state, config, stage_context)

    def user_review_escalation_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return _run_review_gate(
            state,
            config,
            review_point=ESCALATION_REVIEW,
            artifact_id="escalation",
            approved_next="escalation_accept",
            changes_next="escalation_retry",
        )

    def change_request_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return delivery.change_request(state, config, stage_context)

    def release_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return delivery.release(state, config, stage_context)

    def user_review_release_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return _run_review_gate(
            state,
            config,
            review_point=RELEASE_REVIEW,
            artifact_id="release",
            approved_next="complete",
            changes_next="change_request",
        )

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
    graph.add_node("specialist_consultation", specialist_consultation_node, retry_policy=agent_retry_policy)
    graph.add_node("principal_architect", principal_architect_node, retry_policy=agent_retry_policy)
    graph.add_node("architecture_review", architecture_review_node, retry_policy=agent_retry_policy)
    graph.add_node("user_review_specification", user_review_specification_node)
    graph.add_node("scaffold", scaffold_node, retry_policy=agent_retry_policy)
    graph.add_node("acceptance_author", acceptance_author_node, retry_policy=agent_retry_policy)
    graph.add_node("acceptance_review", acceptance_review_node, retry_policy=agent_retry_policy)
    graph.add_node("user_review_acceptance", user_review_acceptance_node)
    graph.add_node("scrum_master", scrum_master_node, retry_policy=agent_retry_policy)
    graph.add_node("technical_lead", technical_lead_node, retry_policy=agent_retry_policy)
    graph.add_node("specialist_dispatch", specialist_dispatch_node, retry_policy=agent_retry_policy)
    graph.add_node("specialist_worker", specialist_worker_node, retry_policy=agent_retry_policy)
    graph.add_node("specialist_gather", specialist_gather_node)
    # A static edge, not the shared router: every `Send` branch converges
    # here and LangGraph runs the target once for the whole superstep,
    # which is what gives the fan-out a single writer for `stage`.
    graph.add_edge("specialist_worker", "specialist_gather")
    graph.add_node("ci_gate", ci_gate_node)
    graph.add_node("code_review", code_review_node, retry_policy=agent_retry_policy)
    graph.add_node("test_and_triage", test_and_triage_node, retry_policy=agent_retry_policy)
    graph.add_node("defect_remediation", defect_remediation_node, retry_policy=agent_retry_policy)
    graph.add_node("security_review", security_review_node, retry_policy=agent_retry_policy)
    graph.add_node("advice_review", advice_review_node, retry_policy=agent_retry_policy)
    graph.add_node("acceptance_dispute", acceptance_dispute_node, retry_policy=agent_retry_policy)
    graph.add_node("milestone_review", milestone_review_node, retry_policy=agent_retry_policy)
    graph.add_node("user_review_sprint", user_review_sprint_node)
    graph.add_node("sprint_advance", sprint_advance_node)
    graph.add_node("change_request", change_request_node)
    graph.add_node("escalation", escalation_node)
    graph.add_node("user_review_escalation", user_review_escalation_node)
    graph.add_node("escalation_accept", escalation_accept_node)
    graph.add_node("escalation_retry", escalation_retry_node)
    graph.add_node("release", release_node)
    graph.add_node("user_review_release", user_review_release_node)
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
        "specialist_consultation",
        "principal_architect",
        "architecture_review",
        "user_review_specification",
        "scaffold",
        "acceptance_author",
        "acceptance_review",
        "user_review_acceptance",
        "scrum_master",
        "technical_lead",
        "specialist_dispatch",
        "specialist_gather",
        "ci_gate",
        "code_review",
        "test_and_triage",
        "defect_remediation",
        "security_review",
        "advice_review",
        "milestone_review",
        "acceptance_dispute",
        "user_review_sprint",
        "sprint_advance",
        "change_request",
        "release",
        "user_review_release",
        "escalation",
        "user_review_escalation",
        "escalation_accept",
        "escalation_retry",
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
    "milestone_review": {"milestone_revision_count": 0, "sprint_replan_count": 0},
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
