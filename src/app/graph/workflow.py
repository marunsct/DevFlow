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
from collections.abc import Sequence
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

from app.observability.degraded import degraded
from app.agents.shared_facts import with_the_facts
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
    specification_for_the_work_order,
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
    failed_fix_tries,
    mark_defect_fixed,
    record_test_run,
    start_remediation,
)
from app.sprint import cause
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

#: Where a milestone review's `blocked` sends the run. The reviewer's schema
#: describes this consequence (`app.agents.milestone_reviewer.BLOCKED_MEANS`)
#: and a test holds the two together.
MILESTONE_REVIEW_NEXT_STAGE = {"blocked": "technical_lead"}

FAST_MILESTONE_REVISIONS = 2
"""The same bound in fast delivery: one send-back, then the findings are recorded as risks."""

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

SPRINT_PLAN_REVIEW = "sprint_plan"
"""Review point, the plan gate (plan WS.3): the sprint plan, before any sprint is built. It waits for a go or a
direction, and goes on by itself after its timeout (`app.server.approval_timeouts.plan_gate_minutes`)."""

from app.agents import interface_clashes  # noqa: E402 - beside its siblings
from app.acceptance import mutation_guided  # noqa: E402 - beside its siblings
from app.graph import defect_fix_modes  # noqa: E402 - beside its siblings
from app.graph.acceptance_nodes import ACCEPTANCE_REVIEW  # noqa: E402 - beside its siblings
from app.graph.delivery import RECORDED_AS_RISKS, RELEASE_REVIEW  # noqa: E402 - beside its siblings
from app.graph.escalation import ESCALATION_REVIEW  # noqa: E402 - beside its siblings

_REVIEW_NODES = {
    SPECIFICATION_REVIEW: "user_review_specification",
    SPRINT_REVIEW: "user_review_sprint",
    PRODUCT_INTAKE_REVIEW: "user_review_product_intake",
    ACCEPTANCE_REVIEW: "user_review_acceptance",
    SPRINT_PLAN_REVIEW: "user_review_sprint_plan",
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
    SPRINT_PLAN_REVIEW: WorkflowStage.SPRINT_PLANNING,
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
        "user_review_sprint_plan",
        # A sprint's tests written and locked at its start, where the suite is written a sprint at a time (LF.1266).
        "sprint_acceptance",
        "technical_lead",
        "specialist_dispatch",
        # Parallel mode's fan-out target. `graph.add_node` registers it and
        # routers reference it, but it was absent here - and every conditional
        # edge map, including the entry router's, is built from this set. So no
        # edge map contained it and a resume parked on it had no target.
        "specialist_worker",
        "specialist_gather",
        # Parallel mode's defect fixes: see `app.graph.nodes.fixes._the_next_fix_batch`.
        "defect_fix_worker",
        "defect_fix_gather",
        # Parallel mode's reviews: see `security_review_node`.
        "review_worker",
        "review_gather",
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
    # A resume inside the reviews' fan-out re-enters the node that started it.
    "review_parallel": "security_review",
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
    # The `architecture_revision_count` of the review whose findings the architect
    # has applied. See `_the_review_s_findings_are_open`.
    architecture_review_applied: int
    # Set once the workflow has raised its one success-measure coverage finding
    # against a specification. See `_a_success_measure_the_specification_drops`.
    specification_coverage_checked: bool
    specification_deferrals_checked: bool
    specification_contract_lines_checked: bool
    specification_kept_files_checked: bool
    specification_signatures_checked: bool
    specification_command_order_checked: bool
    # The workflow's own design checks that sent back a specification the reviewer approved (`HARNESS_FINDINGS_RECHECKED`).
    approved_but_for_the_harness: list[str]
    # Thorough delivery's ledger of gating design findings and how each ended. See `app.graph.design_gate`.
    design_gate: dict[str, Any]
    specification_repair_count: int
    layout_repair_count: int
    # Per-stage count of attempts that ended without a structured response.
    structured_retries: dict[str, int]
    # Per-stage note from the attempt that just died, read once by the
    # fresh one and then cleared. See `app.agents.carry_over`.
    stage_carry_over: dict[str, str]
    milestone_revision_count: int
    # The registry releases and documentation read for the architect before
    # it writes, kept so a retry or a revision is not read again.
    # See `app.agents.research_brief`.
    architect_research: str
    # How often this sprint was planned again because its tests could not be
    # made to pass. Counted apart from `milestone_revision_count`, which is the
    # milestone review's: see `app.graph.nodes.triage._replan_or_escalate`.
    sprint_replan_count: int
    sprint_best_history: list
    sprint_plan: SprintPlanOutput
    # Success measures a sprint plan left unassigned or only partly delivered,
    # as {"measure": n, "missing": [items]}, carried into the one re-plan that
    # asks for them. See `unaccounted_success_measures` and
    # `capabilities_the_plan_never_names`.
    sprint_plan_gaps: list[dict[str, Any]]
    sprint_plan_built_ahead: list[str]
    # What a sprint plan's sprints held over the size limit, or that one held no criterion, carried into the one
    # re-plan that asks for sprints sized by work. See `scrum_master.sprints_not_sized_by_work` (LF.1315).
    sprint_plan_unsized: list[str]
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
    # Whether this milestone plan's work orders were drafted from the
    # specification (fast delivery; `app.graph.drafting`). Cleared with each plan.
    drafted_for_plan: bool
    specialist_outputs: Annotated[dict[str, SpecialistOutput], _merge_or_reset]
    # A builder stage sent back with what its work order still lacks -> that note; "" once it has built again
    # (`app.graph.unfinished_build`, LF.1299). Merged: parallel workers each clear their own.
    unfinished_orders: Annotated[dict[str, str], _merge_or_reset]
    # Which of `unfinished_build`'s two send-backs this attempt has used (each once an attempt). Cleared with each plan.
    builders_sent_back: list[str]
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

    # The redesign (docs/architecture-decisions.md ADR-0005). `stack_pack` names the
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
    # What the release knows it did not prove: deferred criteria, problems the
    # suite was locked with, plan problems noted at dispatch, an unproven
    # setup. Set once by `delivery.release`; a completed run with gaps here is
    # never plain "completed" in any record that shows it.
    completion_gaps: list[str]
    # Parallel mode's defect fixes (`app.graph.nodes.fixes._the_next_fix_batch`): the batch in
    # flight, by defect index; the fix stages tried this round; and the ones
    # whose batch was reverted, to be fixed alone.
    fix_batch: list[int]
    # When the batch was dispatched, so each fixer's calls are counted from it (plan AY step 4).
    fix_batch_started: str
    # When the defect fixed alone started, carried across its approval pause (plan AY step 4).
    fix_started: str
    fixes_tried: list[str]
    fixes_one_at_a_time: list[str]
    # Parallel mode's reviews (`security_review_node`): the reviews in flight -
    # "security" and each advice role - and the results each has returned.
    reviews_in_flight: list[str]
    review_results: Annotated[dict[str, Any], _merge_or_reset]
    # The tests each repair was for, so a test never sent for repair is not
    # refused for a budget others spent. See `acceptance_nodes.may_repair`.
    suite_repaired_tests: list[str]
    #: The locked tests this run's disputes reclassified - sent back to QA as
    #: "cannot pass" past the harness's own re-measure and its cap. Named in
    #: the release's `completion_gaps` (Initiative J.2).
    suite_reclassified_tests: list[str]
    #: How many causes those reclassifications were - one broken helper is one - which the cap counts.
    suite_reclassified_causes: int
    release_attempts: int
    # The last rung: a stuck sprint's decision. See `app.graph.escalation`.
    escalation: dict[str, Any] | None
    escalation_count: int
    # Of those, the ones about the design (an architecture review still asking for changes): they say nothing about
    # whether the build model can build, so the build rung does not count them (`GraphContext.the_model_for_this_attempt`).
    design_escalation_count: int
    # The sprints planned again because later sprints build on what they would defer (`escalation._the_foundation_first`).
    foundation_replanned_sprints: list[int]
    known_issues: list[str]
    unit_failures_accepted_at_an_escalation: list[str]
    # Plan QM.2, off until measured: the sprint attempts whose sources were
    # probed with deliberate changes ("<sprint index>:<re-plan count>"), and
    # the findings no unit test was made to notice, for the release's gaps.
    # See `app.acceptance.mutation_guided`.
    mutation_probed: list[str]
    mutation_gaps: list[str]
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
    # A builder sent back with its work order unfinished has an output and is not done (`unfinished_build`).
    from app.graph.unfinished_build import pending

    done = set(state.get("specialist_outputs") or {}) - pending(state)
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


def the_round_s_measurement(root: Any) -> str:
    """What the acceptance suite measured in the round, in counts; "" when it has not run.

    The log said only how many defects a round raised, as "did not report 5
    failing acceptance criteria"; read as the round's result, a round where
    the product did not start - every criterion failing, the start failure
    standing for the rest - looked better than the next, where it started and
    2 of 13 passed. Measured on one run, by its owner.
    """
    try:
        from app.acceptance import suite

        result = suite.last_result(Path(root)) if root else {}
    except Exception:  # noqa: BLE001 - a log line is never worth a failure
        return ""
    if not result or not result.get("ran"):
        return "the acceptance suite did not run"
    criteria = list((result.get("criteria") or {}).values())
    passing = sum(1 for c in criteria if (c or {}).get("status") == "passed")
    return (
        f"the acceptance suite measured {passing} of {len(criteria)} criteria passing "
        f"({result.get('passed', 0)} of {int(result.get('passed') or 0) + int(result.get('failed') or 0)} tests)"
    )


def _record_the_owners(root: Any, tasks: list[Any], done: Any = ()) -> None:
    """Record which stage owns each file the dispatched work orders list; a file two list has none.

    From the work orders as dispatched, not as the lead planned them. Measured
    on one run: fast delivery split the lead's one backend order of 18 files
    into six orders of three, the table still gave every file to the first,
    and each later order was refused its own files - the service's entry
    point among them - as "specialist_backend_0's", a stage the dispatched
    plan does not have.
    """
    if not root:
        return
    from app.tools.repository import record_work_order_files

    finished = set(done or ())
    declared: dict[str, list[str]] = {}
    for index, task in enumerate(tasks or []):
        for path in getattr(task, "files", None) or []:
            declared.setdefault(str(path), []).append(_specialist_stage_name(task, index))
    # A work order already done - drafted whole by the harness, or finished by its stage - owns nothing any more
    # (harness review P4). Measured over 40 runs: 42 of 64 ownership refusals named an owner that never ran as a
    # stage, its files drafted in fast delivery, so a later stage needing a change there was refused with no one to
    # ask; 12 more named an owner already finished.
    record_work_order_files(root, {path: stages[0] for path, stages in declared.items()
                                   if len(set(stages)) == 1 and stages[0] not in finished})


def _specialist_stage_name(task: Any, index: int) -> str:
    """The stage name one delegated task runs under.

    Shared by linear dispatch, the parallel router and the parallel worker.
    Three copies of one f-string is how a fan-out comes to record its results
    under names the dispatcher does not recognise, which would make every task
    look unfinished forever.
    """
    return f"specialist_{getattr(task, 'specialist_role', 'unknown')}_{index}"


def max_parallel() -> int:
    """How many agents of one run may work at once in parallel mode (`HARNESS_MAX_PARALLEL`, 6).

    A ceiling on every fan-out - work orders, defect fixes, reviews. A local
    model server that answers one request at a time gains nothing past one; a
    hosted API that serves requests side by side gains up to its rate limit.
    """
    raw = os.environ.get("HARNESS_MAX_PARALLEL", "").strip()
    try:
        return max(1, int(raw)) if raw else 6
    except ValueError:
        logger.warning("HARNESS_MAX_PARALLEL is not a number: %r; using 6", raw)
        return 6


def concurrent_requests() -> int:
    """How many of one fan-out to send at once: `max_parallel()`, and no more than the server's slots.

    A request past the server's slots only queues there, and its wait counts
    against its timeout; on a server that splits its context across slots, a
    fan-out wider than the slots is also what refused calls at a fraction of
    the window (`server_profile`). Whether work fans out at all is still the
    owner's execution mode and `max_parallel()`; this sizes each wave.
    """
    try:
        from app.models.server_profile import current

        slots = getattr(current(), "slots", None)
    except Exception:  # noqa: BLE001
        slots = None
    return max(1, min(max_parallel(), slots)) if slots else max_parallel()


def _in_parallel_mode() -> bool:
    """Whether the owner's execution mode is parallel. See `app.graph.nodes.building.specialist_dispatch_node`."""
    try:
        from app.server.runtime_settings import effective_settings

        return effective_settings().execution_mode == "parallel"
    except Exception:  # noqa: BLE001 - an unreadable store is the deployed configuration
        from app.config import load_settings

        try:
            return load_settings().execution_mode == "parallel"
        except Exception:  # noqa: BLE001
            return False


def an_unfinished_sprint(goal: str, replans: int, why: str, report: str) -> str:
    """The escalation's words for a sprint that could not be accepted, with the re-plans it really had (LR.53).

    It said "re-planned 3 times" - the limit - whatever the count: 105 scored results carried it, many after a sprint
    settled or stopped on its first attempt.
    """
    tried = "was planned once" if replans <= 0 else f"was re-planned {replans} time{'s' if replans != 1 else ''}"
    return f"Sprint '{goal}' {tried} and still could not be accepted: {why}.\n\n{report}"


def _fixes_run_side_by_side() -> bool:
    """Whether defects are fixed in batches: parallel mode, with more than one agent allowed."""
    return max_parallel() > 1 and _in_parallel_mode()


def _fix_batch_pending(state: Any) -> list[int]:
    """The defects of the batch in flight whose fixer has not produced an output yet."""
    outputs = state.get("specialist_outputs") or {}
    round_ = state.get("test_round", 0)
    return [index for index in (state.get("fix_batch") or []) if f"defect_fix_{round_}_{index}" not in outputs]


def _with_tried(state: Any, update: dict[str, Any], stage_name: str) -> dict[str, Any]:
    """`update`, with the defect's fix stage recorded as tried in this round."""
    tried = list(dict.fromkeys([*(state.get("fixes_tried") or []), stage_name]))
    alone = [name for name in (state.get("fixes_one_at_a_time") or []) if name != stage_name]
    return {**update, "fixes_tried": tried, "fixes_one_at_a_time": alone}


def _noted_as_reverted(cycle: Any, indices: list[int], broke: list[str], *, in_a_batch: bool = False) -> Any:
    """The cycle with each defect's actual behaviour noting the revert.

    One fix reverted alone is noted in the words `_REVERTED_FOR` reads - two of
    those against one locked test call for a dispute. A batch reverted whole is
    noted otherwise: which of its fixes broke the test is not known, and each is
    fixed alone next.

    The note replaces the one before it, and counts the defect's reverts and the
    locked tests they broke (`_the_reverts_noted`). Found in a code review: each
    revert appended the same ~400-character note, three reverts left about 4,200
    characters of notes ahead of the runner's output, and the rewrite's failure
    text was cut at test 23 of 79.
    """
    # On one line each: the note is found, replaced and read line by line.
    named = "; ".join(str(item).replace("\n", " ") for item in broke[:5])
    unit_guidance = _A_UNIT_TEST_MAY_BE_OUT_OF_DATE if any(item.startswith("unit:") for item in broke) else ""
    note = (
        "A batch of fixes including this one was reverted, because together they broke what "
        f"passed before them: {named}. It is fixed on its own next."
        if in_a_batch
        else f"A fix was tried and reverted, because it broke what passed before it: {named}."
    )

    def noted(item: Any) -> str:
        reverts, broken = _the_reverts_noted(str(item.actual_behavior or ""))
        if not in_a_batch:
            broken.update(name.strip() for name in named.split("; ") if name.strip().startswith("acceptance:"))
        tally = ""
        if reverts >= 1:
            tally = f"\n{_REVERTS_SO_FAR} {reverts + 1}." + (
                f" {_THE_TESTS_THEY_BROKE} " + "; ".join(f"{name} ({count})" for name, count in broken.most_common()) + "."
                if broken else "")
        return (f"{_without_the_revert_note(str(item.actual_behavior or ''))}\n{note}{tally}{unit_guidance}"
                f"{_the_unit_tests_are_out_of_date(item, broke)}")

    return cycle.model_copy(update={"defects": [
        item.model_copy(update={"actual_behavior": noted(item)}) if position in indices else item
        for position, item in enumerate(cycle.defects)
    ]})


#: What a reverted fix of a defect whose broken tests include unit tests is told.
_A_UNIT_TEST_MAY_BE_OUT_OF_DATE = (
    "\nIf the behaviour this sprint delivers is different from what was built before, the "
    "test is out of date, not the product: change what it asserts to the behaviour "
    "this sprint delivers, keep the test's name (a test that disappears is counted "
    "as broken), and say in your answer that the test was out of date."
)
#: How the line that counts a defect's reverted fixes begins, and how it names the locked tests they broke.
_REVERTS_SO_FAR = "Fixes of this defect reverted so far:"
_THE_TESTS_THEY_BROKE = "The locked acceptance tests they broke, each with how many of them broke it:"
_A_REVERT_TALLY = re.compile(
    rf"^{re.escape(_REVERTS_SO_FAR)} (\d+)\.(?: {re.escape(_THE_TESTS_THEY_BROKE)} (.+)\.)?$", re.M)
#: The first line of a revert note, alone or in a batch, and the line that counts the reverts.
_A_REVERT_NOTE_LINE = re.compile(
    rf"\n?^(?:A fix was tried and reverted, because|A batch of fixes including this one was reverted, because"
    rf"|{re.escape(_REVERTS_SO_FAR)})[^\n]*", re.M)


def _without_the_revert_note(actual_behavior: str) -> str:
    """`actual_behavior` with the revert note a fix left on it taken out, whatever came after it kept."""
    text = _A_REVERT_NOTE_LINE.sub("", actual_behavior)
    for guidance in (_A_UNIT_TEST_MAY_BE_OUT_OF_DATE, UNIT_TESTS_AGAINST_THE_SUITE):
        text = text.replace(guidance, "")
    return text.rstrip("\n")


def _the_reverts_noted(actual_behavior: str) -> tuple[int, Any]:
    """How many fixes of the defect were reverted, and how many of them broke each locked acceptance test.

    Read from the tally line a second revert writes; a note without one (a single revert, or notes appended before
    the note was replaced) is counted note by note.
    """
    from collections import Counter

    broken: Counter[str] = Counter()
    tally = _A_REVERT_TALLY.search(actual_behavior)
    if tally:
        for entry in (tally.group(2) or "").split("; "):
            name, _, count = entry.strip().rpartition(" (")
            if name and count.rstrip(")").isdigit():
                broken[name] += int(count.rstrip(")"))
        return int(tally.group(1)), broken
    for match in _REVERTED_FOR.finditer(actual_behavior):
        for name in match.group(1).split("; "):
            if name.strip().startswith("acceptance:"):
                broken[name.strip()] += 1
    reverts = len(_REVERTED_FOR.findall(actual_behavior)) + actual_behavior.count(
        "A batch of fixes including this one was reverted")
    return reverts, broken


#: What a unit-test defect is told when its fix broke the locked acceptance suite. Measured on one run: the unit tests
#: called the product's factory as it was before a fix made it asynchronous, and two fixes in turn changed the product
#: to suit them, broke three and then seven passing acceptance tests, and were reverted; the sprint was planned again.
UNIT_TESTS_AGAINST_THE_SUITE = (
    "\nThe product before this fix passed those acceptance tests, and no fix may change them: where the unit tests "
    "and the acceptance suite disagree, the unit tests are out of date. Change the unit tests to use the product as "
    "it now is - its functions as they are now called, what they now return - keep each test's name, leave the "
    "product as it is, and say in your answer that the unit tests were out of date."
)


def _the_unit_tests_are_out_of_date(defect: Any, broke: list[str]) -> str:
    """`UNIT_TESTS_AGAINST_THE_SUITE` for a failing-unit-tests defect whose fix broke acceptance tests; else ""."""
    if not str(getattr(defect, "description", "") or "").startswith(UNIT_TESTS_FAIL):
        return ""
    return UNIT_TESTS_AGAINST_THE_SUITE if any(item.startswith("acceptance:") for item in broke) else ""


def _the_unit_tests_a_kept_fix_broke(state: Any) -> dict[str, Any]:
    """The update raising what `unit_tests_disagree` kept a fix over, for the next round; {} when nothing was."""
    from app.graph import unit_tests_disagree

    raised = unit_tests_disagree.raised(state)
    return {"review_defects": [*(state.get("review_defects") or []), *raised]} if raised else {}


def _a_revert_escalates_this_fix(cycle: Any, defect_index: int) -> bool:
    """Whether this defect's next fix attempt goes to the judgement model because one was reverted.

    The revert is the proven failure signal: a fix was measured, it broke what
    passed before it, and the harness undid it - stronger evidence than a
    failed try that merely left the defect failing. Both reverted fixes in the
    live run came from the local build model, matching the bench pattern that
    the local model drafts fine but its fixes are the weak link, so the
    attempt right after a revert does not wait for the generic
    `escalate_after()` rung (Initiative L.4).

    Capped at one escalation per defect by its own shape: exactly one revert
    note escalates. A second revert has already pushed `failed_fix_tries` to
    the generic rung, where the ladder escalates on its own - counting that
    too would escalate every later attempt twice over and defeat the cap that
    protects cost.
    """
    try:
        defect = cycle.defects[defect_index]
        notes = str(getattr(defect, "actual_behavior", "") or "")
    except (AttributeError, IndexError, TypeError):
        return False
    reverts, _ = _the_reverts_noted(notes)
    return reverts == 1


def _the_stub_still_served_section(root: Any) -> str:
    """What every fixer must know first while the served app is still the scaffold's stub; else "".

    Measured on one run: a round queued 13 defects, one per criterion, all of
    them failing their first page control because the page served was the
    scaffold's stub - the drafted app sat in folders nothing served. The stub
    is found when a round is assembled; a queue assembled before then went to
    fixer after fixer, ten to seventeen minutes each, every one chasing its
    own symptom. Checked at each dispatch, so the cause reaches the queue too.
    """
    try:
        from app.stacks.scaffold import entrypoint_is_still_the_stub

        stub = entrypoint_is_still_the_stub(root) if root else None
    except Exception:  # noqa: BLE001 - the request stands as it was
        return ""
    if not stub:
        return ""
    return (
        "\n--- Before this defect: the served app is still the scaffold's stub ---\n"
        f"`{stub}` is byte-identical to what the scaffold wrote, and the acceptance suite runs "
        "against exactly that file. Whatever this run drafted elsewhere is not served, which is "
        "why this criterion fails - and every other one with it. First make the served file the "
        "product: build it there, or import the drafted code from it. Then check this defect again.\n"
    )


def _the_unserved_code_section(root: Any) -> str:
    """What every fixer must know about code the product never runs; else "".

    Measured on one run: two copies of the page and the service, one served
    and one drafted beside it, and fixes landed in both - one rewrote a
    migration file nothing ran. See `scaffold.code_the_product_does_not_run`.
    """
    try:
        from app.stacks.scaffold import code_the_product_does_not_run

        problems = code_the_product_does_not_run(root) if root else []
    except Exception:  # noqa: BLE001 - the request stands as it was
        return ""
    if not problems:
        return ""
    return "\n--- Code the product does not run ---\n" + "\n".join(f"- {p}" for p in problems) + "\n"


def _the_database_section(root: Any) -> str:
    """For a service product: the data store here is the embedded file, and a missing server is no blocker; else "".

    Measured on one run: the specification named PostgreSQL, and three fixes of
    three criteria each ended "changed nothing: no PostgreSQL server is
    available, an environmental constraint" - while the same product ran on
    an embedded file. The environment contract says so to every stage; a
    fixer that has just read a specification naming a server needs it said
    where it is deciding whether it can act (Initiative K.2).
    """
    try:
        from app.stacks import contract

        found = contract.the_pack(root) if root else None
        if found is None or found[0].kind not in ("http_api", "fullstack"):
            return ""
    except Exception:  # noqa: BLE001 - the request stands as it was
        return ""
    return (
        "\n--- The database here ---\n"
        "No database server runs here and none is needed: the served service keeps its data in an "
        "embedded file database under the directory named by `DATA_DIR`. Where the specification "
        "names a server such as PostgreSQL, the served code opens that file when no connection "
        "setting is given. A missing server is never a reason to change nothing - make the served "
        "code work on the embedded file.\n"
    )


def _the_last_attempt_section(cycle: Any, defect_index: int) -> str:
    """The differently-shaped work order for a defect's last permitted attempt, or "".

    L.4/L.5 change who fixes and when the loop stops; this changes what is
    asked. A defect that has failed `escalate_after()` fixes is on its last
    rung - after this one the defect is left open and the round counts it -
    and every attempt so far had the same shape: patch the lines the failure
    names. A third variation of the instruction that failed twice is the
    measured treadmill: two whole-stage reverts in one run destroyed unrelated
    work with them. So the last attempt asks for a different shape of work -
    the implicated files rewritten whole, where a half-applied earlier state
    cannot survive, and a named blocker as the way out when the specification
    itself cannot produce a passing file. See Initiative L.6 in
    docs/improvement-plan.md.
    """
    from app.models.roles import escalate_after
    from app.sprint import failed_fix_tries

    tries = failed_fix_tries(cycle, defect_index)
    if tries < escalate_after():
        return ""
    defect = cycle.defects[defect_index]
    files = ", ".join(f"`{f}`" for f in (defect.affected_files or [])) or "each file the failure names"
    return (
        f"\n--- This is the attempt after {tries} that failed ---\n"
        "Every earlier attempt at this exact failure was measured, and was reverted or "
        "left it failing; what each one broke is in the notes above. Another attempt of "
        "the same shape - the same lines patched the same way - will be measured the "
        "same way, so this one changes shape:\n"
        f"- Rewrite {files} whole, from the specification and the failing output, rather "
        "than patching lines inside them: a whole file cannot carry the half-applied "
        "state an earlier attempt left behind.\n"
        "- If the specification itself cannot produce a file that passes, do not guess "
        "past it: report that as a blocker and say exactly what the specification is "
        "missing.\n"
    )


def _with_the_attempt(cycle: Any, index: int, stage: str, fix_result: Any, outcome: str, calls: int | None = None,
                      *, root: str = "", sprint: Any = None) -> Any:
    """The cycle with one fix attempt recorded on defect `index` (plan PH.2), with its model calls when counted (AY step 4).

    With `root`, the attempt is kept in the run's fix journal as well (`cause_journal`, deep review 1.4), which outlives
    this cycle: a re-plan clears the cycle, and with it every attempt recorded on its defects. Never raises.
    """
    try:
        from app.agents.ledger import attempt_record

        defect = cycle.defects[index]
        record = attempt_record(stage, fix_result, outcome)
        if root:
            from app.graph import cause_journal

            cause_journal.record(root, defect, record, sprint=sprint)
        if calls is not None:
            record["calls"] = calls
            from app.graph import defect_budget

            defect_budget.record_calls(stage, defect, calls)
        attempts = [*(getattr(defect, "attempts", None) or []), record]
        return cycle.model_copy(update={"defects": [
            item.model_copy(update={"attempts": attempts}) if position == index else item
            for position, item in enumerate(cycle.defects)
        ]})
    except Exception:  # noqa: BLE001 - the cycle stands as it was
        logger.debug("Could not record the fix attempt", exc_info=True)
        return cycle


def _one_more_failed_fix(cycle: Any, index: int) -> Any:
    """The cycle with one more failed fix counted against defect `index`."""
    return cycle.model_copy(update={"defects": [
        item.model_copy(update={"fix_attempts": int(item.fix_attempts or 0) + 1}) if position == index else item
        for position, item in enumerate(cycle.defects)
    ]})


def _defects_to_fix_together(cycle: Any, candidates: list[int]) -> list[int]:
    """As many of `candidates` as can be fixed at once: files apart, bundles apart, at most `max_parallel()`.

    A defect's files are the ones it names and the ones its bundled related
    failures name, since its fixer is shown those too. Staggered exactly as
    work orders are (`_that_do_not_share_a_file`): defects naming no file may
    touch any, so at most one of them goes with the rest.
    """
    from types import SimpleNamespace

    as_tasks = []
    bundles: dict[int, set[int]] = {}
    for index in candidates:
        defect = cycle.defects[index]
        co = _bundle_co_defects(cycle, index)
        bundles[index] = {index, *(position for position, _ in co)}
        files = [*(defect.affected_files or []), *(f for _, d in co for f in (d.affected_files or []))]
        as_tasks.append((index, SimpleNamespace(
            files=files, task_description=str(defect.description or ""), acceptance_criteria=[],
        )))
    chosen: list[int] = []
    claimed: set[int] = set()
    for index, _ in _that_do_not_share_a_file(as_tasks):
        if bundles[index] & claimed:
            continue
        chosen.append(index)
        claimed |= bundles[index]
        if len(chosen) >= concurrent_requests():
            break
    return chosen or candidates[:1]


def _reviews_pending(state: Any) -> list[str]:
    """The reviews in flight that have not produced a result yet."""
    done = state.get("review_results") or {}
    return [item for item in (state.get("reviews_in_flight") or []) if item not in done]


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
        # A testing work order waits while a builder is sent back because the product does not build (PA.3).
        from app.graph.built_before_testing import held_back

        pending = held_back(state, pending)
        going = _that_do_not_share_a_file(
            pending, already_going=must_go, manifests_present=_manifests_the_project_has(state)
        )
        # At most `max_parallel()` at once, and never fewer than the paused
        # workers that must be re-sent to receive their decisions.
        going = going[: max(concurrent_requests(), len(must_go))]
        return [
            Send("specialist_worker", {**state, "__worker_task": task, "__worker_index": index})
            for index, task in going
        ]

    if stage == "review_parallel":
        pending = _reviews_pending(state)
        if not pending:
            return "review_gather"
        return [Send("review_worker", {**state, "__review_item": item}) for item in pending[: concurrent_requests()]]

    if stage == "defect_fix_parallel":
        # Every fixer of the batch still without an output: each was sent once
        # the batch was chosen, so these are the ones paused for a decision.
        pending = _fix_batch_pending(state)
        if not pending:
            return "defect_fix_gather"
        return [Send("defect_fix_worker", {**state, "__fix_index": index}) for index in pending]

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
            from app.agents.settled_answer import validated_leniently

            return validated_leniently(schema, unwrapped(_without_repeats(payload), schema))
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


def _what_the_criteria_s_tests_printed(repo_root: str, defect: Any) -> dict[str, str] | None:
    """The failing tests of the criteria a defect names, with their output; None for any other defect. Never raises."""
    try:
        from app.acceptance import suite as _the_suite
        from app.acceptance.junit import tags_in

        return _the_suite.what_the_criteria_s_tests_printed(repo_root, tags_in(str(getattr(defect, "description", "") or "")))
    except Exception:  # noqa: BLE001 - a brief is better without it than absent
        return None


def _what_the_unit_tests_printed(repo_root: str, defect: Any) -> dict[str, str] | None:
    """A unit-test defect's own failing tests and their output (HR F3); None for any other defect. Never raises."""
    try:
        from app.acceptance import suite as _the_suite

        return _the_suite.what_the_unit_tests_printed(repo_root, str(getattr(defect, "description", "") or ""),
                                                      str(getattr(defect, "caught_by", "") or ""))
    except Exception:  # noqa: BLE001 - the last failing command stands in, as before
        return None


def _what_the_last_failure_printed(run_id: str | None, defect: Any = None) -> dict[str, str] | None:
    """The last failing command's own output, or None. Never raises.

    Imported here rather than at module scope: the transcript module is
    observability, and a defect fix must not fail because a record could not be
    read. Never for a mutation finding (HR2.fix.6): its product is not failing, and the last command was another
    defect's - mutation fixers were shown it 78 times to their own evidence twice; the finding says what settles it.
    """
    try:
        from app.acceptance import mutation_guided

        if defect is not None and mutation_guided.is_a_finding(defect):
            return None
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

        note = carry_over_note(inner_thread_id, repo_root, stage_name, why)
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
    see `_ask_about_high_confidence_diagnostics`.

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


#: What a test runner or build writes where its own configuration says, so a
#: command that never names it may still have written it.
_RUNNER_OUTPUT = re.compile(
    r"\.(?:xml|log|lcov|tap|tsbuildinfo)$|(?:^|/)(?:reports?|coverage|test-results|junit|logs?)/",
    re.I,
)


def _a_runner_writes(path: str) -> bool:
    """Whether `path` is the kind of file a runner writes: a report, a log, coverage."""
    return bool(_RUNNER_OUTPUT.search(path))


def _files_the_conversation_wrote(result: Mapping[str, Any]) -> list[str]:
    """The files a stage's conversation wrote, deleted or moved, by the tools that did it; in the order first written."""
    messages = list(result.get("messages") or [])
    results = {
        str(getattr(message, "tool_call_id", "")): getattr(message, "content", "")
        for message in messages if getattr(message, "type", None) == "tool"
    }
    written: list[str] = []
    for message in messages:
        for call in getattr(message, "tool_calls", None) or ():
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
            args = (call.get("args") if isinstance(call, dict) else getattr(call, "args", None)) or {}
            call_id = str(call.get("id") if isinstance(call, dict) else getattr(call, "id", ""))
            if name in _FILE_WRITES and _a_tool_result_that_succeeded(results.get(call_id)):
                for key in ("relative_path", "destination"):
                    if args.get(key):
                        path = _without_a_leading_dot_slash(str(args[key]))
                        if path not in written:
                            written.append(path)
    return written


def _a_fix_recorded_from_its_writes(stage_name: str, result: Mapping[str, Any]) -> Any | None:
    """What a fix stage did, when it spent its model calls without ever answering; None when it wrote nothing.

    Measured live: fix stages kept editing to the last call, ignored the
    warning that their budget was nearly spent, and were then started over on
    a fresh conversation twice more - three conversations of forty calls for
    one defect, with the edits of the first already on disk. The harness holds
    the receipts of what was written. It records the fix from them and lets the
    measurement after a fix decide, as it does for an answered one: a fix that
    breaks a passing test is reverted, one whose own tests still fail stays
    open (Initiative AO).
    """
    # A build stage too: measured on one run, a builder wrote the product, ran out of calls twice and was started over
    # each time, about 30 minutes; the test round after it measures what was written, as for a fix.
    if not str(stage_name or "").startswith(("defect_fix_", "specialist_")):
        return None
    written = _files_the_conversation_wrote(result)
    if not written:
        return None
    try:
        from app.agents.specialists import SpecialistOutput

        return SpecialistOutput(
            changed_files=written,
            decisions=[
                "The stage used all of its model calls without writing its answer. Recorded by the "
                "harness from the files it wrote; the measurement after the fix decides whether it worked."
            ],
        )
    except Exception:  # noqa: BLE001 - then the stage is started over, as before
        return None


def _files_it_claims_but_never_wrote(result: Mapping[str, Any], answer: Any) -> list[str]:
    """The files an answer's `changed_files` names that nothing in its conversation wrote.

    Measured on one run: asked by a re-planned milestone to cut a file it
    owned, a stage read that file once and answered that it had removed a
    30-line block, replaced inline styles with classes, edited with
    `replace_lines` and run the tests - none of which it did. The file was
    unchanged, the milestone review blocked on the same size again, and the
    record said the work order was delivered.

    A file a terminal command names may have been changed by it, and is not
    judged; nor, once the stage ran a command, is a report, log or coverage
    file - a runner writes those where its configuration says. Measured on one
    run: a test round reporting the JUnit files its test commands wrote was
    asked what it had done.
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
        if commands and _a_runner_writes(plain):
            return True
        return any(plain.rsplit("/", 1)[-1] in command for command in commands)

    return [name for name in claimed if not _was_written(name)]


def _claims_dropped_from_the_record(structured_response: Any, never_wrote: list[str]) -> Any:
    """The answer with the claims nothing wrote dropped from `changed_files`.

    The record keeps only what changed: a phantom claim left standing says a
    work order was delivered while the file is untouched, and the milestone
    review then blocks on the same evidence twice (Initiative Q.4). An answer
    that cannot be copied comes back as it is - the caller's warning has
    already said what was claimed.
    """
    if not never_wrote or not hasattr(structured_response, "model_copy"):
        return structured_response
    return structured_response.model_copy(update={"changed_files": [
        name for name in structured_response.changed_files if str(name).strip() not in never_wrote
    ]})


def _ask_about_high_confidence_diagnostics(
    agent: Any, inner_thread_id: str, callbacks: Any, diagnostics: list[str], run_id: str | None, stage: str,
    schema: Any = None,
) -> dict[str, Any] | None:
    """Ask the conversation once to fix high-confidence errors in modified files before exiting."""
    bullet_points = "\n".join(diagnostics[:4])
    text = (
        "The checks run on the files modified in this stage found errors:\n"
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


def _the_names_the_module_has(project: Path, importer: Path, finding: dict) -> str:
    """What the module an import reads defines, after a finding about a missing name; "" when it cannot say."""
    try:
        from app.analysis.language_service import the_names_the_module_has

        return the_names_the_module_has(project, importer, finding)
    except Exception:  # noqa: BLE001 - the finding goes out as it was
        return ""


#: Findings an agent stage is told of after its writes.
MOST_DIAGNOSTICS = 4
#: Findings a whole-file pass (a fix's rewrite, a draft's repair) is given and counted by: every one for its files,
#: up to the compiler check's own bound. At 4, a pass saw the first four of a file's errors and the count of a pass
#: with nine was the count of one with four (A2).
MOST_DIAGNOSTICS_FOR_A_PASS = 12


def _diagnostics_in_files_touched(
    state: Any, result: dict[str, Any], structured_response: Any, stage_name: str = "", most: int = MOST_DIAGNOSTICS,
) -> list[str]:
    """High-confidence syntax or reference diagnostics in files modified by this stage.

    Runs what an IDE would underline (via `language_service.underlined_any`) over the
    files touched by this stage. Only certain errors (ReferenceError, missing exports,
    undeclared names) are reported, bounded to `most` items - and not an
    import of a file another work order owns (`_another_work_order_writes_it`).
    A declaration or export the pack's scaffold relies on that a touched file
    dropped comes first (`entry_exports.what_a_stage_broke`).
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

    # Only writes that happened: measured on one run, QA was refused an edit of the product's `app.ts`, was
    # then asked to fix that file's missing import, and spent sixteen more refused writes on it.
    results = {
        str(getattr(message, "tool_call_id", "")): getattr(message, "content", "")
        for message in result.get("messages") or () if getattr(message, "type", None) == "tool"
    }
    for message in result.get("messages") or ():
        for call in getattr(message, "tool_calls", None) or ():
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
            args = (call.get("args") if isinstance(call, dict) else getattr(call, "args", None)) or {}
            call_id = str(call.get("id") if isinstance(call, dict) else getattr(call, "id", ""))
            if name in _FILE_WRITES and _a_tool_result_that_succeeded(results.get(call_id)):
                for key in ("relative_path", "destination"):
                    if args.get(key):
                        files_to_check.add(_without_a_leading_dot_slash(str(args[key])))

    # What the pack's scaffold relies on and this stage's writes dropped, first: the same checks a test round raises
    # as defects, told to the stage that broke them (`entry_exports.what_a_stage_broke`; no model call).
    from app.stacks.entry_exports import what_a_stage_broke

    diagnostics: list[str] = what_a_stage_broke(root, files_to_check)[:most]
    if len(diagnostics) >= most:
        return _with_known_causes(root, diagnostics)
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
                    msg += _the_names_the_module_has(project or Path(root), target, finding)
                    diagnostics.append(f"- In `{relative}` line {line}: {msg}")
                    if len(diagnostics) >= most:
                        return _with_known_causes(root, diagnostics)
        except Exception:  # noqa: BLE001
            continue

    found = [*diagnostics, *_what_the_compiler_says_of(root, files_to_check, stage_name, pinned or "")][:most]
    return _with_known_causes(root, found)


def _with_known_causes(root: str, diagnostics: list[str]) -> list[str]:
    """Each diagnostic that carries an error the stack pack knows, with its cause (`known_errors`); never raises."""
    try:
        from app.stacks.known_errors import with_known_causes_in_lines

        return with_known_causes_in_lines(root, diagnostics)
    except Exception:  # noqa: BLE001 - the diagnostics as found
        return diagnostics


def _the_milestone_is_unfinished(root: str, stage_name: str) -> bool:
    """Whether a file another work order of this milestone owns is not written yet.

    A compiler reads the whole project, so a name defined in a file another
    work order has not written is an error to it - and none of this stage's.
    Only a specialist building a work order is asked this; by the time a fix
    stage runs, every work order is done.
    """
    if not str(stage_name or "").startswith("specialist_"):
        return False
    try:
        import json

        from app.tools.repository import WORK_ORDER_FILES

        table = json.loads((Path(root) / WORK_ORDER_FILES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(table, dict) and any(
        owner != stage_name and not (Path(root) / planned).exists() for planned, owner in table.items()
    )


def _what_the_compiler_says_of(root: str, touched: set[str], stage_name: str, project: str) -> list[str]:
    """The compiler's errors, when this stage changed code in a compiled language; see `compiler_check`.

    Errors in the files the stage touched come first. Not asked while another
    work order's files are still to be written (`_the_milestone_is_unfinished`).
    """
    from app.analysis import compiler_check

    compiled = sorted(name for name in touched if name.lower().endswith(compiler_check.SUFFIXES))
    if not compiled or _the_milestone_is_unfinished(root, stage_name):
        return []
    try:
        found = compiler_check.findings(root, project, compiled)
    except Exception as error:  # noqa: BLE001 - a check that cannot run says nothing
        degraded("check.compiler_findings_in_touched_files", error)
        return []
    found.sort(key=lambda finding: finding["file"] not in touched)
    # Where a package really declares a name the code asked for in the wrong place (PACKAGE_EXPORTS_NAMED).
    return [f"- In `{f['file']}` line {f['line']}: {f['message']} (the compiler)"
            f"{compiler_check.what_the_package_has(root, project, f)}" for f in found]


#: How much of a failing unit run a defect carries.
UNIT_FAILURE_TAIL_CHARACTERS = 3_000


#: A line of a runner's output that states what went wrong: an error or exception
#: named, a failure reported - in the words runners of every language use.
_STATES_AN_ERROR = re.compile(
    r"\b\w*(?:Error|Exception)\b|\berror\b|\bFAIL(?:ED|URE)?\b|\bfailed\b|panicked|\bassert|\bcrash(?:ed|es)?\b|\babort(?:ed|s)?\b",
    re.I,
)
#: A count of no failures, which says nothing went wrong: `Failed: 0`, `0 failed`, `errors=0`. Measured on one C# run:
#: "Passed! - Failed: 0, Passed: 9" was taken as the cause, and the host's crash after it ("aborted ... crashed")
#: was left out.
_A_ZERO_COUNT = re.compile(r"\b(?:fail(?:ed|ures?)?|errors?)\b\s*[:=]?\s*0\b|\b0\s+(?:fail(?:ed|ures?)?|errors?)\b", re.I)
#: A line that only says where: a stack frame, or a runner's banner around one.
_ONLY_SAYS_WHERE = re.compile(r'^\s*(?:File "|at\s|\S+:\d+: in\b|<frozen\b|_{5,}|={5,}|-{5,}|\^+\s*$|\?\?\?)')
#: Lines of a failure's cause kept, the last ones its output gives.
MOST_CAUSE_LINES = 8


def _first_sentence(text: Any) -> str:
    """A defect's first sentence: its check's own words, the same each time it is raised."""
    return re.split(r"(?<=[.!?])\s|\n", " ".join(str(text or "").split()), maxsplit=1)[0]


def superseded_by_one_cause(cycle: Any, new_defects: list[Any]) -> Any:
    """`cycle` with its open per-criterion acceptance defects closed as `superseded` when this round raised the one
    defect for one wrong answer behind them (LR.53).

    Measured on one run: the round raised the one defect, but the eleven per-criterion defects of the round before
    stayed open beside it, so the fixers still worked through twelve and the grouping saved nothing. Each criterion's
    own failures are measured again at the next round, which raises whatever still fails.
    """
    from app.graph.acceptance_nodes import ONE_CAUSE_MARK

    if not any(ONE_CAUSE_MARK in str(getattr(item, "description", "")) for item in new_defects):
        return cycle
    # A criterion this round raises again on its own still fails beside the one cause (LF.1259: one step many tests
    # stop at leaves the criteria with other failures raised), so its defect stays open.
    again = {_first_sentence(getattr(item, "description", "")) for item in new_defects
             if str(getattr(item, "description", "")).startswith("[AC-")}
    closed = [
        defect.model_copy(update={"status": "superseded"})
        if defect.status == "open" and str(defect.description).startswith("[AC-") and ONE_CAUSE_MARK not in defect.description
        and _first_sentence(defect.description) not in again
        else defect
        for defect in cycle.defects
    ]
    return cycle.model_copy(update={"defects": closed})


def _refreshed_by_the_round(cycle: Any, raised: list[Any], test_round: int) -> tuple[Any, list[Any]]:
    """`cycle` with each open defect this round raises again refreshed from it, and the ones raised again.

    Measured on one run: "The unit tests fail." was raised by round 0 and again
    by round 1 with a longer output, both stayed open, and round 2 sent two fix
    stages of forty calls each, one after the other, at the one failure. Raised
    again means the same first sentence from the same check while still open;
    the newer description, output and round replace the older.
    """
    defects = list(getattr(cycle, "defects", None) or [])
    repeated: list[Any] = []
    for item in raised:
        key = (_first_sentence(getattr(item, "description", "")), str(getattr(item, "source", "") or ""))
        # The same measured cause is raised again whatever its first sentence now says (deep review 1.1).
        at = next((index for index, defect in enumerate(defects)
                   if defect.status == "open"
                   and (cause.same_cause(defect, item)
                        or (_first_sentence(defect.description), str(defect.source or "")) == key)), None)
        if at is None:
            continue
        defects[at] = defects[at].model_copy(update={
            "description": item.description,
            "actual_behavior": item.actual_behavior,
            "reproduction_steps": item.reproduction_steps,
            "affected_files": list(item.affected_files or defects[at].affected_files),
            "failing_criteria": list(item.failing_criteria or defects[at].failing_criteria),
            "found_in_round": test_round,
            **({"kind": item.kind, "evidence": list(item.evidence), "cause_key": item.cause_key}
               if getattr(item, "cause_key", "") else {}),
        })
        repeated.append(item)
    if not repeated:
        return cycle, []
    return cycle.model_copy(update={"defects": defects}), repeated


def _what_the_failure_says(output: str) -> str:
    """The lines of a runner's output that state what went wrong, the last of them; "" when none does.

    Measured on one run: a test file had `await` in a plain function, the unit
    run's output ended in pytest's and the import system's frames, and the line
    that said so - `SyntaxError: 'await' outside async function` - was past the
    600 characters a sprint planned again is shown of a defect. Its lead planned
    new test files and left the broken one as it was.
    """
    lines = [" ".join(line.split()) for line in str(output or "").splitlines()]
    stated = [line for line in lines if line and _STATES_AN_ERROR.search(_A_ZERO_COUNT.sub("", line))
              and not _ONLY_SAYS_WHERE.match(line)]
    return "\n".join(dict.fromkeys(stated[-MOST_CAUSE_LINES:]))[:1_000]


#: What a failing-unit-tests defect is told when the locked suite passes in full beside it (deep review B17). Measured
#: on two runs: the unit tests that shipped failing asserted a key order, a count other tests' data changed, and an
#: empty 404 body the interface does not give; the fixers changed the product for them and were reverted.
BESIDE_A_GREEN_SUITE = (
    "The locked acceptance suite passes in full on this product, so it does what the specification asks. A unit test "
    "that fails here may assert what the specification does not - an order of keys, a count that depends on data "
    "other tests leave, a body the interface does not give. Correct such a test to what the specification and the "
    "acceptance suite say, keeping its name; change the product only for a failure the specification backs, and say "
    "in your answer which you did."
)


def _the_unit_tests_fail(milestone: Any, output: str, *, beside_a_green_suite: bool = False,
                         failing: Sequence[str] = ()) -> Any:
    """The defect for a failing unit run, owned by the role that writes the product.

    Not the testing role's: a defect it owns is closed by changing the test,
    and a failing unit test is first the product's to answer. `beside_a_green_suite`: the locked suite passed in
    full on the same product, and the fixer is told the unit test may be the one that is wrong. `failing`: the unit
    tests the runner's report names failing, its evidence (deep review 2026-11-18, item 1.1).
    """
    from app.agents.specialists import ReportedDefect

    roles = [str(getattr(t, "specialist_role", "")) for t in (getattr(milestone, "delegated_tasks", None) or [])]
    owner = next((role for role in roles if role and role not in {"testing", "documentation"}), "testing")
    tail = str(output or "").strip()[-UNIT_FAILURE_TAIL_CHARACTERS:]
    # From the whole run, not its tail: measured on one gate run, the project's
    # command ran the page's tests and then the service's, the tail was the
    # service's passing output from the page runner's timing line on, and the
    # failing test and its error - before it - were in no defect.
    # Grouped by cause when the runner's report was read: the last error lines of the output are often one cause's.
    from app import ci

    causes = ci.the_distinct_causes(str(output or "")) or _what_the_failure_says(str(output or ""))
    # The note a stage's own command gets for the same output: measured on one
    # run, two fixes read `spawn /bin/sh ENOENT` - a child started in a working
    # directory that does not exist - as "no shell here" and changed nothing.
    from app.tools.sandbox import _a_missing_path_that_is_here

    here = _a_missing_path_that_is_here({"stdout": str(output or "")})
    return ReportedDefect(
        description=UNIT_TESTS_FAIL + (f" It says:\n{causes}\n" if causes else "")
        + (f" {here}\n" if here else "")
        + " The runner's output ends:\n" + (tail or "(no output)"),
        severity="major",
        reproduction_steps="Run the project's unit test command.",
        expected_behavior="Every unit test passes.",
        actual_behavior=(("The unit test command exits non-zero. It says:\n" + causes) if causes
                         else "The unit test command exits non-zero.")
        + (f"\n{BESIDE_A_GREEN_SUITE}" if beside_a_green_suite else ""),
        affected_files=[],
        owner=owner,
        **_the_unit_run_s_evidence(output, failing),
    )


def _the_failing_unit_tests(root: str) -> list[str]:
    """The unit tests the pack's report on disk names failing, or the one name of a run that wrote none; [] when it
    cannot say. Never raises."""
    try:
        from app import ci

        read = ci.unit_outcomes_in_the_pack_s_report(root)
        if read is None:
            return []
        outcomes, found = read
        if not found:
            return [ci.UNIT_TESTS_DID_NOT_RUN]
        return sorted(name for name, outcome in outcomes.items() if outcome not in ("passed", "skipped"))
    except Exception:  # noqa: BLE001 - a defect without evidence is compared by its words, as before
        return []


def _the_unit_run_s_evidence(output: str, failing: Sequence[str]) -> dict[str, Any]:
    """The kind and evidence of a failing unit run: each failing test it names, else the error its output ends on."""
    from app import ci

    named = [str(name) for name in failing or () if str(name).strip() and str(name) != ci.UNIT_TESTS_DID_NOT_RUN]
    if named:
        return {"kind": cause.FAILING_TEST, "evidence": [cause.a_failing_test(name) for name in named][:cause.MOST_EVIDENCE]}
    said = cause.an_error_line(output)
    if not said:
        return {}
    # Ran and wrote no report: the tests did not compile or could not start.
    return {"kind": cause.COMPILE_ERROR if ci.UNIT_TESTS_DID_NOT_RUN in list(failing or ()) else cause.FAILING_TEST,
            "evidence": [said]}


#: Files that are a page or a page's component, whatever framework draws it.
_PAGE_SUFFIXES = frozenset({".tsx", ".jsx", ".vue", ".svelte", ".html", ".astro"})


def _with_the_contract_s_server_errors(state: Any, test_result: Any, milestone: Any) -> Any:
    """`test_result` with a defect for each contract line a bare request makes the server fail on, behind the switch.

    Measured on one run: a bare `POST /notes` and `PUT /notes/:id` answered 500 on a green suite; the contract's checks
    ran only at release, so the crash shipped as a gap and no fixer was given it. Asked when the locked suite is green:
    a red one has its own defects, and the checks start the product once more. Never raises.
    """
    try:
        from app.acceptance import interface_contract
        from app.agents.specialists import ReportedDefect
        from app.graph import acceptance_nodes

        root = state["repository"].root_path
        if not interface_contract.server_errors_at_a_round_switch.enabled() or not acceptance_nodes.suite.is_locked(root):
            return test_result
        if any(str(d.description or "").startswith(interface_contract.SERVER_FAILED) for d in test_result.defects):
            # Writes made at once, and requests at the edges, are other probes' findings: asked whatever it says.
            return _with_a_round_trip_defect(state, _with_an_edge_case_defect(
                state, _with_a_concurrent_write_defect(state, test_result, milestone), milestone), milestone)
        from app.acceptance import wrong_shape_body_probe

        errors = interface_contract.server_errors(root) or []
        bad_body = interface_contract.bad_body_errors(root) or []
        wrong_shape = wrong_shape_body_probe.wrong_shape_errors(root) or []
        if errors or bad_body or wrong_shape:
            logger.warning("A green round's contract checks made the server fail on %d line(s)",
                           len(errors) + len(bad_body) + len(wrong_shape))
            test_result = _with_a_server_error_defect(state, test_result, milestone, errors, bad_body, wrong_shape)
        test_result = _with_a_concurrent_write_defect(state, test_result, milestone)
        test_result = _with_an_edge_case_defect(state, test_result, milestone)
        test_result = _with_a_round_trip_defect(state, test_result, milestone)
        return _with_a_kept_empty_defect(state, _with_an_emptied_field_defect(state, test_result, milestone), milestone)
    except Exception as error:  # noqa: BLE001 - the round as measured stands
        degraded("round_check.contract_server_errors", error)
        return test_result


def _with_a_concurrent_write_defect(state: Any, test_result: Any, milestone: Any) -> Any:
    """`test_result` with one defect for each create line that did not keep creates sent at once, behind its switch. Never raises.

    Measured: in several benchmark families products lost writes made at the same moment, which only an external
    quality test caught (`app.acceptance.concurrent_write_probe`).
    """
    try:
        from app.acceptance import concurrent_write_probe
        from app.agents.specialists import ReportedDefect

        if not concurrent_write_probe.enabled() or any(
            str(d.description or "").startswith(concurrent_write_probe.CONCURRENT_WRITES_LOST) for d in test_result.defects
        ):
            return test_result
        found = concurrent_write_probe.concurrent_write_errors(state["repository"].root_path) or []
        if not found:
            return test_result
        logger.warning("A green round's concurrent-write probe: %d create line(s) did not keep writes made at once", len(found))
        n = concurrent_write_probe.AT_ONCE
        defect = ReportedDefect(
            description=concurrent_write_probe.concurrent_write_description(found),
            severity="major",
            reproduction_steps="; ".join(
                f"send {n} `{c.method} {c.path}` requests at the same moment, each with one valid body"
                + (f", then read `GET {f.get('list')}`" if f.get("list") else "") for c, f in found[:4]),
            expected_behavior="; ".join(
                f"each of the {n} writes to `{c.path}` is answered under 500, carries its own id, and is listed"
                for c, _ in found[:4]),
            actual_behavior="; ".join(f"`{c.method} {c.path}`: {concurrent_write_probe.what_came_back(f)}" for c, f in found[:4]),
            affected_files=[],
            owner=_the_unit_tests_fail(milestone, "").owner,
            kind=cause.PROBE_FINDING,
            evidence=[cause.a_probe_request("concurrent writes", f"{c.method} {c.path}") for c, _ in found][:cause.MOST_EVIDENCE],
        )
        return test_result.model_copy(update={"defects": [*test_result.defects, defect]})
    except Exception as error:  # noqa: BLE001 - the round as measured stands
        degraded("round_check.concurrent_write", error)
        return test_result


def _with_an_edge_case_defect(state: Any, test_result: Any, milestone: Any) -> Any:
    """`test_result` with one defect for the requests at the contract's edges the product failed, behind its switch. Never raises.

    Deep review 2026-11-18, item B1: hidden quality tests lose most often on requests no locked test sends - a field
    missing, empty, of the wrong type or very long, an id that is no number or already deleted
    (`app.acceptance.edge_probe`).
    """
    try:
        from app.acceptance import edge_probe
        from app.agents.specialists import ReportedDefect

        if not edge_probe.enabled() or any(
            str(d.description or "").startswith(edge_probe.EDGE_CASES_FAILED) for d in test_result.defects
        ):
            return test_result
        found = edge_probe.edge_errors(state["repository"].root_path) or []
        if not found:
            return test_result
        logger.warning("A green round's edge probe: %d request(s) at the contract's edges were not handled", len(found))
        defect = ReportedDefect(
            description=edge_probe.edge_description(found),
            severity="major",
            reproduction_steps="; ".join(
                f"send `{case['method']} {case['shown']}` {case['what']}" for case, _ in found[:8]),
            expected_behavior=("a status under 500; a refused write stores and changes nothing; a record created "
                               "is read back with each text as it was sent"),
            actual_behavior="; ".join(
                f"`{case['method']} {case['shown']}` {case['what']} {edge_probe.what_came_back(case, f)}"
                for case, f in found[:8]),
            affected_files=[],
            owner=_the_unit_tests_fail(milestone, "").owner,
            kind=cause.PROBE_FINDING,
            evidence=[cause.a_probe_request("edges", f"{case['method']} {case['shown']} {case['what']}")
                      for case, _ in found][:cause.MOST_EVIDENCE],
        )
        return test_result.model_copy(update={"defects": [*test_result.defects, defect]})
    except Exception as error:  # noqa: BLE001 - the round as measured stands
        degraded("round_check.edge_case", error)
        return test_result


def _with_a_round_trip_defect(state: Any, test_result: Any, milestone: Any) -> Any:
    """`test_result` with one defect for the round trips the product failed: a record deleted twice, or a long text
    not read back whole (`app.acceptance.round_trip_probe`). A quality check, so on with no switch. Never raises.

    Measured: a service passed every hidden acceptance test and lost the hidden quality tests of a second delete
    answered 204 where the contract gives 404, and of a long body not read back as written; no probe asked either.
    The brief decides which refusals of a long value are findings (LF.1298).
    """
    try:
        from app.acceptance import round_trip_probe

        if any(str(d.description or "").startswith(round_trip_probe.ROUND_TRIPS_FAILED) for d in test_result.defects):
            return test_result
        brief = str(getattr(state.get("document"), "text", "") or "")
        found = round_trip_probe.round_trip_errors(state["repository"].root_path, brief or None) or []
        if not found:
            return test_result
        logger.warning("A green round's round-trip probe: %d round trip(s) did not read back as written", len(found))
        defect = round_trip_probe.a_defect(found, _the_unit_tests_fail(milestone, "").owner)
        return test_result.model_copy(update={"defects": [*test_result.defects, defect]})
    except Exception as error:  # noqa: BLE001 - the round as measured stands
        degraded("round_check.round_trip", error)
        return test_result


def _with_a_page_check_defect(state: Any, test_result: Any, milestone: Any) -> Any:
    """`test_result` with one defect for the harness's browser checks of a page product it fails, behind its switch.

    Deep review 2026-11-18, item B5: no check typed markup into a field, watched the console while an item was added,
    measured a 360px screen or reloaded the page (`app.acceptance.page_probe`). Never raises.
    """
    try:
        from app.acceptance import page_probe
        from app.agents.specialists import ReportedDefect

        if not page_probe.enabled() or any(
            str(d.description or "").startswith(page_probe.PAGE_CHECK_FAILED) for d in test_result.defects
        ):
            return test_result
        brief = str(getattr(state.get("document"), "text", "") or "")
        found = page_probe.page_errors(state["repository"].root_path, brief) or []
        if not found:
            return test_result
        logger.warning("A green round's page checks: the page failed %d of them", len(found))
        defect = ReportedDefect(
            description=page_probe.page_description(found),
            severity="major",
            reproduction_steps=(
                "Open the page in a browser; type text into each text field and send the form the way the page "
                f"sends it; watch the console and the network; measure it at a {page_probe.PHONE[0]}px-wide screen; "
                "reload it"),
            expected_behavior=("text typed is shown as text; no console error and no request answered 500 or "
                               f"failing; no sideways scrolling at {page_probe.PHONE[0]}px; what persists is shown "
                               "after a reload"),
            actual_behavior=page_probe.page_description(found)[len(page_probe.PAGE_CHECK_FAILED):].strip()[:1500],
            affected_files=[],
            owner="ui_ux",
        )
        return test_result.model_copy(update={"defects": [*test_result.defects, defect]})
    except Exception as failure:  # noqa: BLE001 - the round as measured stands
        degraded("round_check.page_checks", failure)
        return test_result


def _with_an_emptied_field_defect(state: Any, test_result: Any, milestone: Any) -> Any:
    """`test_result` with one defect for each write that accepted a field the criteria refuse empty. Never raises.

    Measured on one run: the suite tried an empty title on create only, the product accepted it on update, and the run
    shipped as passing while a hidden test failed.
    """
    try:
        from app.acceptance import interface_contract
        from app.agents.specialists import ReportedDefect
        from app.graph import acceptance_nodes

        root = state["repository"].root_path
        if any(str(d.description or "").startswith(interface_contract.EMPTIED_FIELD_ACCEPTED) for d in test_result.defects):
            return test_result
        accepted = interface_contract.emptied_field_errors(root) or []
        if not accepted:
            return test_result
        logger.warning("A green round's emptied-field probe: %d write(s) accepted an empty field", len(accepted))
        defect = ReportedDefect(
            description=interface_contract.emptied_field_description(accepted),
            severity="major",
            reproduction_steps="; ".join(
                f"send `{c.method} {c.path}` a valid body with `{c.emptied}` set to an empty string" for c, _ in accepted[:6]),
            expected_behavior="; ".join(f"`{c.method} {c.path}` refuses it with a 4xx and stores nothing" for c, _ in accepted[:6]),
            actual_behavior="; ".join(f"`{c.method} {c.path}` answered {status}" for c, status in accepted[:6]),
            affected_files=sorted({f for f, _ in acceptance_nodes.where_errors_become_5xx(root)}),
            owner=_the_unit_tests_fail(milestone, "").owner,
        )
        return test_result.model_copy(update={"defects": [*test_result.defects, defect]})
    except Exception as error:  # noqa: BLE001 - the round as measured stands
        degraded("round_check.emptied_field", error)
        return test_result


def _with_a_kept_empty_defect(state: Any, test_result: Any, milestone: Any) -> Any:
    """`test_result` with one defect for the writes that refuse an empty value of a field the brief does not refuse
    empty (`interface_contract.kept_empty_errors`). Never raises.

    Measured on five runs of five stacks: the brief refused only an empty title, every product also refused an empty
    body, and a hidden test writing a note with an empty body failed on it.
    """
    try:
        from app.acceptance import interface_contract
        from app.agents.specialists import ReportedDefect
        from app.graph import acceptance_nodes

        root = state["repository"].root_path
        if any(str(d.description or "").startswith(interface_contract.KEPT_EMPTY_REFUSED) for d in test_result.defects):
            return test_result
        brief = str(getattr(state.get("document"), "text", "") or "")
        refused = interface_contract.kept_empty_errors(root, brief) or []
        if not refused:
            return test_result
        logger.warning("A green round's kept-when-empty probe: %d write(s) refused an empty field the brief keeps", len(refused))
        defect = ReportedDefect(
            description=interface_contract.kept_empty_description(
                refused, interface_contract.what_the_brief_refuses_empty(root)),
            severity="major",
            reproduction_steps="; ".join(
                f"send `{c.method} {c.path}` a valid body with `{c.emptied}` set to an empty string" for c, _ in refused[:6]),
            expected_behavior="; ".join(
                f"`{c.method} {c.path}` takes it and answers `{c.emptied}` back as an empty string" for c, _ in refused[:6]),
            actual_behavior="; ".join(f"`{c.method} {c.path}` answered {status}" for c, status in refused[:6]),
            affected_files=sorted({f for f, _ in acceptance_nodes.where_errors_become_5xx(root)}),
            owner=_the_unit_tests_fail(milestone, "").owner,
        )
        return test_result.model_copy(update={"defects": [*test_result.defects, defect]})
    except Exception as error:  # noqa: BLE001 - the round as measured stands
        degraded("round_check.kept_empty", error)
        return test_result


def _with_the_lock_s_server_errors(state: Any, test_result: Any, milestone: Any) -> Any:
    """`test_result` with a defect for what the contract's checks at the lock found, red suite or green. Never raises.

    Settled like the green round's: by the same checks, run again.
    """
    try:
        from app.acceptance import interface_contract

        errors = interface_contract.errors_found_at_the_lock(state["repository"].root_path)
        if not errors or any(
            str(d.description or "").startswith(interface_contract.SERVER_FAILED) for d in test_result.defects
        ):
            return test_result
        return _with_a_server_error_defect(state, test_result, milestone, errors)
    except Exception as error:  # noqa: BLE001 - the round as measured stands
        degraded("round_check.locked_suite_server_errors", error)
        return test_result


def _one_of_them_said(root: str, errors: list[Any]) -> str:
    """`. One such request, sent again by the harness: ...` - what the server-error probe heard from one of `errors`
    and what the server printed for it; "" when it heard from none of them."""
    from app.acceptance import interface_contract

    said = interface_contract.what_a_server_error_said(root)
    calls = {f"`{check.method} {check.path}`" for check, _ in errors}
    return f". One such request, sent again by the harness: {said[:900]}" if said and said.split(" answered", 1)[0] in calls else ""


def _with_a_server_error_defect(state: Any, test_result: Any, milestone: Any, errors: list[Any],
                                bad_body: list[Any] | None = None, wrong_shape: list[Any] | None = None) -> Any:
    """`test_result` with one defect for `errors`, each a contract check and the 5xx it got; for `bad_body`, the same for
    a body nothing can parse; for `wrong_shape`, (check, status, body) for JSON that is not an object."""
    from app.acceptance import interface_contract
    from app.agents.specialists import ReportedDefect
    from app.graph import acceptance_nodes

    root = state["repository"].root_path
    unparsable = list(bad_body or [])
    shaped = list(wrong_shape or [])
    defect = ReportedDefect(
        description=interface_contract.server_error_description(errors, unparsable, shaped),
        severity="major",
        reproduction_steps="; ".join([
            *(f"send `{check.method} {check.path}` with no body to the running service" for check, _ in errors[:6]),
            *(f"send `{check.method} {check.path}` the JSON content type and the body "
              f"`{interface_contract.A_BODY_NOTHING_CAN_PARSE}`" for check, _ in unparsable[:6]),
            *(f"send `{check.method} {check.path}` the JSON content type and the body `{body}`"
              for check, _, body in shaped[:6]),
        ]),
        expected_behavior="; ".join([
            *(f"`{check.method} {check.path}` answers {' or '.join(map(str, check.statuses or (check.status,)))}"
              for check, _ in errors[:6]),
            *(f"`{check.method} {check.path}` refuses a body it cannot parse with a status under 500" for check, _ in unparsable[:6]),
            *(f"`{check.method} {check.path}` refuses a JSON body that is not an object with a status under 500"
              for check, _, _ in shaped[:6]),
        ]),
        actual_behavior="; ".join([
            *(f"`{check.method} {check.path}` answered {status}" for check, status in [*errors[:6], *unparsable[:6]]),
            *(f"`{check.method} {check.path}` answered {status} to `{body}`" for check, status, body in shaped[:6]),
        ]) + _one_of_them_said(root, errors),
        affected_files=sorted({f for f, _ in acceptance_nodes.where_errors_become_5xx(root)}),
        owner=_the_unit_tests_fail(milestone, "").owner,
        kind=cause.PROBE_FINDING,
        evidence=[
            *(cause.a_probe_request("contract, no body", f"{check.method} {check.path}") for check, _ in errors),
            *(cause.a_probe_request("contract, a body nothing can parse", f"{check.method} {check.path}")
              for check, _ in unparsable),
            *(cause.a_probe_request("contract, a body that is not an object", f"{check.method} {check.path}")
              for check, _, _ in shaped),
        ][:cause.MOST_EVIDENCE],
    )
    return test_result.model_copy(update={"defects": [*test_result.defects, defect]})


def _the_served_app_is_the_scaffold_s_stub(relative: str, owner: str) -> Any:
    """The wiring defect for a served app that is still the scaffold's stub.

    The dominant live failure: 31 of 35 locked tests failed against the stub
    while everything drafted sat in files nothing served, and the fixers
    chased the criteria one by one without exiting. One bundled defect names
    the gap itself (Initiative K.3; see `scaffold.entrypoint_is_still_the_stub`).
    """
    from app.agents.specialists import ReportedDefect

    # The page's own stub is the page's specialist's to replace: one run
    # handed every defect to the backend specialist, and none of its fixers
    # ever touched the page component the acceptance suite was served.
    if PurePosixPath(relative).suffix.lower() in _PAGE_SUFFIXES:
        owner = "ui_ux"
    return ReportedDefect(
        description=(
            f"The served app is still the scaffold's stub: `{relative}` is byte-identical to "
            "what the scaffold wrote, so nothing this run drafted is wired into the service "
            "the acceptance suite runs against. This fails when the code runs."
        ),
        severity="major",
        reproduction_steps=f"Read `{relative}`: it is unchanged since the scaffold wrote it.",
        expected_behavior=f"`{relative}` serves the drafted product.",
        actual_behavior=f"`{relative}` is still the scaffold's stub (the harness compared it byte for byte)",
        affected_files=[relative],
        owner=owner,
    )


def _diagnosed_file_by_file(state: Any, saved_run: dict[str, Any], milestone: Any, test_round: int) -> Any:
    """A locked suite that gave no answer, run one file at a time by the harness; or None.

    In every delivery mode: it finds what a test round would, without a model
    looking for it. See `app.acceptance.per_file`. None when the suite did
    answer, or nothing could be run file by file - the testing specialist's
    round, as before.
    """
    from app.graph import acceptance_nodes

    root = state["repository"].root_path
    if (
        state.get("pending_inner_thread_id")
        or saved_run.get("ran")
        or not acceptance_nodes.suite.is_locked(root)
    ):
        return None
    try:
        from app.acceptance.per_file import defects_from, each_file
        from app.agents.specialists import SpecialistOutput
        from app.stacks import contract
        from app.stacks.scaffold import entrypoint_is_still_the_stub, sandbox_runner
        from app.tools.sandbox import timeout_for

        runs = each_file(root, contract.read(root) or {}, sandbox_runner(root))
        if not runs:
            return None
        owner = _the_unit_tests_fail(milestone, "").owner
        defects = defects_from(runs, owner, timeout_for("probe", root))
        unit_ok, unit_output = _run_unit_tests_procedurally(root)
        if unit_ok is False:
            defects.append(_the_unit_tests_fail(milestone, unit_output))
        # A suite that gave no answer, run file by file, failing most of it -
        # ask whether what it ran against is still the scaffold's stub, and
        # name the wiring gap itself instead of only its symptoms (K.3).
        if (stubbed := entrypoint_is_still_the_stub(root)) is not None:
            defects.append(_the_served_app_is_the_scaffold_s_stub(stubbed, owner))
    except Exception as error:  # noqa: BLE001 - the testing specialist's round, as before
        degraded("measure.acceptance_file_by_file", error)
        return None
    logger.info(
        "test_round_%d: the suite gave no answer; the harness ran its %d file(s) one at a time: %s",
        test_round, len(runs), ", ".join(f"{r['file']} {r['outcome']}" for r in runs),
    )
    return SpecialistOutput(
        changed_files=[], defects=defects,
        decisions=["The suite gave no answer as a whole; the harness ran each acceptance file alone (fast delivery)."],
    )


_NOT_A_PROBE_S = object()


def _settled_by_its_own_probe(root: Path, defect: Any) -> Any:
    """Whether a finding of the contract's own probes still holds, by asking that probe again; `_NOT_A_PROBE_S` else.

    Measured on one run: the emptied-field probe found `PATCH` taking an empty title and cited the criterion that
    refuses it; the re-measure at dispatch ran that criterion's acceptance file - which sends an empty title on create
    only - saw it pass, and closed the finding without a fixer. The probe raised it again each round, three attempts
    did not beat the best, and a product passing every locked test was escalated. None when the probe cannot run.
    """
    from app.acceptance import interface_contract

    description = str(getattr(defect, "description", "") or "")
    if description.startswith(interface_contract.EMPTIED_FIELD_ACCEPTED):
        found = interface_contract.emptied_field_errors(root)
        return None if found is None else not found
    if description.startswith(interface_contract.SERVER_FAILED):
        from app.acceptance import wrong_shape_body_probe

        errors, bad_body = interface_contract.server_errors(root), interface_contract.bad_body_errors(root)
        shaped = wrong_shape_body_probe.wrong_shape_errors(root)
        if errors is None and bad_body is None and shaped is None:
            return None
        return not (errors or []) and not (bad_body or []) and not (shaped or [])
    return _NOT_A_PROBE_S


def _the_defect_s_tests_pass(root: Path, defect: Any) -> bool | None:
    """Whether the acceptance files naming the defect's criteria now pass - or the unit tests, when it names none; None when neither can say."""
    try:
        from app.acceptance.junit import tags_in
        from app.acceptance.per_file import each_file
        from app.stacks import contract
        from app.stacks.scaffold import sandbox_runner

        from app.graph.acceptance_nodes import THE_PRODUCT_DOES_NOT_START

        settled = _settled_by_its_own_probe(root, defect)
        if settled is not _NOT_A_PROBE_S:
            return settled
        # What the suite's own run does first: the harness's files put back and a relative import given the
        # extension its runtime needs. Measured on a small-model run: a fixer wrote `./app.js` for `./app.ts`
        # (Node runs the `.ts` itself), the tests it was told "still fail" failed on that import alone, and it
        # spent the stage on the same edit; the harness corrected the import only at the next suite run.
        contract.enforce(root)
        # A server error at the contract's checks is settled by those checks, run again (`interface_contract.still_raised`).
        from app.acceptance import interface_contract

        raised = interface_contract.still_raised(root, str(getattr(defect, "description", "") or ""))
        if raised is not None:
            return not raised
        # A failing build by the build itself: no test answers for it.
        from app.stacks import production_build

        raised = production_build.still_raised(root, str(getattr(defect, "description", "") or ""))
        if raised is not None:
            return not raised
        if str(getattr(defect, "description", "") or "").startswith(THE_PRODUCT_DOES_NOT_START):
            # The suite starts the product its own way; unit tests that pass say
            # nothing about whether it does. Closing this on them left the same
            # defect to be raised again every round while no fixer ever saw it.
            return None
        # A failing unit run is answered by the unit tests alone, whatever ids their names carry: measured on two
        # runs, unit tests named "AC-1 CreateNoteTest" sent the re-measure to the acceptance files of those
        # criteria, which passed, and the defect was closed every round with four unit tests still failing.
        unit_run = str(getattr(defect, "description", "") or "").startswith(UNIT_TESTS_FAIL)
        tags = set() if unit_run else {
            t for t in tags_in(str(getattr(defect, "description", "") or "")) if t.startswith(("AC-", "CR-"))}
        if tags:
            runs = each_file(root, contract.read(root) or {}, sandbox_runner(root), naming=tags)
            if runs:
                return all(run["outcome"] == "finished" for run in runs)
        if not str(getattr(defect, "description", "") or "").startswith(UNIT_TESTS_FAIL):
            # Passing unit tests answer only for a defect that was raised from
            # failing ones. A finding from a test round or a review that names no
            # criterion was closed on them - one naming the very setting to fix
            # among them - and its fixer was never dispatched.
            return None
        ok, _ = _run_unit_tests_procedurally(str(root))
        return ok
    except Exception as failure:  # noqa: BLE001 - a check that cannot answer says nothing
        degraded("measure.defect_tests_pass", failure)
        return None


#: How a defect from a failing unit-test run begins.
UNIT_TESTS_FAIL = "The unit tests fail."


def _the_suite_already_guards_it(state: Any, measured: str, defect: Any) -> bool:
    """Whether the defect is a locked criterion whose own tests measured green after the fix.

    The locked acceptance suite is that criterion's regression test, and the
    harness has just measured it. Requiring the fixer to also name one left a
    fix open whose criterion passed (Initiative AO).
    """
    from app.acceptance.junit import tags_in

    description = str(getattr(defect, "description", "") or "")
    # A locked criterion, or the failing unit tests themselves: either way the
    # tests that were failing are the regression test, and they were just measured.
    # A server error at the contract's checks has those checks for its regression test: they run at every green
    # round and at release (`_with_the_contract_s_server_errors`).
    from app.acceptance.interface_contract import SERVER_FAILED
    from app.stacks.production_build import THE_PRODUCT_DOES_NOT_BUILD

    # A failing build has the build for its regression test: it runs at every round where the product changed.
    is_a_failing_test = description.startswith((UNIT_TESTS_FAIL, SERVER_FAILED)) or description.startswith(THE_PRODUCT_DOES_NOT_BUILD) or any(
        t.startswith(("AC-", "CR-")) for t in tags_in(description)
    )
    if not is_a_failing_test:
        return False
    return _the_defect_s_tests_in(state["repository"].root_path, measured, defect) is True


def _the_unit_tests_about(defect: Any, unit: dict[str, str]) -> dict[str, str]:
    """The unit tests that belong to this defect: all of them when it names no file, else those about its files.

    The whole suite answered for a defect about one file, so another
    defect's failing test left this one open (Initiative AO.1). A test is
    about a file when the file's name, without its extension, is in the
    test's key; a name shorter than three letters says too little to match
    on. {} when the defect names files and no test mentions them: the
    snapshot cannot say.
    """
    files = [str(f) for f in getattr(defect, "affected_files", None) or [] if str(f).strip()]
    if not files:
        return dict(unit)
    stems = {PurePosixPath(f.replace("\\", "/")).stem.lower() for f in files}
    stems = {stem for stem in stems if len(stem) >= 3}
    return {key: outcome for key, outcome in unit.items() if any(stem in key.lower() for stem in stems)}


def _the_defect_s_tests_in(root: str, label: str, defect: Any) -> bool | None:
    """Whether the defect's own tests pass in the snapshot `label` names; None when it cannot say.

    Its own tests are the acceptance tests naming its criteria - or, when it
    names none, the unit tests - as `_the_defect_s_tests_pass` picks them, read
    from what the fix's measurement already ran rather than run again. Only
    the latest snapshot, and only under `label`: one taken at another moment
    measured another change.
    """
    if not label:
        return None
    try:
        from app import ci
        from app.acceptance.junit import tags_in
        from app.analysis import dependency_drift
        from app.stacks import contract as the_contract

        # A defect about what the manifests declare is settled by declaring
        # it, measured by the same reconciliation that raised it - not by unit
        # tests that only mention the package. Measured on a gate run: a fixer
        # declared both packages, and the defect was left open on them.
        project = str((the_contract.read(root) or {}).get("project") or "")
        left = dependency_drift.still_undeclared(Path(root) / project, str(getattr(defect, "description", "") or ""))
        if left is not None:
            return not left
        # So is one about the scaffold's contract: by the check that raised it (`entry_exports.still_raised`).
        from app.stacks import entry_exports

        raised = entry_exports.still_raised(root, str(getattr(defect, "description", "") or ""))
        if raised is not None:
            return not raised
        # And one about a server error at the contract's checks: by those checks, run again.
        from app.acceptance import interface_contract

        raised = interface_contract.still_raised(root, str(getattr(defect, "description", "") or ""))
        if raised is not None:
            return not raised
        # And a failing build: by the build (it runs only if the product changed since it last did).
        from app.stacks import production_build

        raised = production_build.still_raised(root, str(getattr(defect, "description", "") or ""))
        if raised is not None:
            return not raised
        snapshot = ci.load(root, "latest")
        if snapshot is None or snapshot.label != label:
            return None
        from app.graph.acceptance_nodes import THE_PRODUCT_DOES_NOT_START

        if str(getattr(defect, "description", "") or "").startswith(THE_PRODUCT_DOES_NOT_START):
            # Whether the suite reached the product, and nothing else: the unit
            # tests say nothing about how the suite starts it.
            if not snapshot.acceptance_ran:
                return None
            return bool(snapshot.acceptance) and not snapshot.problem
        tags = {t for t in tags_in(str(getattr(defect, "description", "") or "")) if t.startswith(("AC-", "CR-"))}
        if tags:
            mine = [outcome for key, outcome in snapshot.acceptance.items() if tags & set(tags_in(key))]
            # A skipped test proves nothing either way: it is neither the
            # fixer's failure nor its success (Initiative AO.1).
            decisive = [outcome for outcome in mine if outcome != "skipped"]
            if decisive:
                return all(outcome == "passed" for outcome in decisive)
            if mine:
                return None
        if snapshot.unit_ran and snapshot.unit:
            about = _the_unit_tests_about(defect, snapshot.unit)
            return all(outcome != "failed" for outcome in about.values()) if about else None
        return None
    except Exception as swallowed:  # noqa: BLE001 - a measurement that cannot answer says nothing
        degraded("measure.defect_tests_in_snapshot", swallowed)
        return None


def _what_measures_it_gone(state: Any, defect: Any) -> str:
    """What harness measurement, taken now, shows the defect gone when its own tests cannot say; "" when none does.

    The language service no longer reporting it, the using file no longer importing a removed name, or what
    `_resolved_by_a_measurement` reads (a regressed test passing again, the product starting, a page check). Never
    raises.
    """
    try:
        root = state["repository"].root_path
        source = str(getattr(defect, "source", "") or "")
        if source == "language service":
            from app.graph.engineering import no_longer_underlined

            return "the language service" if no_longer_underlined(root, defect.description) else ""
        if source == "interface clash":
            return "the interface check" if interface_clashes.still_clashing(root, defect.description) is False else ""
        proof, _ = _resolved_by_a_measurement(state, defect)
        return proof
    except Exception as swallowed:  # noqa: BLE001 - a measurement that cannot answer shows nothing gone
        degraded("measure.settlement_fallback", swallowed)
        return ""


def _the_product_started_in(root: str, label: str) -> bool:
    """Whether the snapshot `label` names is the latest and measured the product starting. Never raises."""
    try:
        from app import ci

        snapshot = ci.load(root, "latest")
        return bool(label) and snapshot is not None and snapshot.label == label and not snapshot.problem
    except Exception:  # noqa: BLE001 - an unread snapshot shows nothing started
        return False


#: The key of `_settle_the_fix`'s update that says how the attempt ended, for the attempt record; popped by its caller.
SETTLED_AS = "__settled_as__"


def _settle_the_fix(
    state: Any, cycle: Any, defect_index: int, stage_name: str, fix_result: Any, *, measured: str = "",
    changed_nothing: bool | None = None,
) -> tuple[dict[str, Any], bool]:
    """What one fix that broke nothing settles: (the update, whether it blames a locked test).

    The update carries `remediation` - the defect fixed, or left open with
    the reason in the ledger - the fix's output, and under `SETTLED_AS` how the
    attempt ended. `measured` is the label of the snapshot
    `engineering.after_a_fix` just took of this fix: the defect's own tests in
    it decide, not the test the fixer names (`_the_defect_s_tests_in`).

    A defect is fixed only on a measurement: its own tests passing, or a
    harness check showing what it described gone. With none it is
    `UNVERIFIED` - still open, and the next test round decides. A fix whose
    stage changed no file (`changed_nothing`, from git since the fix began;
    None when that cannot be told) is never fixed. Measured on one 24-hour run:
    all nine "fixed" defects had no passing command, and one was closed with
    a change the fixer never made.
    """
    from app.observability import defect_ledger
    from app.sprint import NOTHING_WAS_CHANGED, UNVERIFIED

    defect = cycle.defects[defect_index]
    update: dict[str, Any] = {}
    settled_as = "left open: its tests still fail"
    #: Whether a measurement settled this defect either way: only such a fix may end the start-break streak.
    measured_either_way = True
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
    if mutation_guided.is_a_finding(defect):
        # A change no test noticed is settled by the harness's own check, as
        # a language-service finding is asked again: ahead of every rule
        # below, since its "own tests" are the whole unit run, and nothing the
        # product does is wrong (plan QM.2).
        update["remediation"] = _a_mutation_finding_settled(state, cycle, defect_index, stage_name, fix_result)
    elif fix_result.blockers and not fix_result.changed_files:
        # Blocked and nothing changed: not a fix. Recorded as fixed, it was
        # closed with no change behind it, and a stage that could not
        # reply at all now answers this way (`_blocked_for_want_of_room`).
        # The next round measures it again.
        update["remediation"] = cycle
        # A package it says cannot be loaded, loaded by the harness: the next fixer is given the fact, not the claim.
        loads = _what_a_claimed_unloadable_package_does(state["repository"].root_path, list(fix_result.blockers))
        if loads:
            defects = list(cycle.defects)
            defects[defect_index] = defect.model_copy(
                update={"actual_behavior": f"{defect.actual_behavior or ''}\n{loads}".strip()})
            update["remediation"] = cycle.model_copy(update={"defects": defects})
        defect_ledger.note(
            "left open", stage_name, defect=defect, round_=state.get("test_round", 0), index=defect_index,
            sprint=state.get("current_sprint_index", 0),
            detail="the fix stage changed nothing and reported: " + "; ".join(map(str, fix_result.blockers))[:300]
            + (f" - {loads}" if loads else ""),
        )
        settled_as, measured_either_way = NOTHING_WAS_CHANGED, False
    elif changed_nothing is True:
        # No file of the product changed since the fix began, whatever the fixer says it changed: not a fix. Measured
        # on one run: a defect was closed with "changed routers/users.py" from a fixer that made no write call.
        update["remediation"] = cycle
        defect_ledger.note(
            "left open", stage_name, defect=defect, round_=state.get("test_round", 0), index=defect_index,
            sprint=state.get("current_sprint_index", 0),
            detail="nothing was changed: no file of the product differs from before the fix"
            + (f" (the fixer said it changed {', '.join(map(str, fix_result.changed_files))[:200]})"
               if fix_result.changed_files else ""),
        )
        settled_as, measured_either_way = NOTHING_WAS_CHANGED, False
    elif (measured_now := _the_defect_s_tests_in(state["repository"].root_path, measured, defect)) is False:
        # Its own tests still fail, measured after the fix. Closed, the next
        # round found it again and charged the attempt a round late. Ahead of
        # the regression-test rule: measured live, three fixes whose unit tests
        # still failed were each recorded as "named no regression test", the
        # lesser reason.
        update["remediation"] = cycle
        # Unless they fail further on than before it (LF.1272): measured on a medium run, fixes that moved their tests
        # from 500 to 404, a later step reached, were counted as failed fixes like ones that changed nothing.
        from app.graph import judged_fixes

        forward = judged_fixes.moved_forward(state["repository"].root_path, stage_name, defect)
        if forward:
            update["remediation"] = judged_fixes.with_the_new_evidence(cycle, defect_index, forward)
            settled_as = f"{judged_fixes.MOVED_FORWARD}: {forward}"
        defect_ledger.note(
            "left open", stage_name, defect=defect, round_=state.get("test_round", 0), index=defect_index,
            sprint=state.get("current_sprint_index", 0),
            detail=settled_as if forward else "its own tests still fail, measured after the fix",
        )
    elif str(getattr(defect, "source", "") or "") == "language service" and _still_underlined(
        state["repository"].root_path, defect
    ):
        # A finding the language service still reports is not fixed, whatever
        # the fix changed: asked again here, as the next round would ask it.
        update["remediation"] = cycle
        defect_ledger.note(
            "left open", stage_name, defect=defect, round_=state.get("test_round", 0), index=defect_index,
            sprint=state.get("current_sprint_index", 0),
            detail="the language service still reports it, asked again after the fix",
        )
        settled_as = "left open: the language service still reports it"
    elif str(getattr(defect, "source", "") or "") == "interface clash" and (
        still := interface_clashes.still_clashing(state["repository"].root_path, defect.description)
    ) is not None and still:
        # Asked again, as the language service is: measured live, a clash was
        # closed on any named test and held open on none, never re-checked.
        update["remediation"] = cycle
        defect_ledger.note(
            "left open", stage_name, defect=defect, round_=state.get("test_round", 0), index=defect_index,
            sprint=state.get("current_sprint_index", 0),
            detail="the using file still imports the removed name, asked again after the fix",
        )
        settled_as = "left open: the using file still imports the removed name"
    elif defect.regression_test_required and not regression_test and measured_now is not True \
            and not _the_suite_already_guards_it(state, measured, defect) \
            and not (str(getattr(defect, "source", "") or "") == "interface clash"
                     and interface_clashes.still_clashing(state["repository"].root_path, defect.description) is False):
        # No named regression test and no measurement of its own tests: the defect stays open on purpose. The next
        # test round will count this as another failed attempt, so the bounded loop still terminates. A defect whose
        # own tests measured passing is closed by that measurement (below): measured in the deep review of
        # 2026-11-18, 17 defects whose tests passed were left open here after 17-19 model calls each.
        update["remediation"] = cycle
        defect_ledger.note(
            "left open", stage_name, defect=defect, round_=state.get("test_round", 0), index=defect_index,
            sprint=state.get("current_sprint_index", 0),
            detail="the fix named no regression test",
        )
        settled_as, measured_either_way = "left open: the fix named no regression test", measured_now is not None
    elif measured_now is None and not (gone := _what_measures_it_gone(state, defect)):
        # Nothing measures what it described, before or after the fix: the fixer's word is all there is. Closed on it,
        # the ledger, the summary and the re-plan read a fix nobody saw; open, the next test round decides
        # (`closed_by_a_round_that_found_nothing`) or a fixer is asked again.
        logger.info("The fix for '%s' could not be measured at settlement: left open, unverified",
                    defect.description[:80])
        update["remediation"] = cycle
        if regression_test:
            # The test it named, kept for the round that closes it (`closed_by_a_round_that_found_nothing`).
            defects = list(cycle.defects)
            defects[defect_index] = defect.model_copy(update={"regression_test": regression_test})
            update["remediation"] = cycle.model_copy(update={"defects": defects})
        defect_ledger.note(
            "unverified", stage_name, defect=defect, round_=state.get("test_round", 0), index=defect_index,
            sprint=state.get("current_sprint_index", 0),
            detail="nothing the harness measures shows it gone; left open for the next test round"
            + (f"; the fixer said: changed {', '.join(map(str, fix_result.changed_files))[:200]}"
               if fix_result.changed_files else ""),
        )
        settled_as, measured_either_way = UNVERIFIED, False
    else:
        if measured_now is None:
            logger.info("The fix for '%s' was measured by %s at settlement", defect.description[:80], gone)
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
        # Closed by its measurement, the regression test the harness would like is a note, not a reason to keep it
        # open (A7): its own tests, just measured, are what guards it.
        unnamed = defect.regression_test_required and not regression_test
        guarded_by = (f"{gone}, measured after the fix" if measured_now is None
                      else "the locked acceptance suite, measured after the fix" if _the_suite_already_guards_it(
                          state, measured, defect) else "its own tests, measured passing after the fix")
        if unnamed and measured_now is True:
            resolution = (resolution + "; " if resolution else "") + "the fix named no regression test of its own"
        update["remediation"] = mark_defect_fixed(
            cycle, defect_index,
            # A criterion the suite measured green after the fix has the locked
            # suite for its regression test (`_the_suite_already_guards_it`).
            regression_test=regression_test or (guarded_by if defect.regression_test_required else regression_test),
            verified_by=verified_by, resolution=resolution,
        )
        defect_ledger.note(
            "fixed", stage_name, defect=defect, round_=state.get("test_round", 0), index=defect_index,
            sprint=state.get("current_sprint_index", 0),
            detail=(resolution or "") + (f" (verified by {verified_by})" if verified_by else " (no passing command recorded)"),
        )
        settled_as = "fixed"

    if mutation_guided.is_a_finding(defect):
        settled_as = "left open: its tests still fail" if update["remediation"] is cycle else "fixed"
    # A kept fix that changed the product, measured with the product starting, ends the start-break streak; one that
    # changed nothing, or that nothing measured, does not (`start_breaks`). Measured: a "fixed" on the fixer's word
    # cleared it, the next nine fixers were not told, and the tenth repeated the change that stops the start.
    if measured_either_way and changed_nothing is not True and _the_product_started_in(
            state["repository"].root_path, measured):
        from app.agents import start_breaks

        start_breaks.clear(state["repository"].root_path)
    update[SETTLED_AS] = settled_as

    still_open = settled_as != "fixed"
    # Unverified is neither fixed nor failed: the next test round decides, and a defect it closes had no failed fix.
    # Nor is a fix that moved its tests forward (LF.1272): it is kept, and what is left is the next fault.
    from app.graph.judged_fixes import MOVED_FORWARD

    if still_open and settled_as != UNVERIFIED and not settled_as.startswith(MOVED_FORWARD):
        # One more failed try: past `escalate_after()` its next fix runs on
        # the judgement model (`GraphContext.the_build_model`).
        update["remediation"] = _one_more_failed_fix(update["remediation"], defect_index)
    blames = still_open and not mutation_guided.is_a_finding(defect) and _blames_a_locked_test(
        state, [*fix_result.blockers, *fix_result.decisions], changed_nothing=not fix_result.changed_files
    )
    update["specialist_outputs"] = outputs
    return update, blames


def _a_mutation_finding_settled(state: Any, cycle: Any, defect_index: int, stage_name: str, fix_result: Any) -> Any:
    """`cycle` after one fix of a mutation finding: fixed, closed as equivalent or as a gap; `cycle` itself if left open.

    Fixed only when the unit tests fail with the change and pass without it,
    measured here (`mutation_guided.settled`) - not on a named test. Closed,
    never escalated, when the fixer says the change behaves the same and why,
    or once its tries are spent: a finding is about the tests' strength, not
    something the product does wrong, so setting it aside accepts no known
    defect. `accept_risk` records it with the reason, the way a person would.
    """
    from app.observability import defect_ledger
    from app.sprint import accept_risk

    defect = cycle.defects[defect_index]
    where = {"round_": state.get("test_round", 0), "index": defect_index, "sprint": state.get("current_sprint_index", 0)}
    root = state["repository"].root_path
    # Tests that fail on the product as it is, or notice nothing, are put back first (`MUTATION_TEST_RETENTION`).
    from app.acceptance import mutation_equivalents, mutation_retention
    from app.graph import mutation_gaps_bundled
    from app.observability.transcript import _run_id_from_config

    # The findings in its file its fixer was handed too (`MUTATION_GAPS_BUNDLED`): a test that notices one of their
    # changes is kept, and each is checked here - closed if settled, else left for its own fixer.
    bundled = mutation_gaps_bundled.Bundled(
        root, _bundle_co_defects(cycle, defect_index) if fix_result.changed_files else [])
    checked, put_back = mutation_retention.judged(
        root, _run_id_from_config(), stage_name, lambda: mutation_guided.settled(root, defect),
        keeps=bundled.any_settled if bundled.open else None)
    if put_back:
        defect_ledger.note("retention", stage_name, defect=defect, detail=put_back, **where)

    def with_the_bundled(after: Any) -> Any:
        return bundled.closed(after, stage_name=stage_name, round_=where["round_"], sprint=where["sprint"],
                              put_back=put_back)

    if checked is True:
        detail = "the unit tests fail with the change and pass without it, measured by the harness"
        defect_ledger.note("fixed", stage_name, defect=defect, detail=detail, **where)
        return with_the_bundled(mark_defect_fixed(
            cycle, defect_index,
            regression_test="the unit tests, which fail with the change and pass without it",
            verified_by="the harness's mutation check", resolution=detail[0].upper() + detail[1:] + ".",
        ))
    why = mutation_guided.equivalent_because(fix_result)
    if why and not fix_result.changed_files:
        defect_ledger.note("closed", stage_name, defect=defect, detail="judged equivalent: " + why, **where)
        mutation_equivalents.remember(root, defect, why)
        return accept_risk(cycle, defect_index, reason=mutation_guided.EQUIVALENT + why)
    measured = (
        "the unit tests still pass with the change" if checked is False
        else "the change could not be made again where it was, or the unit tests did not run"
    ) + (f" ({put_back})" if put_back else "")
    tries = failed_fix_tries(cycle, defect_index) + 1
    if tries >= mutation_guided.MOST_TRIES:
        defect_ledger.note("closed", stage_name, defect=defect, detail=f"a completion gap after {tries} tries: {measured}", **where)
        return with_the_bundled(
            accept_risk(cycle, defect_index, reason=f"{mutation_guided.A_GAP}{measured} after {tries} fix stage(s)."))
    defect_ledger.note("left open", stage_name, defect=defect, detail=measured + ", asked again after the fix", **where)
    return with_the_bundled(cycle)


def _put_back_a_deliberate_change(state: Any) -> None:
    """With `MUTATION_GUIDED_TESTS` on, undo a mutation check a dead worker left in the product. Never raises.

    A deploy restarts the worker mid-stage, and the stage is entered again on
    the tree as it was left: a fix measured, or a fixer briefed, against a
    deliberate break.
    """
    if not mutation_guided.enabled():
        return
    try:
        from app.acceptance.mutation import restore_an_interrupted_probe

        restore_an_interrupted_probe(state["repository"].root_path)
    except Exception as error:  # noqa: BLE001 - the probe's own entry tries again
        degraded("probe.deliberate_change_put_back", error)


def _only_mutation_findings_open(cycle: Any, measured: list[Any]) -> bool:
    """Whether a round found nothing and every defect still open is a mutation finding.

    Such a round found nothing wrong with the product, only tests too weak to
    notice a change, and is not charged against the product's attempts (plan
    QM.2), as a round of only test defects is not.
    """
    still = [d for d in getattr(cycle, "defects", None) or [] if getattr(d, "status", "") == "open"]
    return not measured and bool(still) and all(mutation_guided.is_a_finding(d) for d in still)


def _mutation_findings_set_aside(state: Any, cycle: Any, test_round: int) -> tuple[Any, list[str]]:
    """`cycle` with each open mutation finding the sprint has no round for closed as a gap; and the run's gaps from them.

    The sprint's attempts bound the findings as they bound every defect, but a
    finding never spends the last of them: one still open when the sprint has
    no attempt or round to spare is a completion gap, not an escalation (plan
    QM.2). The gaps are every finding closed unsettled, this sprint's added to
    the run's. A no-op for a cycle with no finding.
    """
    from app.observability import defect_ledger
    from app.sprint import ROUNDS_PER_ATTEMPT_CEILING, accept_risk

    known = list(state.get("mutation_gaps") or [])
    defects = list(getattr(cycle, "defects", None) or [])
    if not any(mutation_guided.is_a_finding(d) for d in defects):
        return cycle, known
    no_room = (
        len(cycle.test_runs) + 2 > cycle.max_attempts * ROUNDS_PER_ATTEMPT_CEILING
        or cycle.attempt + 1 >= cycle.max_attempts
    )
    for index, defect in enumerate(defects):
        if defect.status != "open" or not mutation_guided.is_a_finding(defect):
            continue
        tries = failed_fix_tries(cycle, index)
        if not no_room and tries < mutation_guided.MOST_TRIES:
            continue
        why = "the sprint had no fix round to spare for it" if no_room else f"{tries} fix stage(s) did not settle it"
        defect_ledger.note("closed", f"test_round_{test_round}", defect=defect, round_=test_round, index=index,
                           sprint=state.get("current_sprint_index", 0), detail="a completion gap: " + why)
        cycle = accept_risk(cycle, index, reason=f"{mutation_guided.A_GAP}{why}.")
    gaps = [gap for d in cycle.defects if (gap := mutation_guided.the_gap(d))]
    return cycle, list(dict.fromkeys([*known, *gaps]))


def _only_unit_tests_open_beside_a_green_suite(state: Any, cycle: Any) -> bool:
    """Whether the suite ran with every due criterion passing and every open defect is a failing unit test. Never raises."""
    try:
        from app.acceptance import suite
        from app.graph import acceptance_nodes, settle_when_green

        still_open = [d for d in getattr(cycle, "defects", None) or () if getattr(d, "status", "") == "open"]
        if not still_open:
            return False
        failing, command = acceptance_nodes._failing_due(state)
        saved = suite.last_result(state["repository"].root_path) or {}
        if failing or not saved.get("ran") or int(saved.get("failed") or 0) > 0:
            return False
        return all(settle_when_green._a_unit_test_failure(d, command) for d in still_open)
    except Exception:  # noqa: BLE001 - the round goes on as before
        return False


def _the_mutation_probe(state: Any, cycle: Any, test_round: int) -> dict[str, Any]:
    """The update for a sprint whose due criteria all pass: its findings to fix, or only that it was probed; {} when off.

    Once per sprint attempt - its index and re-plan count - and never again
    on the last sprint's release path. The sources are the product's own files
    this sprint changed (`_the_files_this_milestone_changed`). See
    `app.acceptance.mutation_guided`.
    """
    if not mutation_guided.enabled():
        return {}
    from app.observability import defect_ledger

    index = int(state.get("current_sprint_index") or 0)
    key = f"{index}:{int(state.get('sprint_replan_count') or 0)}"
    done = list(state.get("mutation_probed") or [])
    if key in done or (int(state.get("release_attempts") or 0) and any(k.split(":")[0] == str(index) for k in done)):
        return {}
    root = state["repository"].root_path
    changed = _the_files_this_milestone_changed(state, state.get("specialist_outputs") or {})
    found = [mutation_guided.defect(site) for site in mutation_guided.probe(root, changed)]
    update: dict[str, Any] = {"mutation_probed": [*done, key]}
    if not found:
        return update
    for position, item in enumerate(found, start=len(cycle.defects)):
        defect_ledger.note("raised", f"test_round_{test_round}", defect=item, round_=test_round, index=position,
                           sprint=index, detail="a deliberate change no test noticed")
    logger.warning("Sprint %d: %d deliberate change(s) no test noticed; the testing role is asked for unit tests",
                   index + 1, len(found))
    return {
        **update,
        "remediation": cycle.model_copy(update={"defects": [*cycle.defects, *found]}),
        "stage": "defect_remediation",
        "defect_cursor": 0,
    }


#: How each runtime is asked whether a package loads: the command, with `{name}` for the package. Node imports it as
#: the product does (an ES module, or a CommonJS one through its default).
_LOAD_A_PACKAGE = {
    "node": ["node", "-e", "import('{name}').then(m => console.log('LOADS', Object.keys(m).slice(0, 8).join(', ')))"
                           ".catch(e => { console.log('FAILS', String(e && e.message || e).slice(0, 300)); process.exit(1); })"],
}
#: Words of a claim that something cannot be loaded.
_A_LOADING_CLAIM = re.compile(r"\b(?:import|imports|imported|require|load|loads|resolve|module|ESM|CommonJS)\b", re.I)


def _what_a_claimed_unloadable_package_does(repo_root: str, blockers: list[str]) -> str:
    """What loading a declared package the blockers say cannot be loaded shows, or "". Never raises.

    Measured on one run: two fixers reported that `sqlite3` could not be imported as an ES module, changed nothing,
    and one ran to the call cap; `await import('sqlite3')` loaded it in the project. A runtime the table does not
    name, or a claim naming no declared package, says nothing.
    """
    try:
        import json as _json

        from app.stacks import contract
        from app.stacks.scaffold import sandbox_runner

        text = " ".join(map(str, blockers or []))
        found = contract.the_pack(repo_root)
        command = _LOAD_A_PACKAGE.get(str(getattr(found[0], "code_runs_in", "") or "")) if found else None
        if not command or not _A_LOADING_CLAIM.search(text):
            return ""
        project = str(found[1].get("project") or "")
        manifest = _json.loads((Path(repo_root) / project / "package.json").read_text(encoding="utf-8"))
        declared = [*(manifest.get("dependencies") or {}), *(manifest.get("devDependencies") or {})]
        named = [name for name in declared if re.search(rf"(?<![\w@/-]){re.escape(name)}(?![\w/-])", text, re.I)]
        if not named:
            return ""
        name = named[0]
        outcome = sandbox_runner(repo_root)([part.replace("{name}", name) for part in command], "probe", project) or {}
        said = str(outcome.get("stdout") or "") + str(outcome.get("stderr") or "")
        if "LOADS" in said:
            exports = said.split("LOADS", 1)[1].strip().splitlines()[0][:200] if said.split("LOADS", 1)[1].strip() else ""
            return (f"The harness loaded it: `{name}` loads in this project (its exports: {exports or 'none listed'}). "
                    "Loading it is not what is wrong; the cause is elsewhere.")
        if "FAILS" in said:
            return f"The harness tried loading `{name}` in this project and it fails: {said.split('FAILS', 1)[1].strip()[:300]}"
        return ""
    except Exception:  # noqa: BLE001 - the claim stands as it was made
        return ""


def _the_unit_run_kept(repo_root: str, command: list[Any]) -> tuple[bool, str] | None:
    """The last unit run's (passed, output) when the product and the command are as they were then; else None.

    The record (`ci.UNIT_RUN_FILE`, MEASURE_ONCE) is one, shared with every CI snapshot.
    """
    from app import ci

    saved = ci.the_unit_run_kept(repo_root, command)
    if saved is None:
        return None
    logger.info("The product is as the unit tests last measured it; that run stands")
    return bool(saved.get("passed")), str(saved.get("output") or "")


def _keep_the_unit_run(repo_root: str, command: list[Any], passed: bool, output: str) -> None:
    """Keep this unit run with the product's fingerprint, for `_the_unit_run_kept` and CI's snapshots. Never raises.

    Each test's outcome in the pack's report goes with it, so the next snapshot of the same product reads it
    instead of running the unit tests again.
    """
    from app import ci

    try:
        outcomes = ci.unit_outcomes_in_the_pack_s_report(repo_root)
    except Exception:  # noqa: BLE001 - kept without outcomes, a snapshot runs them again
        outcomes = None
    unit, found = outcomes if outcomes is not None else (None, False)
    ci.keep_the_unit_run(repo_root, command, passed, output, unit, found)


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

        reports = _the_unit_reports(repo_root, found, cmd)
        from app.acceptance import junit

        # An unchanged product's unit run stands (MEASURE_ONCE): measured on one run, one test round ran the same
        # `npm test` four times with no fix between, five minutes each on a unit test that never settled.
        kept = _the_unit_run_kept(repo_root, cmd)
        if kept is not None:
            return _not_a_pass_on_no_test(repo_root, reports, *kept)
        for report in reports:
            junit.clear(report)
        runner = sandbox_runner(repo_root)
        from app.acceptance import unmeasured

        def measure() -> dict[str, Any]:
            return runner(cmd, "test", project) or {}

        def not_taken(answered: dict[str, Any]) -> str:
            return unmeasured.why(answered, reached_tests=any(junit.read(report).tests for report in reports))

        outcome = unmeasured.once_more(measure, not_taken)
        if not_taken(outcome):
            # Not measured is unknown, not failed: no "the unit tests fail" defect from a refusal (A1). Not kept.
            unmeasured.record(repo_root, "unit tests", not_taken(outcome))
            return None, f"The harness could not measure the unit tests: {not_taken(outcome)}"
        # The sandbox answers as its tool does, the code as text: "0" is not 0.
        # Measured on one run: every harness test round said the unit tests
        # failed while all 109 passed, and the sprint was planned again three times.
        from app.stacks.scaffold import _exit_code

        rc = _exit_code(outcome)
        output = str(outcome.get("stdout") or "") + str(outcome.get("stderr") or "")
        # What the sandbox said instead, when the command ended without a code of its own: measured on one Go run, a
        # unit run held to its time limit came back as "Command timed out after 300 seconds" and nothing else, and
        # the defect said the runner's output ended "(no output)" - no fixer was told a test never returned.
        if outcome.get("error"):
            output = (output.rstrip() + "\n" + str(outcome["error"])).strip()
        if rc != 0:
            output = (output.rstrip() + "\n" + _what_the_unit_reports_say(reports)).strip()
        passed, output = _not_a_pass_on_no_test(repo_root, reports, rc == 0, output)
        _keep_the_unit_run(repo_root, cmd, passed, output)
        return passed, output
    except Exception as error:  # noqa: BLE001 - procedural test failure falls back to agent triage
        return False, f"The harness could not run the unit tests: {error}"


def _not_a_pass_on_no_test(repo_root: str, reports: list[Path], passed: bool, output: str) -> tuple[bool, str]:
    """A unit run that exited as a pass and collected no test, once unit tests were ordered, as a failing run whose
    output ends saying where the runner looks and where the test files are (LF.1263).

    Measured on a full-stack run: every test round's unit run printed "No test files found" and "no tests ran", the
    gate passed it each time, and the service's unit tests - written where the runner does not look - never ran.
    Before any unit test is written or planned, a run of none passes as it did.
    """
    if not passed:
        return passed, output
    from app.stacks.unit_test_home import none_collected

    why = none_collected(repo_root, reports, output)
    if not why:
        return passed, output
    logger.warning("The unit run collected no test while unit tests were ordered: %s", why[:300])
    return False, (str(output or "").rstrip() + "\n" + why).strip()


def _the_unit_reports(repo_root: str, record: dict[str, Any], command: list[Any]) -> list[Path]:
    """Where the unit run writes its report: the pack's, and any XML file the command names.

    A runner told to write JUnit to a file prints nothing. Measured on one
    run: three rounds' defects read "The unit tests fail. The runner's output
    ends: (no output)" - each fixer had to find out which tests failed, fixed
    something else, and the sprint was planned again.
    """
    from app.stacks import contract

    folder = Path(repo_root) / str(record.get("project") or "")
    found: list[Path] = []
    pack = contract.the_pack(repo_root)
    if pack is not None and getattr(pack[0], "unit_report", ""):
        found.append(folder / pack[0].unit_report)
    for word in (str(part) for part in command):
        named = word.split("=", 1)[-1]
        if named.lower().endswith(".xml") and "*" not in named:
            found.append(folder / named)
    return list(dict.fromkeys(found))


def _what_the_unit_reports_say(reports: list[Path]) -> str:
    """The failing tests in the unit reports, each with its message; "" when none are found."""
    from app import ci
    from app.acceptance import junit

    return ci.what_the_failing_unit_tests_say([test for report in reports for test in junit.read(report).tests])


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



def _it_ran_past_its_output_limit(stage_name: str, attempts: int, chars: int) -> str:
    """The message for a stage whose replies had text and ran to the output limit without an accepted answer.

    Told as the reply that wrote nothing - "spent its entire output budget
    before writing anything ... no text" - while each of the sprint planner's
    six replies held 78,000 to 129,000 characters: a plan, then the same plan or
    a sentence written over and over until the limit. The fix that message names
    (more output tokens) is the wrong one for a reply that never stops.
    """
    tried = (
        f" This was attempt {attempts} at the stage; the earlier ones ended "
        "without a structured response too."
        if attempts > 1
        else ""
    )
    return (
        f"Agent '{stage_name}' wrote replies that ran to the output limit without an answer the "
        f"stage's schema accepts: the last was {chars:,} characters, cut off by the limit "
        f"(`finish_reason: length`).{tried}\n\n"
        "A reply that runs to the limit with text in it is a model that does not stop - it writes "
        "its answer and goes on, repeating it or a sentence - or an answer far longer than it "
        "should be. A higher output limit makes each such reply cost more, not less. Look at the "
        "last reply in the run's transcript: if it repeats itself, the model server's repetition "
        "penalty and sampling settings are the place to look; if an answer near its start misses "
        "the schema, the stage's validation errors say which field."
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
    if getattr(message, "invalid_tool_calls", None):
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
    if ran_out and not text.strip():
        return _it_spent_its_whole_output_budget(stage_name, attempts)
    if ran_out:
        return _it_ran_past_its_output_limit(stage_name, attempts, len(text))
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

    Item 7 of Part III of the hardening plan (`docs/improvement-plan.md §E1`). Cancelling a run did two
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


def remember_the_stop(run_id: str | None) -> None:
    """Remember, in this process, that `run_id` was stopped (paused or cancelled) - see `stopped_here`."""
    if run_id:
        _CANCELLED_RUNS.add(str(run_id))


def stopped_here(run_id: str | None) -> bool:
    """Whether this process stopped `run_id` and has not resumed it since. No database read.

    A stage's agent loop runs in an executor thread that the stopped task does not end. Measured on one run: after a
    pause, the paused stage kept calling the model for five minutes, beside the same run rewound in the other worker
    process, and could have written into the workspace the rewind had just restored. Each model call asks this.
    """
    return bool(run_id) and str(run_id) in _CANCELLED_RUNS


def forget_the_stop(run_id: str | None) -> None:
    """Forget, in this process, that `run_id` was asked to stop - it is being resumed.

    `_stop_if_cancelled` remembers a stop per process. A paused run resumed by
    a task in the same worker process would otherwise stop again at its first
    stage boundary, whatever the database now says.
    """
    _CANCELLED_RUNS.discard(str(run_id or ""))


def _the_run_approves_its_own_writes(run_id: str | None) -> bool:
    """Whether this run answers its own write approvals (`auto_approve`); False when unknown."""
    if not run_id:
        return False
    try:
        from app.server.run_store import RunStore

        record = RunStore.shared().load(run_id)
    except Exception:  # noqa: BLE001 - unknown is not approved
        return False
    return bool(getattr(record, "auto_approve", False))


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
    except Exception as error:  # noqa: BLE001 - a cancel check must never fail a run
        degraded("cancel_check", error)
        return
    if requested:
        _CANCELLED_RUNS.add(run_id)
        logger.info("Run %s was cancelled; stopping at a stage boundary", run_id)
        raise RunCancelled(f"Run {run_id} was cancelled.")


def _name_the_stage_on_the_run(run_id: str | None, stage_name: str) -> None:
    """Show the stage just entered on the run's row, so its page names where the run is now.

    Never fails a stage: the row is a display, and the next pause writes it anyway.
    """
    if not run_id:
        return
    try:
        from datetime import datetime, timezone

        from app.server.run_store import RunStore
        from app.server.runner import _stage_narration

        meaning, _status = _stage_narration(stage_name, auto_approve=False)
        RunStore.shared().record_stage(run_id, stage_name, meaning, datetime.now(timezone.utc).isoformat())
    except Exception:  # noqa: BLE001 - a display must never stop a run
        logger.debug("Could not name the stage on the run's row", exc_info=True)




class StageGaveNoAnswer(ValueError):
    """A stage spent every way to answer: no structured response, no retry left, no blocker it may return.

    A `ValueError` as before, so every handler of that is unchanged; its own
    class so a stage with an answer of its own to fall back on (the sprint
    plan: `scrum_master.a_plan_the_harness_writes`) catches this and nothing else.
    """

#: (run, stage) pairs whose answer was asked for in parts: once per stage, so a
#: stage the parts could not answer goes on to its restarts as before.
_ASKED_IN_PARTS: set[tuple[str, str]] = set()



#: Tools whose calls change something, and the argument that names what.
_WHAT_A_CALL_ACTED_ON = (
    ("write_artifact", "relative_path"), ("edit_artifact", "relative_path"), ("replace_lines", "relative_path"),
    ("delete_artifact", "relative_path"), ("move_artifact", "relative_path"),
    ("run_terminal_command", "command"), ("run_validation", "command"),
)


def _what_the_stage_did(result: dict[str, Any], most: int = 40) -> str:
    """The stage's writes and commands with their outcomes, and its last words, from its conversation; "" if none.

    An answer asked for in parts is asked without the conversation, and for a
    stage that did work its answer is a report of that work. Measured live: the
    acceptance writer's parts, given only the request, reported files it never
    wrote, a setup it never read and checks of files that did not exist.
    """
    acting = dict(_WHAT_A_CALL_ACTED_ON)
    asked: dict[str, tuple[str, str]] = {}
    lines: list[str] = []
    last_words = ""
    for message in result.get("messages") or []:
        kind = getattr(message, "type", None)
        if kind == "ai":
            text = str(getattr(message, "content", "") or "").strip()
            if text:
                last_words = text
            for call in getattr(message, "tool_calls", None) or []:
                name = str(call.get("name") or "")
                if name in acting:
                    target = (call.get("args") or {}).get(acting[name])
                    shown = " ".join(map(str, target)) if isinstance(target, list) else str(target or "")
                    asked[str(call.get("id") or "")] = (name, shown[:160])
        elif kind == "tool":
            entry = asked.pop(str(getattr(message, "tool_call_id", "") or ""), None)
            if entry:
                outcome = " ".join(str(getattr(message, "content", "") or "").split())[:180]
                lines.append(f"- {entry[0]} {entry[1]} -> {outcome}")
    record = "\n".join(lines[-most:])
    if last_words:
        record += ("\n" if record else "") + "Its last words: " + " ".join(last_words.split())[:1200]
    return record

def _the_answer_in_parts(
    run_id: str | None, stage_name: str, agent: Any, initial_request: Any, result: dict[str, Any],
) -> Any | None:
    """The stage's answer asked for in parts when its last reply ran out of room; else None.

    Whole replies that run out - reasoning to the limit, or an answer that does
    not stop - were met with the same request again, thinking off and then
    on fresh conversations. A smaller question is the lever that works on any
    model: see `app.agents.answered_in_parts`. Once per stage of a run.
    """
    schema = getattr(agent, "workflow_response_format", None)
    model = getattr(agent, "workflow_model", None)
    last = next((m for m in reversed(result.get("messages") or []) if getattr(m, "type", None) == "ai"), None)
    key = (str(run_id or ""), stage_name)
    if schema is None or not isinstance(model, BaseChatModel) or key in _ASKED_IN_PARTS:
        return None
    if last is None or not _the_reply_was_cut_off_before_it_began(last):
        return None
    _ASKED_IN_PARTS.add(key)
    messages = (initial_request or {}).get("messages") or [] if isinstance(initial_request, dict) else []
    request = "\n\n".join(
        str(m.get("content") if isinstance(m, dict) else getattr(m, "content", "")) for m in messages
    ).strip()
    if not request:
        return None
    did = _what_the_stage_did(result)
    if did:
        request += (
            "\n\n--- What this stage did, from its own conversation ---\n" + did
            + "\n\nThe answer reports this work: name only the files, commands and results this record "
            "shows, as it shows them."
        )
    try:
        from app.agents.answered_in_parts import answered_in_parts

        return answered_in_parts(schema, request, model, stage_name)
    except Exception:  # noqa: BLE001 - the stage goes on to its restarts as before
        logger.warning("Stage %s could not be answered in parts", stage_name, exc_info=True)
        return None


def _the_harness_s_sprint_plan(state: Any, measures: list[str], root_path: str, why: str) -> dict[str, Any]:
    """The update that goes on with one sprint over every criterion, said as the harness's, when the planner gave none."""
    from app.acceptance import suite as acceptance_suite
    from app.agents.scrum_master import THE_HARNESS_S_PLAN, a_plan_the_harness_writes

    specification = state.get("technical_specification")
    plan = a_plan_the_harness_writes(
        acceptance_suite.criteria(root_path), measures,
        list(getattr(specification, "file_plan", None) or []),
        str(getattr(state.get("product_intake"), "product_name", "") or ""),
    )
    logger.warning("The sprint planner gave no answer; going on with %s", THE_HARNESS_S_PLAN)
    first_line = why.strip().splitlines()[0] if why.strip() else "no answer"
    update: dict[str, Any] = {
        "sprint_plan": plan,
        "stage": "technical_lead",
        "pending_approval": None,
        "pending_inner_thread_id": None,
        "pending_decision": None,
        # Through the path every set-aside issue takes to the release's gaps.
        "known_issues": [*(state.get("known_issues") or []),
                         f"The sprint plan is {THE_HARNESS_S_PLAN}: {first_line[:300]}"],
    }
    try:
        from app.decisions import record_decision

        record_decision(
            state, update, point="sprint_plan", question="How is the work split into sprints?",
            options=["the planner's plan", THE_HARNESS_S_PLAN], decision=THE_HARNESS_S_PLAN,
            rationale=f"The sprint planner spent every way to answer. {first_line[:400]}",
        )
    except Exception:  # noqa: BLE001 - a record is evidence, not control flow
        logger.debug("Could not record the sprint plan decision", exc_info=True)
    return update

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
    _name_the_stage_on_the_run(config["configurable"].get(APP_RUN_ID_KEY), stage_name)

    # Narration only. `build_activity_callbacks` returns [] when the run id is
    # unknown or the feature is switched off, and the handler never raises.
    from app.server.agent_stream import build_activity_callbacks

    activity = build_activity_callbacks(config["configurable"].get(APP_RUN_ID_KEY), stage_name)

    pending_decision = state.get("pending_decision")
    if pending_decision is not None and not state.get("pending_inner_thread_id"):
        # A decision with no gate waiting for it answers nothing. Resumed on a
        # conversation made up for it, the stage ran with no request at all:
        # measured on one run, rewound while parked on another stage's gate,
        # the resume answered that gate, and the rewound review was handed
        # only the project memory - it read the specification for itself and
        # never saw the request built for it. It starts as a stage starts.
        logger.warning(
            "Stage %s was handed a decision with no gate waiting for it; it starts afresh", stage_name,
        )
        pending_decision = None
    if pending_decision is not None:
        inner_thread_id = state.get("pending_inner_thread_id")
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
                # Most of a stage's calls run here, resumed after a gated tool:
                # the retry carries this conversation on, as in the branch below.
                from app.graph import abandoned_threads

                abandoned_threads.remember(
                    getattr(state.get("repository"), "root_path", None), outer_thread_id, stage_name,
                    inner_thread_id, process=abandoned_threads.AFTER_A_TRANSIENT_ERROR,
                )
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
        # Unless a stopped worker cut the last visit off mid-conversation: that
        # is not a new attempt, and it carries on (`app.graph.abandoned_threads`).
        from app.graph import abandoned_threads

        visit_root = getattr(state.get("repository"), "root_path", None)
        cut_off = abandoned_threads.cut_off(visit_root, outer_thread_id, stage_name, agent)
        inner_thread_id = cut_off[0] if cut_off else f"{outer_thread_id}:{stage_name}:{uuid.uuid4().hex[:8]}"
        if cut_off:
            logger.warning(
                "Stage %s was cut off (a stopped worker or a transient model error); carrying on in its own "
                "conversation", stage_name,
            )
        abandoned_threads.remember(visit_root, outer_thread_id, stage_name, inner_thread_id)
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
        from app.agents.project_snapshot import for_a_stage

        snapshot = for_a_stage(getattr(state.get("repository"), "root_path", None))
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
                    None if cut_off else initial_request,
                    config=_inner_agent_config(
                        inner_thread_id,
                        config["configurable"].get(APP_RUN_ID_KEY),
                        activity,
                        stage=stage_name,
                        recursion_limit=INNER_AGENT_RECURSION_LIMIT,
                    ),
                )
            abandoned_threads.forget(visit_root, outer_thread_id, stage_name)
        except Exception as exc:  # noqa: BLE001 - re-raised unless handled below
            abandoned_threads.forget(visit_root, outer_thread_id, stage_name)
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
                # Another attempt at the call, not at the stage: the retry
                # carries this conversation on from its last saved step.
                abandoned_threads.remember(
                    visit_root, outer_thread_id, stage_name, inner_thread_id,
                    process=abandoned_threads.AFTER_A_TRANSIENT_ERROR,
                )
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
        if structured_response is None and was_stopped_by_the_budget(result):
            structured_response = _a_fix_recorded_from_its_writes(stage_name, result)
            if structured_response is not None:
                logger.warning(
                    "Stage %s was stopped at its model-call budget without an answer; recorded from the "
                    "%d file(s) it wrote instead of starting it over", stage_name,
                    len(structured_response.changed_files),
                )
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
        structured_response = _the_answer_in_parts(
            config["configurable"].get(APP_RUN_ID_KEY), stage_name, agent, initial_request, result,
        )

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
        from app.graph.agent_loop_fix_limits import ends_for_good

        restarted = (
            None
            if out_of_room or ends_for_good(stage_name, result)
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
            raise StageGaveNoAnswer(
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

    # Reported changes nothing made: dropped from the record, deterministically
    # (Initiative Q.4). The clarification this used to send was a full model
    # call on the stage's own thread - eleven a day - and the two stages
    # measured receiving it doubled down anyway: one call from its budget, its
    # tools withheld, it named the same file again. The harness already holds
    # the ground truth (write receipts), so the drop costs nothing and the
    # record keeps only what changed. The warning is the counting line for the
    # per-model claim rate; see `_files_it_claims_but_never_wrote` for what
    # counts as a receipt.
    from app.agents.settled_answer import was_stopped_by_the_budget as _stopped_by_the_budget

    never_wrote = _files_it_claims_but_never_wrote(result, structured_response)
    if never_wrote:
        logger.warning(
            "Stage %s claimed %d file(s) nothing in it wrote: %s; dropped from the record, "
            "no model call", stage_name, len(never_wrote), ", ".join(never_wrote),
        )
        structured_response = _claims_dropped_from_the_record(structured_response, never_wrote)

    kept_as_blockers: list[str] = []
    if not never_wrote and not _stopped_by_the_budget(result):
        diagnostics = _diagnostics_in_files_touched(state, result, structured_response, stage_name)
        # Only what the stage may write is put to it; an error in another's file is its answer's blocker (PA.8).
        from app.graph import its_own_to_fix

        root_path = str(getattr(state.get("repository"), "root_path", "") or "")
        diagnostics, not_its_own = its_own_to_fix.split(
            root_path, stage_name, config["configurable"].get(APP_RUN_ID_KEY), diagnostics)
        if not_its_own:
            logger.warning(
                "Stage %s: errors in files it may not write kept as its blockers, not put to it: %s",
                stage_name, "; ".join(not_its_own),
            )
            kept_as_blockers = its_own_to_fix.blocker_lines(root_path, stage_name, not_its_own)
            structured_response = its_own_to_fix.with_blockers(structured_response, kept_as_blockers)
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
                structured_response = its_own_to_fix.with_blockers(
                    answer_without_leaked_turns(followed["structured_response"]), kept_as_blockers)

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


def _a_model_to_revise_with(judgement_model: Any) -> Any:
    """The judgement model, or the deployment's own when none is named; never raises.

    No model named is a local-only run, not a reason to skip the in-place
    revision: the parts writer resolves the same `None` the same way.
    """
    if judgement_model is not None:
        return judgement_model
    try:
        from app.models import build_default_chat_model

        return build_default_chat_model()
    except Exception:  # noqa: BLE001 - the architect revises as before
        logger.warning("Could not build a model to revise the specification in place", exc_info=True)
        return None


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
    # Every list section, not only the required ones: a repair of `testing` is
    # not a reason to lose the interface design, the file plan or the
    # function contracts either.
    sections = [
        name for name in getattr(type(revised), "model_fields", {}).keys()
    ]
    kept = {
        section: getattr(previous, section)
        for section in sections
        if not getattr(revised, section, None) and getattr(previous, section, None)
    }
    if kept:
        logger.info("The repaired specification left %s empty; kept them from the previous answer", ", ".join(kept))
    return revised.model_copy(update=kept) if kept else revised


def _the_scaffold_s_layout(state: Any) -> str:
    """The files the chosen pack's scaffold serves and where its tests live, for the architect; "" when no pack fits.

    See `_the_scaffold_s_facts`.
    """
    facts = _the_scaffold_s_facts(state)
    if not facts:
        return ""
    return "\n\n--- The layout the project is set up with (write the file plan in it) ---\n" + "\n".join(facts) + "\n"


def _the_setup_for_the_review(state: Any) -> str:
    """The same facts for the architecture review; "" when no pack fits. See `build_architecture_review_request`."""
    return "\n".join(_the_scaffold_s_facts(state))


def _the_scaffold_s_facts(state: Any) -> list[str]:
    """The chosen pack's layout and data store, one line each; [] when no pack fits.

    The architect wrote the file plan knowing the stack, not the layout the
    harness would set up for it. Measured on one run: the plan put the service
    in `backend/app/` and the page in `frontend/src/` while the scaffold served
    the package's `main.py` and `src/App.tsx`; 28 files were drafted where
    nothing served them. Never raises.
    """
    try:
        from app.stacks import choose_pack, the_python_package
        from app.tools.repository import pinned_project_directory

        stack = getattr(state.get("stack_selection"), "technology_stack", None)
        brief = getattr(state.get("document"), "text", "") or ""
        pack = choose_pack(stack, brief) if stack is not None else None
        if pack is None:
            return []
        root = getattr(state.get("repository"), "root_path", None)
        project = (pinned_project_directory(Path(root)) if root else None) or ""
        package = the_python_package(project, brief) if project and pack.language == "python" else None
        # The same lines every builder and judge reads once the scaffold is
        # set up (plan CM.1): one function, so the two cannot drift.
        from app.agents.shared_facts import layout_facts, what_the_setup_decides

        return [*layout_facts(pack, project, package), *what_the_setup_decides(pack, project, package)]
    except Exception:  # noqa: BLE001 - the architect plans as before
        logger.debug("Could not describe the scaffold's layout", exc_info=True)
        return []


def _the_layout_repair(served: list[str], state: Any) -> str:
    """What the architect is told when its file plan names none of the served files.

    Each path from the workspace root, as the file plan writes them. Measured
    live: told "the scaffold serves `src/App.tsx`, `pkg/main.py`" with no folder,
    the architect planned `pkg/src/App.tsx` - the page inside the service's
    package - and two repairs later the plan still built it where nothing
    served it.
    """
    project = ""
    try:
        from app.tools.repository import pinned_project_directory

        root = getattr(state.get("repository"), "root_path", None)
        project = (pinned_project_directory(Path(root)) if root else None) or ""
    except Exception:  # noqa: BLE001 - the paths as the check gave them
        project = ""
    named = [f"{project}/{path}" if project and not path.startswith(f"{project}/") else path for path in served]
    where = (
        f" (paths from the workspace root: the project folder is `{project}/`)" if project else ""
    )
    return (
        "The project's scaffold serves "
        + ", ".join(f"`{path}`" for path in named)
        + where
        + ": the acceptance suite runs the product through exactly these files, and the "
        "file plan names none of them, so what it plans would be built where nothing serves "
        "it. Plan the product in those files - or in modules they import - and keep the "
        "project's layout. Return only `file_plan`, `component_boundaries` and "
        "`implementation_order` with the paths corrected; unchanged sections are "
        "automatically preserved."
    )


#: The settings the harness itself gives the product when it starts it.
_GIVEN_AT_START = frozenset({"PORT", "DATA_DIR"})
#: A setting said to be needed before the product can start, in one sentence.
_NEEDED_TO_START = re.compile(
    r"`?\b([A-Z][A-Z0-9]*_[A-Z0-9_]+|[A-Z]{3,})\b`?[^.;\n]{0,160}?"
    r"(?:required at start(?:up)?|refuses? to start|fails? (?:to start )?if (?:it is )?(?:missing|unset|not set)"
    r"|Default:\s*None|must be (?:set|provided)\b[^.;\n]{0,40}?(?:start|run))",
    re.I,
)


def _settings_it_cannot_start_without(specification: Any) -> list[str]:
    """The settings, besides the ones the harness gives, the specification says the product cannot start without.

    Measured on one gate run: the environment contract told every stage the
    product starts from `PORT` and `DATA_DIR` alone, and the specification said
    in six sections that `SECRET_KEY` is "required at startup. Default: None
    (service fails if missing)" - the product did not start for the suite, and
    every fix was told to keep what the specification gives.
    """
    try:
        text = " ".join(
            str(value) for value in (specification.model_dump() if hasattr(specification, "model_dump") else {}).values()
        )
    except Exception:  # noqa: BLE001 - the specification goes on as written
        return []
    found = []
    for match in _NEEDED_TO_START.finditer(text):
        name = match.group(1)
        if name.upper() == name and name not in _GIVEN_AT_START and name not in found and name not in {"JWT", "API", "URL", "HTTP", "CORS"}:
            found.append(name)
    return found


def _the_startup_repair(required: list[str]) -> str:
    """What the architect is told when the specification makes the product unable to start as the harness starts it."""
    named = ", ".join(f"`{name}`" for name in required)
    return (
        f"The specification says the product cannot start without {named}. Every test here starts "
        "it with only `PORT` and `DATA_DIR` set (the environment contract), so as written it never "
        "starts for them. Give each a development default the environment overrides, or generate it "
        "at first start and keep it under `DATA_DIR`; a production deployment still sets it. Return "
        "only the sections that say otherwise - `configuration`, `security_and_privacy`, `deployment`, "
        "`error_catalogue`, `function_contracts`, `file_plan` - corrected; unchanged sections are "
        "automatically preserved."
    )


def _the_served_files_the_plan_leaves_out(specification: Any, state: Any) -> list[str]:
    """The files the stack's scaffold serves that the specification's file plan never names; [] if none or unknown.

    Measured on one run: the file plan put the product in `frontend/` and
    `backend/app/`; the scaffold served `src/App.tsx` and the package's
    `main.py`; nothing drafted was ever served and every page test failed its
    first control. Said to the architect, the cheapest moment to fix it.
    """
    try:
        from app.stacks import choose_pack, the_python_package
        from app.tools.repository import pinned_project_directory

        stack = getattr(state.get("stack_selection"), "technology_stack", None)
        pack = choose_pack(stack, getattr(state.get("document"), "text", "") or "") if stack is not None else None
        if pack is None:
            return []
        declared = [e for e in (getattr(pack, "entrypoint", ""), *(getattr(pack, "entrypoints", ()) or ())) if e]
        if not declared:
            return []
        root = getattr(state.get("repository"), "root_path", None)
        project = pinned_project_directory(Path(root)) if root else None
        package = (the_python_package(project, getattr(state.get("document"), "text", "") or "")
                   if project and pack.language == "python" else None)
        plan = " ".join(str(item) for item in getattr(specification, "file_plan", None) or [])
        if not plan.strip():
            return []
        served = [pack.filled(e, project or "", "", package) for e in declared]

        def named(path: str) -> bool:
            # The path itself or under the project folder - `frontend/src/App.tsx` is not `src/App.tsx`.
            where = rf"(?:{re.escape(project)}/)?" if project else ""
            return re.search(rf"(?<![\w./-]){where}{re.escape(path)}(?![\w/.-])", plan) is not None

        return [path for path in served if not named(path)]
    except Exception as error:  # noqa: BLE001 - the specification goes on as written
        degraded("spec_check.served_files_in_plan", error)
        return []


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
    if state.get("architecture_revision_count", 0) + 1 >= _the_revision_limit():
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


class _HarnessFindingsRechecked:
    """`HARNESS_FINDINGS_RECHECKED`: a revision made only for the workflow's own findings is checked by them, not reviewed again.

    Measured on one day: in three runs the reviewer approved the specification, one of the workflow's checks below
    added a finding, and after the revision a whole second review raised new findings and escalated - which also
    skips the code reviews. The checks are mechanical and cheap; the second review costs minutes and starts over.
    Behind a switch, measured: a second review can catch an error the revision brings in.
    """

    ON_BY_DEFAULT = False
    #: What the admin page says this switch does.
    explanation = ("When the design reviewer approves and only the workflow's own checks send the specification back, "
                   "the revision is checked by those checks alone, not reviewed again whole.")

    @staticmethod
    def enabled() -> bool:
        from app.switches import is_on

        return is_on("HARNESS_FINDINGS_RECHECKED", _HarnessFindingsRechecked.ON_BY_DEFAULT)


harness_findings_rechecked = _HarnessFindingsRechecked()

#: The workflow's own design checks, by name, each asked again as if for the first time.
_THE_HARNESS_S_DESIGN_CHECKS = {
    "coverage": lambda state, spec: _a_success_measure_the_specification_drops(state, spec),
    "deferrals": lambda state, spec: _a_brief_feature_the_specification_defers(state, spec),
    "contract": lambda state, spec: _contract_lines_nothing_can_read(state),
    "kept": lambda state, spec: _behaviour_the_specification_gives_kept_files(state, spec),
    "order": lambda state, spec: _the_same_command_in_another_order(state, spec),
    "signature": lambda state, spec: _a_kept_signature_the_specification_calls_otherwise(state, spec),
}
_THE_CHECKS_ONCE_FLAGS = ("specification_coverage_checked", "specification_deferrals_checked",
                          "specification_contract_lines_checked", "specification_kept_files_checked",
                          "specification_command_order_checked", "specification_signatures_checked")


def _the_harness_findings_still_open(state: Any, spec_text: str, names: Sequence[str]) -> list[Any]:
    """The findings the named checks still raise on the specification as it is now; never raises (an error is open)."""
    fresh = {**state, "architecture_revision_count": 0, **{flag: False for flag in _THE_CHECKS_ONCE_FLAGS}}
    still = []
    for name in names:
        check = _THE_HARNESS_S_DESIGN_CHECKS.get(name)
        if check is None:
            continue
        try:
            found = check(fresh, spec_text)
        except Exception as failure:  # noqa: BLE001 - not known to be settled
            degraded("design_check.asked_again", failure)
            return [object()]
        if found is not None:
            still.append(found)
    return still


def _the_harness_s_findings_now(state: Any, spec_text: str, names: Sequence[str]) -> list[tuple[str, Any]]:
    """(name, finding) for each named check that finds something on the specification as it is now, asked as if for the
    first time. A check that cannot be asked finds nothing, as it does when asked the first time. Never raises."""
    fresh = {**state, "architecture_revision_count": 0, **{flag: False for flag in _THE_CHECKS_ONCE_FLAGS}}
    found = []
    for name in names:
        check = _THE_HARNESS_S_DESIGN_CHECKS.get(name)
        if check is None:
            continue
        try:
            finding = check(fresh, spec_text)
        except Exception as failure:  # noqa: BLE001 - as the check itself does
            degraded("design_check.asked_again", failure)
            continue
        if finding is not None:
            found.append((name, finding))
    return found


def _approved_once_the_harness_s_findings_are_settled(state: Any, spec_text: str) -> dict[str, Any] | None:
    """The approving update for a revision that settled the workflow's own findings on an approved specification; else None.

    Behind `HARNESS_FINDINGS_RECHECKED`. None - review it as usual - when the switch is off, nothing was overturned,
    no revision has been made, or a check still finds what it found.
    """
    overturned = list(state.get("approved_but_for_the_harness") or [])
    if not (overturned and harness_findings_rechecked.enabled() and state.get("architecture_revision_count", 0) >= 1):
        return None
    from app.graph import design_gate

    # Thorough delivery: a gating finding the reviewer raised is settled only by a review (`app.graph.design_gate`).
    if design_gate.a_finding_the_reviewer_raised_is_open(state):
        return None
    if _the_harness_findings_still_open(state, spec_text, overturned):
        return None
    from app.agents.architecture_reviewer import ArchitectureReviewOutput
    from app.decisions import record_decision

    logger.info("The revision settled the workflow's own findings (%s): approved without a second review",
                ", ".join(overturned))
    approved = ArchitectureReviewOutput(status="approved", findings=[])
    update: dict[str, Any] = {"architecture_review": approved, "approved_but_for_the_harness": []}
    design_gate.settled_by_the_checks(state, update, f"the workflow's checks ({', '.join(overturned)}) no longer find it")
    _record_document(state, "docs/architecture_review.md", render_architecture_review(approved))
    record_decision(
        state, update, point="technical_specification",
        question="Is the specification ready to build from?",
        options=["approve", "send it back to the architect"], decision="approve",
        rationale=("The architecture reviewer approved it; the revision settled the workflow's own findings "
                   f"({', '.join(overturned)}), checked again by the same checks."),
    )
    update["stage"] = "user_review_specification" if _review_enabled(state, SPECIFICATION_REVIEW) else "scaffold"
    return update


def _decided_after_one_revision(state: Any, spec_text: str) -> dict[str, Any] | None:
    """The update for a specification revised once, decided by the deterministic gates instead of a second review.

    Behind `ONE_DESIGN_REVIEW` (`app.graph.one_design_review`); None - review it as usual - when off or not yet revised.
    Approved when the workflow's own design checks and the contradiction check find nothing open; otherwise the design
    escalation, which records each open point as a known risk or settles it.
    """
    from app.graph import design_gate, one_design_review

    # Thorough delivery reviews every revision again (`app.graph.design_gate`): the gates below would send what they
    # leave open to an escalation that builds with it.
    if design_gate.applies() or not one_design_review.applies(state.get("architecture_revision_count", 0)):
        return None
    still = _the_harness_findings_still_open(state, spec_text, list(_THE_HARNESS_S_DESIGN_CHECKS))
    open_points = [
        _format_finding(found) if hasattr(found, "description") else "A design check could not be asked again."
        for found in still
    ] + one_design_review.contradictions(state.get("technical_specification"))
    previous = state.get("architecture_review")
    answered = len((previous.get("findings") if isinstance(previous, dict) else getattr(previous, "findings", None)) or [])
    logger.info("The specification was %s: %d point(s) still open", one_design_review.SAID, len(open_points))
    if open_points:
        return {
            "stage": "escalation",
            "error": None,
            "escalation": {
                "kind": "design",
                "findings": open_points,
                "error": (f"The specification was {one_design_review.SAID}: after one revision for {answered} review "
                          f"finding(s), the workflow's checks still find {len(open_points)} point(s) open."),
            },
        }
    from app.agents.architecture_reviewer import ArchitectureReviewOutput
    from app.decisions import record_decision

    approved = ArchitectureReviewOutput(status="approved", findings=[])
    update: dict[str, Any] = {"architecture_review": approved}
    _record_document(state, "docs/architecture_review.md", render_architecture_review(approved))
    record_decision(
        state, update, point="technical_specification",
        question="Is the specification ready to build from?",
        options=["approve", "send it back to the architect"], decision="approve",
        rationale=(f"The specification was {one_design_review.SAID}: one revision answered the review's {answered} "
                   "finding(s), and the workflow's design checks and the contradiction check find nothing open."),
    )
    update["stage"] = "user_review_specification" if _review_enabled(state, SPECIFICATION_REVIEW) else "scaffold"
    return update


def _the_same_command_in_another_order(state: Any, spec_text: str) -> Any:
    """A major finding for command lines that differ only in the order of their arguments and give different results.

    Measured on two runs of one brief, both false acceptances: the specification gave `--top N --json` and
    `--json --top N` different output, the suite tested both, and the product followed the one the brief did not
    state. Once per run, and never on the revision that would exhaust the limit, like the checks beside it.
    """
    if state.get("specification_command_order_checked"):
        return None
    if state.get("architecture_revision_count", 0) + 1 >= _the_revision_limit():
        return None
    from app.acceptance.interface_contract import commands_that_differ_only_in_order

    pairs = commands_that_differ_only_in_order(spec_text)
    if not pairs:
        return None
    from app.agents.architecture_reviewer import ArchitectureReviewFinding

    return ArchitectureReviewFinding(
        severity="major",
        description=(
            "The specification gives one command two results by the order of its options alone: "
            + "; ".join(f"`{a}` against `{b}`" for a, b in pairs)
            + ". The order of a command's options does not change what it does."
        ),
        evidence="Compared by the workflow across the specification's command lines.",
        required_remediation=(
            "Give the command one result whatever the order of its options - the one the brief states - and "
            "change every line and criterion that says otherwise."
        ),
    )


def _contract_lines_nothing_can_read(state: Any) -> Any:
    """A major finding for the interface contract's lines that follow none of its forms, behind the switch.

    Measured on one run: 32 of 58 lines at the lock read as nothing, and the release was the first to say so, when no
    one could still rewrite them. Raised by the workflow, like `_a_brief_feature_the_specification_defers`: once per
    run, and never on the revision that would exhaust `MAX_ARCHITECTURE_REVISIONS`.
    """
    from app.acceptance import interface_contract

    if (not interface_contract.unread_at_review_switch.enabled() or state.get("specification_contract_lines_checked")
            or state.get("architecture_revision_count", 0) + 1 >= _the_revision_limit()):
        return None
    from app.stacks import product_kind

    # A library's interface is its public functions: its contract lines are calls, the three forms the reader knows
    # (a request, a page control, a command line) do not apply to it, and the finding asked for a rewrite no product of
    # that kind can use (measured on a library run: ten calls written `AC-1 command textkit.slugify(...) -> ...`).
    if product_kind(getattr(state.get("stack_selection"), "technology_stack", None)) == "library":
        return None
    lines = getattr(state.get("technical_specification"), "interface_contract", None) or ()
    text = interface_contract.unread_lines_finding(lines)
    if not text:
        return None
    from app.agents.architecture_reviewer import ArchitectureReviewFinding

    return ArchitectureReviewFinding(
        severity="major",
        description=text,
        evidence="Read by the workflow with the same reader the suite's lock and the release use.",
        required_remediation=(
            "Rewrite each in one of the three forms: `AC-3 GET /api/orders -> 200`, `AC-1 page /login textbox \"Email\"`, "
            "`AC-5 command ledger add 12.50 -> exit 0`. What a line is for goes before its arrow or in the other sections."
        ),
    )


def _a_brief_feature_the_specification_defers(state: Any, spec_text: str) -> Any:
    """A major finding for a feature the operator's brief lists and the specification defers.

    The review is told of these and judges each, and that was not enough.
    Measured on one gate run: the review's request named "reminders" from the
    brief's "Due dates and reminders" as deferred - and a major finding - and
    its eight findings never mentioned it; the product shipped without them,
    as the run before it had. Raised by the workflow, like
    `_a_success_measure_the_specification_drops`: once per run, and never on
    the revision that would exhaust `MAX_ARCHITECTURE_REVISIONS`.
    """
    if state.get("specification_deferrals_checked"):
        return None
    if state.get("architecture_revision_count", 0) + 1 >= _the_revision_limit():
        return None
    brief = getattr(state.get("document"), "text", "") or ""
    from app.analysis.integration_checks import brief_features_the_text_defers

    found = brief_features_the_text_defers(brief, spec_text)
    if not found:
        return None
    from app.agents.architecture_reviewer import ArchitectureReviewFinding

    return ArchitectureReviewFinding(
        severity="major",
        description=(
            "The specification defers a feature the operator's brief requires: "
            + "; ".join(f"`{feature}` (the brief: \"{line}\"; the specification: \"{where}\")"
                        for feature, line, where in found)
            + ". Deferring a requirement is the operator's decision, not the run's."
        ),
        evidence="Compared by the workflow against the operator's brief, word for word.",
        required_remediation=(
            "Specify each one as the other features are specified - its data, the functions or "
            "endpoints that carry it, the interface that shows it, and an acceptance criterion that "
            "verifies it - or, where the specification builds it under another name, say where."
        ),
    )


#: Behaviour a specification has given the pack's kept start files that a review then sends a sprint back for:
#: handling the stop signals. Narrow on purpose: measured over 20 specifications, broader words (validates,
#: persists) named test lines and deferral lists in 13, and "creates the data directory" 9 runs that all passed,
#: since the product creates it anyway; the stop signals cost a milestone revision and a blocking finding.
_PRODUCT_BEHAVIOUR = re.compile(
    r"\b(?:SIGTERM|SIGINT|signal\s+handl\w*|graceful(?:ly)?\s+shut\w*|shutdown\s+handl\w*)", re.I)
#: How far after the file's name the behaviour may be named for the file to be its subject.
_NEAR_ITS_NAME = 100
#: A sentence about tests or about what is left out says nothing of what a file does.
_NOT_ABOUT_THE_FILE = re.compile(r"\b(?:AC|CR)-\d+\b|\btests?\b|\bassert\w*|\bdefer\w*|\bout of scope\b", re.I)
#: Another file named in a sentence, which the behaviour may belong to instead.
_ANOTHER_FILE_NAMED = re.compile(r"\b[\w-]+\.(?:[cm]?[jt]sx?|py|rb|go|rs|java|kt|cs|php|sh|json|toml|ya?ml)\b")


def _gives_it_behaviour(sentence: str, start: int, end: int) -> bool:
    """Whether a sentence gives the file at `start:end` the behaviour: named soon after it, no other file between."""
    if _NOT_ABOUT_THE_FILE.search(sentence):
        return False
    for match in _PRODUCT_BEHAVIOUR.finditer(sentence, end):
        between = sentence[end:match.start()]
        if len(between) <= _NEAR_ITS_NAME and not _ANOTHER_FILE_NAMED.search(between):
            return True
    return False


def _behaviour_the_specification_gives_kept_files(state: Any, spec_text: str) -> Any:
    """A major finding for each sentence of the specification that gives product behaviour to a file the pack keeps.

    Measured on four runs: told the pack's files are the harness's and do nothing more, the specification still
    wrote "Entry Point (src/main.ts - kept by harness): ... registering signal handlers for graceful shutdown ...
    Creates DATA_DIR" and "start.sh creates DATA_DIR"; the design reviews left it open and a milestone review sent a
    sprint back for it. Raised by the workflow like `_a_brief_feature_the_specification_defers`: once per run, and
    never on the revision that would exhaust `MAX_ARCHITECTURE_REVISIONS`. Never raises.
    """
    try:
        if state.get("specification_kept_files_checked"):
            return None
        if state.get("architecture_revision_count", 0) + 1 >= _the_revision_limit():
            return None
        from app.stacks import choose_pack

        stack = getattr(state.get("stack_selection"), "technology_stack", None)
        pack = choose_pack(stack, getattr(state.get("document"), "text", "") or "") if stack is not None else None
        if pack is None:
            return None
        kept = {*pack.kept_files, *(["start.sh"] if "start.sh" in (pack.files or {}) else [])}
        served = [e for e in (pack.entrypoint, *pack.entrypoints) if e and e not in kept]
        names = {PurePosixPath(path).name: path for path in kept}
        found: list[tuple[str, str]] = []
        for sentence in re.split(r"(?<=[.!?])\s+|\n", spec_text or ""):
            for name, path in names.items():
                at = re.search(rf"(?<![\w.-]){re.escape(name)}\b", sentence)
                if at and _gives_it_behaviour(sentence, at.start(), at.end()):
                    found.append((path, " ".join(sentence.split())[:200]))
                    break
        if not found:
            return None
        from app.agents.architecture_reviewer import ArchitectureReviewFinding

        files = sorted({path for path, _ in found})
        return ArchitectureReviewFinding(
            severity="major",
            description=(
                "The specification gives product behaviour to "
                + ", ".join(f"`{path}`" for path in files)
                + ", which the harness writes and keeps as it is - no work order may change "
                + ("it" if len(files) == 1 else "them") + ": "
                + "; ".join(f"\"{where}\"" for _, where in found[:4])
                + "."
            ),
            evidence="Compared by the workflow against the files the stack's setup keeps.",
            required_remediation=(
                "Give that behaviour to the product's own files"
                + (f" - `{served[0]}`, which the start file loads, or a module it imports" if served else "")
                + " - in every section that names it, and say what the kept file does only as it is."
            ),
        )
    except Exception as error:  # noqa: BLE001 - the review stands as written
        degraded("spec_check.kept_files_behaviour", error)
        return None


def kept_signatures_called_otherwise(state: Any, spec_text: str) -> list[tuple[str, str, str]]:
    """(file, declaration, the specification's sentence) for each declaration the setup keeps with no parameters that
    the specification calls with arguments; [] without a pack. Never raises."""
    try:
        from app.stacks import choose_pack

        stack = getattr(state.get("stack_selection"), "technology_stack", None)
        pack = choose_pack(stack, getattr(state.get("document"), "text", "") or "") if stack is not None else None
        if pack is None:
            return []
        found: list[tuple[str, str, str]] = []
        for relative, kept in (getattr(pack, "required_signatures", None) or {}).items():
            for _pattern, written in kept:
                named = re.search(r"(\w+)\s*\(\s*\)", written)
                if named is None:
                    continue
                # A declaration with parameters counts too: in a specification, `pub fn app(state: AppState)` is the
                # contradiction itself (measured on one Rust run, the sentence a revision kept).
                call = re.compile(rf"(?<![\w.]){re.escape(named.group(1))}\s*\(\s*(?!\))[^)\n]{{1,80}}\)")
                for sentence in re.split(r"(?<=[.!?])\s+|\n", spec_text or ""):
                    if call.search(sentence):
                        found.append((relative, written, " ".join(sentence.split())[:200]))
        return found
    except Exception as error:  # noqa: BLE001 - nothing found is the old behaviour
        degraded("spec_check.kept_signature_found", error)
        return []


def _a_kept_signature_the_specification_calls_otherwise(state: Any, spec_text: str) -> Any:
    """A major finding when the specification calls a declaration the pack keeps with no parameters, with arguments.

    Measured on two Rust runs: the stack's setup declares `pub fn app() -> Router` (its start file and tests call it
    bare), and the specification designed "main opens the Store ... passed to app()" and "axum::serve on app(store)".
    The builders followed the specification, the pack's contract was raised against it in every round, and two sprint
    attempts were spent on a design that could not satisfy both. Raised once per run, like the other checks here, and
    never on the revision that would exhaust `MAX_ARCHITECTURE_REVISIONS`. Never raises.
    """
    try:
        if state.get("specification_signatures_checked"):
            return None
        if state.get("architecture_revision_count", 0) + 1 >= _the_revision_limit():
            return None
        found = kept_signatures_called_otherwise(state, spec_text)
        if not found:
            return None
        from app.agents.architecture_reviewer import ArchitectureReviewFinding

        relative, written, where = found[0]
        return ArchitectureReviewFinding(
            severity="major",
            description=(
                f"The specification calls `{written.split('(')[0].split()[-1]}` with arguments - \"{where}\" - but the "
                f"stack's setup declares it `{written}` in `{relative}`, and its start file and tests call it with none. "
                "The builders follow the specification, so the product is built against a declaration it cannot keep."
            ),
            evidence="Compared by the workflow against the declarations the stack's setup keeps.",
            required_remediation=(
                f"Specify `{written}` as declared: whatever the call would have been passed, the function builds for "
                "itself inside (from the environment and the configuration it reads), and every caller - the entry "
                "point, the tests - calls it as declared. Change every section that passes it something."
            ),
        )
    except Exception as error:  # noqa: BLE001 - the review stands as written
        degraded("spec_check.kept_signature", error)
        return None


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


def _milestone_findings_that_block(state: Any, review: Any) -> list[Any]:
    """The milestone review's blocking findings; with `MILESTONE_EVIDENCE_GATE` on, only those a test or check shows."""
    blocking = _findings_that_block(review, state["repository"].root_path)
    from app.graph import milestone_evidence

    if not blocking or not milestone_evidence.enabled():
        return blocking
    shown, unshown = milestone_evidence.shown_and_not(state, blocking)
    if unshown:
        logger.warning("Milestone review: %d blocking finding(s) no test, check or underline shows; advice, not a "
                       "send-back (MILESTONE_EVIDENCE_GATE)", len(unshown))
    return shown


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


def _the_scope_cuts(state: Any, deferred_here: list[str], accepted_at_escalation: str) -> list[dict[str, str]]:
    """Each criterion an accepted sprint went on without, with why (`app.sprint.record.scope_cuts`); never raises."""
    try:
        from app.acceptance import suite
        from app.graph.acceptance_nodes import _failing_due
        from app.sprint import record as sprint_record

        root = state["repository"].root_path
        failing = _failing_due(state)[0] if accepted_at_escalation else []
        return sprint_record.scope_cuts(deferred_here, suite.deferred(root), failing, accepted_at_escalation)
    except Exception:  # noqa: BLE001 - the status line still names what was deferred
        logger.debug("Could not name the sprint's scope cuts", exc_info=True)
        return []


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


#: Characters of a defect's actual behaviour an attempt's record keeps.
DEFECT_CAUSE_KEPT = 1_200


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
                # What it showed, so a sprint planned again knows its cause, not
                # only its name: "the product does not start" says nothing of why.
                "actual_behavior": str(getattr(defect, "actual_behavior", "") or "")[:DEFECT_CAUSE_KEPT],
                "found_in_round": getattr(defect, "found_in_round", None),
            }
            for defect in (getattr(cycle, "defects", None) or [])
        ],
    }


def the_attempt_in_progress(state: Mapping[str, Any]) -> dict[str, Any]:
    """The attempt at the current sprint the run is working through, as `_record_sprint_summary` would record it.

    For the run page while the run is live (`sprint_summary.sprint_views`): an
    attempt is recorded only when it ends, so between two records the page had
    nothing newer than the attempt before this one.
    """
    earlier = list(state.get("sprint_earlier_plans") or [])
    now = _what_a_plan_did(state.get("milestone_plan"), state.get("remediation"))
    return {
        "sprint_index": state.get("current_sprint_index", 0),
        "rounds": state.get("test_round", 0),
        "features": [feature for done in earlier for feature in done.get("features") or []] + now["features"],
        "defects": [defect for done in earlier for defect in done.get("defects") or []] + now["defects"],
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
    except Exception as error:  # noqa: BLE001 - a summary without the record beats no summary
        degraded("sprint_record", error)

    deferred_here = _deferred_in_this_attempt(state, since)
    attempt = {
        "sprint_index": sprint_index,
        "number": len(already) + 1,
        "status": status,
        "deferred": deferred_here,
        "scope_cuts": _the_scope_cuts(state, deferred_here, accepted_at_escalation) if status == "Completed" else [],
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
    except Exception as error:  # noqa: BLE001 - as above
        degraded("sprint_summary", error)
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
    except Exception as failure:  # noqa: BLE001 - the round as reported stands
        degraded("check.suite_the_stage_left_failing", failure)
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
    unlabelled = _A_LABEL.sub("", text or "", count=1)
    for match in _A_NAME.finditer(unlabelled):
        name = next(group for group in match.groups() if group).strip().lower()
        # A folder in a path says where a runner was, not what is wrong: measured on one run, the project folder in a
        # unit run's paths merged a criterion's own failure into that defect.
        if unlabelled[match.end():match.end() + 1] == "/" or unlabelled[max(0, match.start() - 1):match.start()] == "/":
            continue
        if _A_FILE_NAME.match(name) and not name.startswith(("#", ".")):
            continue
        names.add(name)
        # A name inside a quoted test name counts on its own as well.
        if match.group(1):
            names.update(_names_in(match.group(1)) - {name})
    return names


#: A compiler's or runtime's error location - `Program.cs(297,84)` or `server.go:10` - on a line that says error.
_AN_ERROR_AT = re.compile(r"([\w.-]+\.[A-Za-z]{1,6})(?:\((\d+)(?:,\d+)?\)|:(\d+))")


#: The harness's own wording of a compiler error a language service reported: `src/main.rs line 32: the trait ...`.
_A_REPORTED_ERROR_AT = re.compile(r"([\w./-]+\.[A-Za-z]{1,6}) line (\d+):")
#: How many lines after an error's own line still place it: rustc, Go vet and others name the place on the next lines
#: (`error[E0277]: ...` then `  --> src/main.rs:32:27`).
_LINES_AN_ERROR_NAMES_ITS_PLACE_IN = 3


def _error_locations(text: str) -> set[tuple[str, str]]:
    """The (file name, line) pairs `text` quotes for an error, lower-cased.

    A place counts on a line that says error, on the few lines after one (`--> file:line:col`), or in the harness's
    own `<file> line N:` wording of a reported compiler error. A warning's place does not.
    """
    found: set[tuple[str, str]] = set()
    since_error = _LINES_AN_ERROR_NAMES_ITS_PLACE_IN + 1
    for line in str(text or "").splitlines():
        lowered = line.lower()
        if "error" in lowered:
            since_error = 0
        elif "warning" in lowered:
            since_error = _LINES_AN_ERROR_NAMES_ITS_PLACE_IN + 1
        else:
            since_error += 1
        for match in _A_REPORTED_ERROR_AT.finditer(line):
            found.add((PurePosixPath(match.group(1)).name.lower(), match.group(2)))
        if since_error > _LINES_AN_ERROR_NAMES_ITS_PLACE_IN:
            continue
        for match in _AN_ERROR_AT.finditer(line):
            found.add((PurePosixPath(match.group(1)).name.lower(), match.group(2) or match.group(3)))
    return found


def _what_it_quotes(defect: Any) -> str:
    """A defect's description, with what the product's own start wrote when the start is in it (`start_output`)."""
    from app.acceptance import start_output

    return f"{getattr(defect, 'description', '') or ''}\n{start_output.in_text(str(getattr(defect, 'actual_behavior', '') or ''))}"


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
    # One compiler error quoted by both: measured on one C# run, "the unit tests fail" quoted `Program.cs(297,84):
    # error CS0721` and "the product does not start" carried the same error in what its start wrote; two fixers in
    # parallel took turns at one file for half an hour.
    if _error_locations(_what_it_quotes(one)) & _error_locations(_what_it_quotes(other)):
        return True
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


from app.graph.engineering import SAME_PROBLEM_ELSEWHERE  # noqa: E402 - the merge and the recheck share it


def _still_underlined(root: str, defect: Any) -> bool:
    from app.graph.engineering import still_underlined

    return still_underlined(root, str(getattr(defect, "description", "") or ""))


def _the_criteria_due(state: Any) -> list[str]:
    """The locked criteria this sprint is held to, as `id: text`; [] when none can be read."""
    try:
        from app.graph import acceptance_nodes

        due = set(acceptance_nodes.criteria_due(state) or [])
        return [f"{c.id}: {c.text}" for c in acceptance_nodes.suite.criteria(state["repository"].root_path)
                if not due or c.id in due]
    except Exception:  # noqa: BLE001 - the readiness check still reports it
        return []


def _names_a_cause(defect: Any) -> bool:
    """Whether the defect is a check's finding of a cause, not a symptom of one.

    The language service's findings (a name at a file and line, a package no
    manifest declares) are certain and say where the change is; a failing
    test only says something is wrong. So is the pack contract's (an entry
    file that no longer exports what the pack's start file imports): measured
    on a small-model run, it was merged under "The unit tests fail" and the
    fixers never read which name was gone.
    """
    from app.analysis import dependency_drift

    return (
        str(getattr(defect, "source", "") or "") in {"language service", "pack contract"}
        or str(getattr(defect, "description", "") or "").startswith(dependency_drift.OPENING)
    )


def _with_a_stopped_service_s_report(item: Any, others: list[Any]) -> str:
    """The lead defect's `actual_behavior`, with what a merged defect says a service wrote as it stopped by itself.

    A merge keeps only the lead's: the report that names the cause would go with the defect merged away.
    """
    from app.acceptance import start_output, suite as acceptance_suite

    actual = str(getattr(item, "actual_behavior", "") or "")
    for other in others:
        said = str(getattr(other, "actual_behavior", "") or "")
        for report in (acceptance_suite.what_a_stopped_service_wrote(said), start_output.in_text(said)):
            if report and report not in actual:
                actual = f"{actual}\n{report}".strip()
    return actual


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

    # The files of the causes each group holds. A symptom that names no file
    # joins any cause it shares a name with, and so joined every cause to
    # every other: measured on one gate run, a dozen unknown imports in five
    # files and the undeclared packages were merged under one failing test,
    # one fixer rewrote four files, and each round met the next import. Two
    # causes share a group only when they share a file.
    caused: dict[int, set[str]] = {
        i: {PurePosixPath(str(f)).name.lower() for f in getattr(d, "affected_files", None) or []}
        for i, d in enumerate(reported) if _names_a_cause(d)
    }
    caused_here = {i: set(files) for i, files in caused.items()}
    for i in range(len(reported)):
        for j in range(i + 1, len(reported)):
            ri, rj = root(i), root(j)
            # Two causes in one file are one fixer's: it rewrites that file.
            in_one_file = i in caused_here and j in caused_here and bool(caused_here[i] & caused_here[j])
            if ri == rj or not (in_one_file or _the_same_cause(reported[i], reported[j])):
                continue
            if ri in caused and rj in caused and not caused[ri] & caused[rj]:
                continue
            parent[rj] = ri
            if rj in caused:
                caused[ri] = caused.get(ri, set()) | caused.pop(rj)
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
        # A defect that names its cause leads the symptoms it explains: its
        # files are where the change is. Measured on one gate run: packages no
        # manifest declared were merged under "the suite fails ... importlib",
        # and the fix rewrote the code that imports them.
        # Next, a harness probe's finding leads a failing unit test it is merged with: the probe found the product
        # wrong at its interface, and its finding blocks the release. Measured on one run: led by "the unit tests
        # fail", the fixer was told the product was right and wrote tests only, and the release was not deliverable.
        from app.acceptance import probes_at_release

        group = sorted(group, key=lambda i: (not _names_a_cause(reported[i]),
                                             not probes_at_release.carries_a_finding(reported[i])))
        item = reported[group[0]]
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
        # What each check said the right outcome is, once each: a finding
        # about a module its importers lack says where the name belongs, and
        # the merge kept only the first finding's - measured: the module was
        # rewritten for its own finding and the routers' name never added.
        expected = list(dict.fromkeys(
            str(getattr(member, "expected_behavior", "") or "").strip() for member in (item, *others)
        ))
        merged.append(item.model_copy(update={
            "expected_behavior": " ".join(e for e in expected if e)[:2000],
            "actual_behavior": _with_a_stopped_service_s_report(item, others),
            "description": f"{item.description}{SAME_PROBLEM_ELSEWHERE}{also}",
            "affected_files": files,
            "severity": severity,
            # What each member measured, so the merged defect's cause key is all of theirs (deep review 1.1).
            **cause.as_merged(item, others),
        }))
        logger.warning(
            "%d defects describe one problem; merged into one: %s",
            len(group), " ".join(str(item.description).split())[:100],
        )
    return merged


_FAILING_LAYERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # The layer a failure was met at, read from its text. Deliberately the
    # layers where one cause fails many criteria - a server that does not
    # start, a route nobody serves, a middleware that refuses everything -
    # and deliberately not assertion outcomes, which are each criterion's own
    # symptom (Initiative L.1).
    ("connection-refused", re.compile(r"ECONNREFUSED|ECONNRESET|ERR_CONNECTION_REFUSED|ERR_CONNECTION_RESET")),
    ("not-found", re.compile(r"\b404\b|\bNot Found\b")),
    ("unauthorized", re.compile(r"\b40[13]\b|\bUnauthorized\b|\bForbidden\b")),
    ("server-error", re.compile(r"\b50[023]\b|\bInternal Server Error\b|\bBad Gateway\b|\bService Unavailable\b")),
    # A control the page never showed: every page test's first step meets it
    # when the page does not render. One run's round queued 13 defects, one per
    # criterion, each failing its first `locator.fill`/`locator.click` at
    # "Timeout 3000ms exceeded" - one cause, thirteen fixers.
    ("control-never-shown", re.compile(r"\blocator\.\w+: Timeout \d+m?s exceeded")),
    ("timeout", re.compile(r"Timeout \d+m?s exceeded|\bTimed out\b|\bETIMEDOUT\b|\bexceeded while waiting\b")),
)

_A_ROUTE = re.compile(r"(?:GET|POST|PUT|PATCH|DELETE)\s+(/[^\s\"'`;,)\]]+)|https?://[^\s\"'`]+?(/[^\s\"'`?]+)")


def _the_first_failing_layer(text: str) -> str:
    """The name of the layer this failure text meets, or "" when it names none.

    An assertion that a criterion's own expectation was not met is not a
    layer: two criteria failing their assertions are two symptoms, whatever
    else they share. A connection nobody accepted, a status nobody served,
    a wait that ran out - those fail many criteria from one cause.
    """
    text = str(text or "")
    for name, pattern in _FAILING_LAYERS:
        if pattern.search(text):
            return name
    return ""


def _the_text_of_a_defect(item: Any) -> str:
    return " ".join(
        str(getattr(item, name, "") or "")
        for name in ("description", "actual_behavior", "reproduction_steps")
    )


def _share_a_failing_surface(one: Any, other: Any) -> bool:
    """Whether two defects fail at one surface: a file in common, or a route in common."""
    files = {PurePosixPath(str(f)).name.lower() for f in getattr(one, "affected_files", None) or []}
    theirs = {PurePosixPath(str(f)).name.lower() for f in getattr(other, "affected_files", None) or []}
    if files & theirs:
        return True
    mine = {m for groups in _A_ROUTE.findall(_the_text_of_a_defect(one)) for m in groups if m}
    theirs = {m for groups in _A_ROUTE.findall(_the_text_of_a_defect(other)) for m in groups if m}
    return bool(mine & theirs)


#: First failing layers every request meets, whatever the route.
_WHOLE_PRODUCT_LAYERS = frozenset({"connection-refused", "unauthorized", "control-never-shown"})


#: Criteria failing the same way on the same page before they are one cause.
SAME_FAILURE_BEFORE_ONE_CAUSE = 3

_A_NUMBER = re.compile(r"\d+")
#: What a test typed into a field, in a page snapshot: each test types its own.
_A_FIELD_S_VALUE = re.compile(r'((?:textbox|searchbox|combobox|spinbutton) "[^"]*"):.*')


def _the_failure_as_met(item: Any) -> str:
    """The failure lines and the page a criterion failed on, with numbers taken out; or "".

    An assertion is a symptom, not a layer (`_the_first_failing_layer`) - but
    the same assertion failing on the same page, across many criteria, is
    the step they all pass through. Measured live: eight criteria each
    failed `expect(page).toHaveURL(expected)` on one sign-in page showing
    "Login failed", and went to eight fixers one by one.
    """
    from app.graph.acceptance_nodes import THE_PAGE_WHEN_IT_FAILED

    actual = str(getattr(item, "actual_behavior", "") or "")
    head, found, page = actual.partition(THE_PAGE_WHEN_IT_FAILED)
    if not found or not page.strip():
        return ""
    lines = sorted({part.split(": ", 1)[-1].strip() for part in head.split("; ") if part.strip()})
    page = _A_FIELD_S_VALUE.sub(r"\1", page.strip())
    return _A_NUMBER.sub("#", " | ".join(lines) + "\n" + page) if lines else ""


_A_CRITERION_DEFECT = re.compile(r"^\[((?:AC|CR)-\d+)\] (.*)$", re.S)


def _the_failing_tests_it_names(item: Any, criteria: dict[str, Any]) -> frozenset[str]:
    """The failing tests a defect is about: its measured evidence first (deep review 2026-11-18, item 1.1), else the
    tests of the criterion its description names in the suite's result; empty when neither says."""
    tests = frozenset(
        " ".join(str(record.get("test")).split()) for record in getattr(item, "evidence", None) or ()
        if isinstance(record, dict) and record.get("test")
    )
    if tests:
        return tests
    found = _A_CRITERION_DEFECT.match(str(getattr(item, "description", "") or ""))
    return frozenset(
        " ".join(str(t.get("name")).split()) for t in ((criteria.get(found.group(1)) or {}).get("tests") or [])
        if t.get("outcome") == "failed"
    ) if found else frozenset()


def _one_defect_per_failing_tests(reported: list[Any], result: dict[str, Any]) -> list[Any]:
    """`reported` with defects for criteria whose failing tests are exactly the same set merged, in order.

    The same failing tests decide every criterion they carry, so one fixer settles them all. Measured on one run:
    two criteria carried by one failing test had two fixers, about 40 and 45 minutes, both left open. The set is read
    from what the round measured (`evidence`) where the defect carries it, and from the suite's result by the
    criterion its description names where it does not.
    """
    criteria = (result or {}).get("criteria") or {}
    if len(reported) < 2:
        return list(reported)
    first_with: dict[frozenset[str], Any] = {}
    merged: list[Any] = []
    for item in reported:
        failing = _the_failing_tests_it_names(item, criteria)
        lead = first_with.get(failing) if failing else None
        if lead is None:
            if failing:
                first_with[failing] = item
            merged.append(item)
            continue
        found = _A_CRITERION_DEFECT.match(str(getattr(item, "description", "") or ""))
        lead_found = _A_CRITERION_DEFECT.match(str(getattr(lead, "description", "") or ""))
        if lead_found and found:
            lead.description = f"[{lead_found.group(1)}][{found.group(1)}] {lead_found.group(2)}"
        else:
            lead.description = (f"{lead.description}{SAME_PROBLEM_ELSEWHERE}- [{getattr(item, 'source', '') or 'reported'}] "
                                f"{' '.join(str(getattr(item, 'description', '')).split())[:400]}")
        lead.expected_behavior = f"{getattr(lead, 'expected_behavior', '')}; {getattr(item, 'expected_behavior', '')}".strip("; ")
        if getattr(item, "evidence", None) or getattr(lead, "evidence", None):
            lead.evidence = cause.merged_evidence((lead, item))
    return merged


def _one_defect_per_root_error(reported: list[Any]) -> list[Any]:
    """`reported` with the defects that fail at one layer behind one cause merged, in order.

    One run queued 13 defects from one root cause - every acceptance
    criterion failing behind a server that did not serve - and the fixers
    worked them one by one while the cause was one thing (Initiative L.1).
    Bundling by identical description (`_one_defect_per_cause`) cannot see
    it: the criteria share no words but the layer they fail at.

    A layer the whole product meets - three defects or more failing at it,
    whatever their surfaces - is one root cause and clusters wholesale: one
    auth middleware behind every API criterion, one server behind every
    page. A layer two criteria meet clusters only when they share a failing
    surface, so two independently missing routes stay two repairs. The
    merged defect keeps the first member's place and owner and carries every
    member's failure as evidence, all of their files, and the worst severity
    among them - the same shape as the identical-description merge beside it.
    """
    if len(reported) < 2:
        return list(reported)
    layers: dict[str, list[int]] = {}
    met: dict[str, list[int]] = {}
    for index, item in enumerate(reported):
        layer = _the_first_failing_layer(_the_text_of_a_defect(item))
        if layer:
            layers.setdefault(layer, []).append(index)
        elif _the_failure_as_met(item):
            met.setdefault(_the_failure_as_met(item), []).append(index)
    met = {k: v for k, v in met.items() if len(v) >= SAME_FAILURE_BEFORE_ONE_CAUSE}
    if not layers and not met:
        return list(reported)

    parent = list(range(len(reported)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for layer, indices in layers.items():
        # Only a layer the whole product sits behind is merged wholesale: a
        # connection nobody accepted (the server did not start, or served the
        # scaffold's stub) and a 401 on every request (one auth middleware).
        # A 404, 500 or timeout can have as many causes as routes, so it
        # clusters only when the defects share a failing surface.
        if layer in _WHOLE_PRODUCT_LAYERS and len(indices) >= 3:
            for other in indices[1:]:
                if root(other) != root(indices[0]):
                    parent[root(other)] = root(indices[0])
        elif len(indices) == 2:
            i, j = indices
            if root(i) != root(j) and _share_a_failing_surface(reported[i], reported[j]):
                parent[root(j)] = root(i)
    for indices in met.values():
        for other in indices[1:]:
            if root(other) != root(indices[0]):
                parent[root(other)] = root(indices[0])

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
        layer = _the_first_failing_layer(_the_text_of_a_defect(item)) or "the same failure on the same page"
        files = list(dict.fromkeys(
            str(f) for member in (item, *others) for f in getattr(member, "affected_files", None) or []
        ))
        severity = min(
            (str(getattr(member, "severity", "major") or "major") for member in (item, *others)),
            key=lambda value: _SEVERITY_RANK.get(value, 1),
        )
        also = "\n".join(
            f"- {' '.join(str(other.description).split())[:400]}"
            for other in others
        )
        merged.append(item.model_copy(update={
            "actual_behavior": _with_a_stopped_service_s_report(item, others),
            "description": (
                f"{item.description}\n\n{len(others)} other criteria meet the same first failure "
                f"({layer}); one cause is behind them, so one repair answers all of them:\n{also}"
            ),
            "affected_files": files,
            "severity": severity,
            **cause.as_merged(item, others),
        }))
        logger.warning(
            "%d defects fail at one layer (%s); one fixer gets them all: %s",
            len(group), layer, " ".join(str(item.description).split())[:100],
        )
    return merged


#: A workspace path written in a finding: `notes-api/package.json`, `notes-api/test/notes.test.ts`.
_A_PATH_IN_A_FINDING = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.(?:json|[cm]?[jt]sx?|py|toml|cfg|ya?ml))(?![\w/])")


def _the_workspace_files_named(root: str | None, text: str, most: int = 6) -> list[str]:
    """The files `text` names that exist in the workspace at `root`, in the order named; [] without a root."""
    if not root:
        return []
    found: list[str] = []
    for name in _A_PATH_IN_A_FINDING.findall(str(text or "")):
        if name not in found and (Path(root) / name).is_file():
            found.append(name)
        if len(found) >= most:
            break
    return found


def _proven_problems_the_round_left_out(
    proven: list[str], reported: list[Any], milestone: Any, state_root: str | None = None
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
        # The files it names are the fix's to change together: a fix given none changed one side and broke the other.
        affected = _the_workspace_files_named(state_root, problem)
        try:
            left_out.append(ReportedDefect(
                description=problem,
                severity="major",
                reproduction_steps="Read the files it names; this was decided by comparing them.",
                expected_behavior="The two files agree.",
                actual_behavior=problem,
                affected_files=affected,
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
    """The specification's interface design, for a task that builds the interface - its role's, or one of its files
    is the interface's (`file_domains`, SK.1); else []."""
    if str(getattr(task, "specialist_role", "") or "") != "ui_ux":
        from app.analysis.file_domains import domains_of_files

        if "interface" not in domains_of_files(getattr(task, "files", None) or []):
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


def _the_review_s_findings_are_open(state: Any) -> bool:
    """Whether the architecture review asks for changes the architect has not yet made.

    A review's findings are applied once. Measured live: after a review-driven
    revision the architect's own checks sent it back for one section, and the
    repair pass was handed the review's findings again beside "return only
    `specialist_advice_decisions`" - it rewrote ten sections a second time, four
    minutes of model time, where the same repair with nothing else asked had
    rewritten one. A later review raises the revision count, so its findings
    are open again.
    """
    review = state.get("architecture_review")
    if review is None or getattr(review, "status", None) != "changes_required":
        return False
    return state.get("architecture_review_applied") != state.get("architecture_revision_count", 0)


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
    if _the_review_s_findings_are_open(state):
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

    Read from the run's record at each decision, not only from the policy the run
    started with (plan WS.3): the owner can switch a review on or off while the run
    is live (`PUT /runs/{id}/review-policy`), and the next gate the run reaches
    follows the change. Outside a recorded run, the state's policy decides.
    """
    live = _the_live_review_policy()
    if live is not None:
        return bool(live.get(review_point, False))
    return bool((state.get("review_policy") or {}).get(review_point, False))


def _the_live_review_policy() -> dict[str, bool] | None:
    """The review policy on this call's run record now; None when the call has no recorded run. Never raises."""
    from app.observability.log_context import current_run

    run_id, _stage = current_run()
    if not run_id:
        return None
    try:
        from app.server.run_store import RunStore

        record = RunStore.shared().load(str(run_id))
    except Exception:  # noqa: BLE001 - no store reachable: the policy the run started with decides
        return None
    if record is None:
        return None
    policy = getattr(record, "review_policy", None)
    return dict(policy) if isinstance(policy, dict) else None


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


def _the_product_starts_now(root: str, defect: Any) -> str:
    """Why a "the product does not start" defect is resolved by the suite's last run, or "".

    The suite reached the product: some test ran against it, and no start
    failure was recorded. A start defect names no criterion and no unit test,
    so nothing else closes it. Measured on one gate run: round 1's suite
    passed 47 of 62 tests, and round 0's start defect stayed open - its fixer
    spent 20 minutes on it and left it open because the unit tests, which say
    nothing about the start, failed for another reason.
    """
    try:
        from app.acceptance import suite as acceptance_suite
        from app.graph.acceptance_nodes import THE_PRODUCT_DOES_NOT_START

        if not str(getattr(defect, "description", "") or "").startswith(THE_PRODUCT_DOES_NOT_START):
            return ""
        last = acceptance_suite.last_result(root)
        reached = int(last.get("passed") or 0) + int(last.get("failed") or 0)
        if str(last.get("problem") or "").strip() or reached <= 0:
            return ""
        return f"the product starts: the suite's last run reached it ({last.get('passed') or 0} of {reached} tests passed)"
    except Exception as error:  # noqa: BLE001 - a check that cannot answer says nothing
        degraded("probe.product_starts", error)
        return ""


def _resolved_by_a_measurement(state: Any, defect: Any, *, measured_since: bool = True) -> tuple[str, str]:
    """(what proves it, why it is resolved) for a defect a measurement shows resolved; else ("", "")."""
    if mutation_guided.is_a_finding(defect):
        # A test an earlier fix wrote may already notice this change (`mutation_guided.what_settles_it` shows a
        # fixer the others in its file). Measured as the fix of it would be: two unit runs, not a fix stage. Only
        # before a fixer is sent: a finding the round's own probe just raised is unnoticed by definition.
        if measured_since and mutation_guided.settled(state["repository"].root_path, defect):
            return "the unit tests", "a unit test already fails with this change and passes without it"
        return "", ""
    regressed = _a_regressed_test_passing_since(state, defect)
    if regressed:
        return regressed, f"{regressed} passes again"
    started = _the_product_starts_now(state["repository"].root_path, defect)
    if started:
        return "the locked acceptance suite's run", started
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
        from app.acceptance import unstable

        # A stored measurement closes a defect only while the product is as the suite measured it. Found in a code
        # review: `ci.revert_to` puts the tree back, but the suite's saved result is git-ignored and survives it, so a
        # reverted fix's green run closed another defect without a fixer and the next round raised it again. A
        # product that changed since goes to the re-measure below, which reads the product as it is.
        stale = acceptance_suite.is_locked(root) and not unstable.unchanged_since_the_suite_measured(root)
        resolved = [] if stale else acceptance_nodes.passing_since_reported(state, list(defect.failing_criteria or []))
        proof, why = ("", "") if resolved or stale else _resolved_by_a_measurement(state, defect)
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
                # Nothing stored can settle it, and the queue this defect came
                # from may be an hour old and many fixes deep: re-measure its
                # own tests now, at dispatch. Seconds of probe against a fixer
                # stage of minutes, and a green probe closes the defect with
                # no model call at all. A probe that cannot answer (None)
                # dispatches the fixer exactly as before (Initiative L.3).
                # Taken before the probe: a product keeping its store in a
                # committed file is rewritten by the probe itself, and read
                # after it the product had always "changed".
                unchanged = unstable.unchanged_since_the_suite_measured(root)
                if _the_defect_s_tests_pass(Path(root), defect):
                    # Passing alone on the very product the suite measured it
                    # failing on is not a fix: the tests depend on order or on
                    # another test's data. Held as a dispute while one may be
                    # (`app.acceptance.unstable`).
                    from app.acceptance.junit import tags_in

                    criteria = [t for t in tags_in(str(defect.description or "")) if t.startswith(("AC-", "CR-"))]
                    if criteria and unchanged and _a_dispute_may_be_held_now(state):
                        from app.observability import defect_ledger

                        logger.warning("Defect '%s' passes alone and fails in the suite on the same product: "
                                       "its tests are unstable; the QA lead judges them", defect.description[:80])
                        defect_ledger.note(
                            "left open", f"defect_fix_{state.get('test_round', 0)}_{defect_index}",
                            defect=defect, round_=state.get("test_round", 0), index=defect_index,
                            detail="its own tests pass alone and fail in the whole suite on the same product: unstable",
                            sprint=state.get("current_sprint_index", 0),
                        )
                        return _handing_on(
                            stage="acceptance_dispute", dispute_returns_to="test_and_triage",
                            defect_cursor=defect_index + 1, fix_base_commit="",
                            dispute_reason=unstable.reason(criteria),
                        )
                    logger.warning(
                        "Defect '%s' is already fixed: its own tests pass in a re-measure taken at "
                        "dispatch; closed without a fixer", defect.description[:80],
                    )
                    from app.observability import defect_ledger

                    defect_ledger.note(
                        "closed without a fixer", f"defect_fix_{state.get('test_round', 0)}_{defect_index}",
                        defect=defect, round_=state.get("test_round", 0), index=defect_index,
                        detail="its own tests passed in a re-measure taken at dispatch",
                        sprint=state.get("current_sprint_index", 0),
                    )
                    return _handing_on(
                        stage="defect_remediation",
                        defect_cursor=defect_index + 1,
                        fix_base_commit="",
                        remediation=mark_defect_fixed(
                            cycle, defect_index,
                            regression_test="a re-measure of its own tests at dispatch",
                            verified_by="the harness's probe before a fixer was spawned",
                            resolution=(
                                "Already fixed when it came up for dispatch: its own tests "
                                "passed in a re-measure taken now."
                            ),
                        ),
                    )
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
    except Exception as error:  # noqa: BLE001 - a defect not closed here goes to a fixer as before
        degraded("measure.earlier_fix_resolved", error)
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
    except Exception as error:  # noqa: BLE001
        degraded("measure.round_closes_defects", error)
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


#: Defects a fixer is shown beside its own, at most: fixers handed more fixed less.
MOST_BUNDLED_DEFECTS = 2

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
    # A mutation finding names no file: the open ones in its file, with `MUTATION_GAPS_BUNDLED` on, each settled by the
    # harness's own check after the fix (`_a_mutation_finding_settled`).
    from app.graph import mutation_gaps_bundled

    gaps = mutation_gaps_bundled.bundled_with(cycle, defect_index, MOST_BUNDLED_DEFECTS)
    if gaps:
        return gaps
    # Only defects that share a file with this one, and at most
    # `MOST_BUNDLED_DEFECTS` of them, most files in common first. Every open
    # defect of the same owner was bundled, and over every recorded run a fixer
    # handed one defect fixed it 64% of the time in a median 18k output tokens,
    # one handed four or more fixed 26% in 73k, with 62% of those stages cut off
    # at the reply limit against 11%. Acceptance defects arrive one per root
    # error, so a bundle mostly joined unrelated causes; and a defect an earlier
    # fix resolved is closed by measurement whether or not it was bundled.
    mine = {str(name).strip() for name in defect.affected_files or [] if str(name).strip()}
    related = [
        (len(mine & {str(name).strip() for name in d.affected_files or []}), pos, d)
        for pos, d in enumerate(cycle.defects[defect_index + 1:], start=defect_index + 1)
        if d.status == "open" and d.owner == defect.owner and _a_measurement_can_close(d)
    ]
    shared = sorted((r for r in related if r[0] > 0), key=lambda r: (-r[0], r[1]))[:MOST_BUNDLED_DEFECTS]
    return [(pos, d) for _, pos, d in sorted(shared, key=lambda r: r[1])]


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


def _the_specification_for_the_fix(state: Any, defect: Any, co_defects: list[tuple[int, Any]]) -> str:
    """The specification's entries for a defect's files and criteria, as a work order is given them.

    A fix is built by the faster model too, and was handed none of it.
    Measured on one run: the specification gave the store's load rule as
    "nextId = max(stored nextId, max(existing id)+1)" and the route
    handlers' body parsing inside a try/catch; the builder wrote neither, and
    the fixers sent to repair both were shown only the defect.
    """
    from types import SimpleNamespace

    from app.acceptance.junit import tags_in
    from app.agents.specialists import specification_for_the_work_order

    named = [*(defect.affected_files or [])]
    for _, other in co_defects:
        named.extend(other.affected_files or [])
    # A failing criterion names no file; the specification's tests name it.
    named.extend(t for t in tags_in(str(defect.description or "")) if t.startswith(("AC-", "CR-")))
    if not named:
        return ""
    return "\n" + specification_for_the_work_order(
        state.get("technical_specification"), SimpleNamespace(files=list(dict.fromkeys(named)), interfaces=[]),
    )


def _the_fixes_to_keep_for(state: Any, defect: Any) -> str:
    """The earlier fixes a rewrite of `defect` must keep, as the section a fix stage is shown; "" for none. Never raises."""
    try:
        from app.agents.specialists import fixes_to_keep_section
        from app.sprint import record as sprint_record

        return fixes_to_keep_section(sprint_record.fixes_to_keep(
            list(state.get("sprint_attempts") or []),
            files=[str(f) for f in getattr(defect, "affected_files", None) or []],
            role=str(getattr(defect, "owner", "") or ""),
        ))
    except Exception:  # noqa: BLE001 - a rewrite asked without them, as before
        return ""


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
        from app.acceptance import sprint_scope
        from app.graph import acceptance_nodes

        root = state["repository"].root_path
        sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
        index = int(state.get("current_sprint_index", 0) or 0)
        if not sprints or index >= len(sprints):
            return ""
        if acceptance_nodes.record_the_sprint_scope(state) is None:
            return ""
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


def _defects_only_about_deferred(reported: list[Any], root: str | Path) -> tuple[list[Any], list[Any]]:
    """(the reported defects a fix can close, those naming only criteria the suite has deferred). Never raises.

    A deferred criterion is no fix stage's in this run: its locked tests cannot pass, or a later sprint builds it.
    Measured on one run: AC-19 was deferred with its repairs spent, but the round's checks named only one of its
    four tests as unable to pass, so the defect about all four went on to fixers; one fix broke 37 tests and was
    reverted, and the next round raised it again.
    """
    try:
        from app.acceptance import suite as _suite

        deferred = sorted((_suite.deferred(root) or {}).keys())
    except Exception:  # noqa: BLE001 - the round's defects stand
        return reported, []
    return _defects_only_about(reported, deferred) if deferred else (reported, [])


def _defects_only_about(
    reported: list[Any], criteria: list[str], root: str | Path | None = None,
) -> tuple[list[Any], list[Any]]:
    """(the reported defects a fix can close, those naming only `criteria` or only the locked suite's files).

    `criteria` are those whose locked tests cannot pass and may not be
    repaired again (`acceptance_nodes.beyond_repair`): a defect about them
    alone has nothing a fix stage can change. Nor has the testing role's
    finding that names only the locked suite's own files: measured on one run,
    "Acceptance test all_ops.spec.js uses fetch and expects listRes.status()"
    named no criterion, and two fix stages each answered that the locked suite
    was wrong and changed nothing.
    """
    if not criteria:
        return reported, []
    from app.acceptance.junit import tags_in

    suite_names: set[str] = set()
    if root is not None:
        try:
            from app.acceptance import suite as _suite

            suite_names = {path.name for path in _suite.suite_files(root)}
        except Exception:  # noqa: BLE001 - only the criteria decide, as before
            suite_names = set()
    kept: list[Any] = []
    set_aside: list[Any] = []
    for item in reported:
        text = " ".join(
            str(getattr(item, name, "") or "")
            for name in ("description", "reproduction_steps", "expected_behavior", "actual_behavior")
        )
        named = {tag for tag in tags_in(text) if tag.startswith("AC-")}
        files = {Path(str(f)).name for f in getattr(item, "affected_files", None) or () if str(f).strip()}
        about_the_suite_alone = (
            bool(suite_names) and "testing" in str(getattr(item, "owner", "") or "").lower()
            and any(name in text for name in suite_names) and files <= suite_names
            and not (named - set(criteria))
        )
        (set_aside if (named and named <= set(criteria)) or about_the_suite_alone else kept).append(item)
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
    except Exception as error:  # noqa: BLE001 - the round's report as written stands
        degraded("scope_check.defects_a_later_sprint_builds", error)
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
    except Exception as error:  # noqa: BLE001 - the review as written stands
        degraded("review_check.command_record", error)
        return review


#: A criterion or test case a finding can be held to: `AC-12`, `TC-AC-3-01`.
_A_MEASURE_NAMED = re.compile(r"\b(?:AC|TC)-[A-Z0-9]+(?:-[A-Z0-9]+)*\b", re.I)


def _findings_no_measure_holds(review: Any, repo_root: str) -> Any:
    """`review` with each gating finding that names no criterion or test case made minor, while every test passes.

    A send-back costs a full round - one run spent 35 minutes a round, twice,
    on a sprint whose every acceptance and unit test passed, over findings
    about how a test was worded. With every measure green, a finding that
    cannot name the criterion or test case it says is not met is a risk to
    record, not a reason to rebuild. Kept in the review and the Sprint Record.
    """
    try:
        tests = _where_each_test_command_stands(repo_root)
        if not tests or not all(tests.values()):
            return review
        findings, moved = [], 0
        for finding in getattr(review, "findings", None) or []:
            text = " ".join(str(getattr(finding, key, "") or "") for key in (
                "description", "required_remediation", "evidence"))
            if _severity_gates(getattr(finding, "severity", "")) and not _A_MEASURE_NAMED.search(text):
                moved += 1
                finding = finding.model_copy(update={
                    "severity": "minor",
                    "description": (
                        "Every test command's most recent run passed and this names no criterion or test "
                        f"case it holds the sprint to, so it is recorded as a risk: {finding.description}"
                    ),
                })
            findings.append(finding)
        if not moved:
            return review
        logger.warning(
            "Milestone review raised %d gating finding(s) naming no criterion or test case while every "
            "test passes; recorded as minor", moved,
        )
        return review.model_copy(update={"findings": findings})
    except Exception as error:  # noqa: BLE001 - the review as written stands
        degraded("review_check.no_measure_holds", error)
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
    except Exception as error:  # noqa: BLE001 - the review as written stands
        degraded("review_check.dependency_check", error)
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
    except Exception as error:  # noqa: BLE001 - the review as written stands
        degraded("review_check.security_grade", error)
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
    except Exception as error:  # noqa: BLE001 - the review as written stands
        degraded("review_check.server_only_the_tests_start", error)
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
    except Exception as error:  # noqa: BLE001 - never fail a finished run over this gate
        degraded("gate.brief_requirements_built", error)
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
        elif index == 0 and not reported:
            # The first sprint with nothing reported: everything there is new
            # to it - most often code a setup stage wrote before any sprint
            # planned work, which a review must still read.
            reported |= set(_the_whole_product(root))
    except Exception:  # noqa: BLE001 - evidence is best-effort, never fatal
        logger.warning("Could not read what this sprint changed", exc_info=True)
    return sorted(reported)


def _the_whole_product(root: str) -> list[str]:
    """Every product file in the workspace: no workflow document, no harness record, no dotfile."""
    from app.tools.repository import HARNESS_FILES, list_repository_files

    return [
        name for name in list_repository_files(root)
        if not name.startswith("docs/")
        and not any(part.startswith(".") for part in name.split("/"))
        and name.rsplit("/", 1)[-1] not in HARNESS_FILES
    ]


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
    except Exception as error:  # noqa: BLE001 - a gate that cannot read must not stop a run
        degraded("gate.suite_the_ledger_measured", error)
        return None


def _the_last_test_command(state: WorkflowGraphState) -> str:
    """The command of the last test run this sprint recorded in the execution ledger, as one string; "" if none."""
    try:
        recorded = [dict(entry) for entry in (state.get("sprint_attempts") or [])]
        since = max((str(entry.get("ended_at")) for entry in recorded if entry.get("ended_at")), default=None)
        entry = last_test_run(_the_ledger(state["repository"].root_path, 1000), since=since) or {}
        command = entry.get("command") or entry.get("argv") or ""
        return " ".join(str(part) for part in command) if isinstance(command, (list, tuple)) else str(command)
    except Exception:  # noqa: BLE001 - then the gate reads as before
        return ""


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
    # Another command's failing run beside a locked suite measured fully green is no reason to redraft: measured on
    # three runs, the last ledger run was a unit-test or partial run (9 cases, 1 failed) while the suite stood at 18 of
    # 18, and each sprint was sent back for a revision the owner's rule (LF.327) says a green sprint does not get; the
    # failures ship as a known issue (`release_with_failing_unit_tests`).
    from app.graph import settle_when_green

    if settle_when_green.enabled() and settle_when_green.the_locked_suite_is_green(state["repository"].root_path):
        last = str(_the_last_test_command(state) or "")
        acceptance = settle_when_green.the_acceptance_command(state["repository"].root_path)
        if acceptance and last and last != acceptance:
            logger.info("The ledger's last failing run was `%s`, not the locked suite, which is green; not sent back",
                        last[:120])
            return ""
    # Failing only where a later sprint builds: this sprint is measured by its own share of the suite.
    if settle_when_green.enabled() and settle_when_green.the_locked_suite_is_green_for_this_sprint(
            state["repository"].root_path):
        logger.info("The locked suite fails only tests of criteria a later sprint delivers; the sprint is not sent back")
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
        f" {getattr(finding, 'required_remediation', '')}"
    )
    return bool(named) and named <= kept


def _about_the_locked_suite_only(finding: Any, repo_root: str) -> bool:
    """Whether every file a finding names is in the locked acceptance suite, and it names one. Never raises.

    By path, not by name: a unit test may share a suite file's name.
    """
    try:
        from app.acceptance import suite

        if not suite.is_locked(repo_root):
            return False
        where = suite.directory(repo_root)
        if where is None:
            return False
        root = Path(repo_root).resolve()
        inside = where.resolve()
        named = [str(path).strip().lstrip("/") for path in getattr(finding, "affected_files", None) or [] if str(path).strip()]
        return bool(named) and all(inside in (root / path).resolve().parents for path in named)
    except Exception:  # noqa: BLE001 - not known to be the suite's
        return False


def _findings_about_the_locked_suite_made_minor(review: Any, repo_root: str) -> Any:
    """`review` with each gating finding whose files are all in the locked acceptance suite recorded as minor.

    No sprint may change the locked suite - only its own reopening does - so a revision asked for one cannot be made
    and the sprint goes back for work nobody may do. Measured on one run: every test passed, and the milestone review
    called a locked test vacuous (major); the lead's plan was sent back twice for a work order to change it. Kept in
    the review and the Sprint Record, so the release names it as a gap.
    """
    try:
        findings, moved = [], 0
        for finding in getattr(review, "findings", None) or []:
            if _severity_gates(getattr(finding, "severity", "")) and _about_the_locked_suite_only(finding, repo_root):
                moved += 1
                finding = finding.model_copy(update={
                    "severity": "minor",
                    "description": (
                        "The files this names are the locked acceptance suite, which no sprint may change; recorded "
                        f"as a gap in the suite, not a reason to send the sprint back: {finding.description}"
                    ),
                })
            findings.append(finding)
        if not moved:
            return review
        logger.warning("Milestone review raised %d gating finding(s) about the locked suite only; recorded as minor", moved)
        return review.model_copy(update={"findings": findings})
    except Exception:  # noqa: BLE001 - the review as written stands
        return review


def _findings_about_the_harness_s_files_made_minor(review: Any, repo_root: str) -> Any:
    """`review` with each gating finding whose files are all the harness's own recorded as minor. Never raises.

    No work order may change a file the harness keeps - `contract.enforce` puts it back before every run - so a
    revision asked for one cannot be made, and the sprint is sent back for work nobody may do. Measured on one run:
    the milestone review asked for signal handlers in the pack's kept start file `src/main.ts`. The security review
    leaves such findings out (`_without_findings_about_the_harness_s_files`); the milestone review keeps them, minor,
    because an emptied `changes_required` review is asked again.
    """
    try:
        findings, moved = [], 0
        for finding in getattr(review, "findings", None) or []:
            if _severity_gates(getattr(finding, "severity", "")) and _about_the_harness_s_files_only(finding, repo_root):
                moved += 1
                finding = finding.model_copy(update={
                    "severity": "minor",
                    "description": (
                        "The files this names are the harness's own, put back before every run, and no work order "
                        f"may change them; not a reason to send the sprint back: {finding.description}"
                    ),
                })
            findings.append(finding)
        if not moved:
            return review
        logger.warning("Milestone review raised %d gating finding(s) about the harness's own files; recorded as minor", moved)
        return review.model_copy(update={"findings": findings})
    except Exception:  # noqa: BLE001 - the review as written stands
        return review


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


def _criteria_the_suite_names(root: Any) -> set[str]:
    """Every criterion id a test in the locked suite's own files carries; empty when unreadable."""
    try:
        from app.acceptance import suite as acceptance_suite
        from app.acceptance.junit import tags_in

        return {
            tag for path in acceptance_suite.suite_files(root)
            for tag in tags_in(path.read_text(encoding="utf-8", errors="replace"))
        }
    except Exception:  # noqa: BLE001 - unknown: nothing is called missing on its account
        return set()


def criteria_past_the_cap(failing: list[tuple[str, str, str]], past_the_cap: list[str]) -> list[str]:
    """The criteria ids of the failing tests a dispute called wrong past the reclassification cap, sorted.

    `past_the_cap` holds the dispute's repair sentences ("`test_x` cannot pass for ..."), each naming its test in the
    backticks it opens with; a bare name is taken as it is. Measured live: matched as whole strings, they named no
    test, and nothing was deferred.
    """
    names = {(re.match(r"\s*`([^`]+)`", item) or re.match(r"(.*)", item)).group(1).strip() for item in past_the_cap}
    return sorted({cid for name, text, _ in failing if name in names for cid in re.findall(r"\b(?:AC|CR)-\d+", text)})


def past_the_cap_with_their_criteria(failing: list[tuple[str, str, str]], past_the_cap: list[str]) -> list[str]:
    """Each test past the cap as "[AC-n] `name` ...": its criteria's tags in front, its name in backticks.

    The deferral keeps the tests it was judged on by reading these tags; the dispute's own sentences carry none.
    Measured on one run: AC-7 and AC-11 were deferred with no test recorded against them, so the very next lock took
    the deferrals off as "a test now carries them" - the same broken tests - and the fixers were sent to them again.
    """
    tags = {name: " ".join(f"[{cid}]" for cid in dict.fromkeys(re.findall(r"\b(?:AC|CR)-\d+", text)))
            for name, text, _ in failing}
    lines = []
    for item in past_the_cap:
        name = (re.match(r"\s*`([^`]+)`", item) or re.match(r"(.*)", item)).group(1).strip()
        rest = item if item.lstrip().startswith("`") else f"`{name}`"
        lines.append(f"{tags.get(name, '')} {rest}".strip())
    return lines


def _the_locked_tests_still_failing(state: Any) -> list[tuple[str, str, str]]:
    """(test name, criterion, failure) for each locked test the last measurement shows failing."""
    from app.acceptance import suite as acceptance_suite

    try:
        root = state["repository"].root_path
        if not acceptance_suite.is_locked(root):
            return []
        saved = acceptance_suite.last_result(root) or {}
    except Exception as error:  # noqa: BLE001 - nothing readable, nothing to judge
        degraded("gate.locked_tests_still_failing", error)
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
    # A measurement in which no test reported at all - the product did not
    # start, a reverted fix left nothing measured - shows every criterion
    # "untested" while `ran` is true. Measured live: a dispute held 100 ms after
    # a fix was reverted told QA six due criteria had no test, against 25 tests
    # in the suite naming them, and QA rewrote the suite. Only a measurement
    # with results can show a test missing, and never one the suite names.
    reported = sum(int(saved.get(key) or 0) for key in ("passed", "failed", "skipped")) or sum(
        len(c.get("tests") or []) for c in (saved.get("criteria") or {}).values() if isinstance(c, dict)
    )
    named = _criteria_the_suite_names(root)
    for cid, criterion in (saved.get("criteria") or {}).items():
        if not isinstance(criterion, dict) or cid in deferred or cid not in due:
            continue
        status = str(criterion.get("status") or "")
        tests = criterion.get("tests") or []
        if status == "untested" or not tests:
            # Only a suite that ran can show a criterion has no test: when the
            # runner wrote no report, every criterion reads "untested", and
            # QA would be sent to add tests that are there.
            if not saved.get("ran") or not reported or cid in named:
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


def _this_attempt(state: Any, judging_the_last: bool = False) -> str:
    """The sprint and how many attempts at it have been recorded: "4:2" for sprint 5's third.

    `judging_the_last`: the key of the attempt that just failed, for a dispute held at its re-plan - the attempt is
    recorded by then, so the count is one past it. Without this, a re-plan dispute after attempt N and a dispute held
    during attempt N+1 shared one key: measured on one run, every fixer that blamed a locked test during the next two
    attempts found its attempt "already disputed", and fixers worked a right product for 283 more calls.

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
    return f"{index}:{max(0, len(attempts) - 1) if judging_the_last and attempts else len(attempts)}"


def _a_dispute_is_due(state: Any) -> bool:
    """Whether this re-plan of a failed attempt should first have its failing locked tests judged."""
    from app.graph.acceptance_nodes import may_repair

    if _the_last_failed_attempt_at_this_sprint(state) is None:
        return False
    if [c for c in state.get("revision_comments") or [] if str(c).strip()]:
        return False
    if _this_attempt(state, judging_the_last=True) in (state.get("disputed_sprints") or []):
        return False
    failing = _the_locked_tests_still_failing(state)
    return bool(failing) and may_repair(state, [f"`{name}`" for name, _, _ in failing])


#: The locked suite named as a whole: "the acceptance tests call ...", "the locked suite expects ...".
_THE_SUITE_AS_A_WHOLE = re.compile(r"\b(?:locked|acceptance)\s+(?:test|tests|suite|spec|specs)\b", re.I)


def _blames_a_locked_test(state: Any, blockers: list[str], changed_nothing: bool = False) -> bool:
    """Whether a fix stage's blockers name a file or a test of the locked acceptance suite. Never raises.

    By its test as well as its file: measured on a gate run, a fixer changed
    nothing and reported "test_ac7_persistence_after_restart has an unfixable
    typo" - a locked test signing in as the wrong account - and, its file not
    named, no dispute was held; the next round sent the same criterion to
    another fixer.
    """
    try:
        from app.acceptance import suite as acceptance_suite

        root = state["repository"].root_path
        if not acceptance_suite.is_locked(root):
            return False
        names = {path.name for path in acceptance_suite.suite_files(root)}
        for _, name in acceptance_suite.declared_tests(root):
            title = re.sub(r"\[[^\]]*\]$", "", str(name)).strip()
            # A plain word as a title (`describe('Accounts')`) is any sentence's
            # word: it blames the suite only with a tag or as a phrase.
            if title and (re.search(r"\b[A-Z]{2,}-\d+\b", title) or len(title.split()) >= 3 or "_" in title):
                names.add(title)
        text = " ".join(map(str, blockers or []))
        # A fix that changed nothing and says the acceptance tests are the trouble blames the suite though it names no
        # file or test: measured on one run, a dozen fixers each wrote "The acceptance tests call page.evaluate() with
        # fetch(...) before page.goto(...)", no dispute was held, and two rounds went to a right product.
        if changed_nothing and _THE_SUITE_AS_A_WHOLE.search(text):
            return True
        return any(name and re.search(rf"(?<![\w.]){re.escape(name)}(?![\w])", text) for name in names)
    except Exception:  # noqa: BLE001 - not blamed is how it was before
        return False


def _the_test_named(entry: str) -> str:
    """A test's own title from a revert's `acceptance: <file> › ... › <title>` entry."""
    return str(entry).rsplit(" › ", 1)[-1].strip()


def _a_dispute_may_be_held_now(state: Any, also: list[str] | None = None) -> bool:
    """Whether this attempt may have its failing locked tests judged before it ends.

    Measured on one run: sprint 4's locked responsive test had a logic error -
    it switched to the "Active" view and expected no items, though the item it
    had added was active. Every fix stage in two rounds - three of them sent to
    defects already fixed - changed nothing and named that test as the reason,
    and each defect was left open. A dispute waited for the attempt to fail,
    which cost the attempt's remaining rounds first. Once per attempt, as at a
    re-plan, and only while the suite may still be repaired.
    """
    from app.graph.acceptance_nodes import may_repair

    if _this_attempt(state) in (state.get("disputed_sprints") or []):
        return False
    failing = _the_locked_tests_still_failing(state)
    # `also`: a passing locked test the dispute is about (two reverted fixes broke it). Measured on one run: every
    # fix of a DELETE criterion was reverted for breaking another criterion's test, five times, and no dispute was
    # held - the failing tests had been repaired already, the contested one never had.
    contested = [f"`{_the_test_named(name)}`" for name in also or []]
    return bool(failing) and may_repair(state, [*(f"`{name}`" for name, _, _ in failing), *contested])


#: What a reverted fix leaves on its defect's actual behaviour. See the
#: `broke` branch of `defect_remediation_node`.
_REVERTED_FOR = re.compile(r"A fix was tried and reverted, because it broke what passed before it: (.+?)\.(?:\n|$)")


#: Reverted fixes, each breaking one passing locked test, before that test stops reverting a fix alone: two, the
#: evidence a dispute is held on (`_a_locked_test_two_fixes_broke`). Counted within an attempt, which a re-plan starts
#: afresh: measured on one run, three never came in one attempt while the same test reverted eight fixes over four.
REVERTS_BEFORE_A_TEST_IS_CONTESTED = 2


def _a_contested_test_past_repair(state: Any, cycle: Any) -> str:
    """A passing locked test that two reverted fixes broke and the suite may no longer be repaired for; else "".

    Measured on one run: every fix of a DELETE criterion was reverted for breaking a test that asserted JSON on every
    response, a 204 included - eight times over four attempts - with the suite's repairs spent, so no dispute could
    judge it. Such a test no longer reverts, alone, a fix that makes other tests pass (`engineering.after_a_fix`).
    """
    try:
        from collections import Counter

        from app.graph.acceptance_nodes import may_repair

        counts: Counter[str] = Counter()
        for defect in getattr(cycle, "defects", None) or []:
            counts.update(_the_reverts_noted(str(getattr(defect, "actual_behavior", "") or ""))[1])
        name = next((n for n, c in counts.most_common() if c >= REVERTS_BEFORE_A_TEST_IS_CONTESTED), "")
        if not name or may_repair(state, [f"`{_the_test_named(name)}`"]):
            return ""
        return name
    except Exception as error:  # noqa: BLE001 - the revert gate stands as it was
        degraded("gate.contested_test_past_repair", error)
        return ""


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
        counts.update(_the_reverts_noted(str(getattr(defect, "actual_behavior", "") or ""))[1])
    return next((name for name, count in counts.most_common() if count >= 2), "")


def _with_the_api(request: dict, state: Any) -> dict:
    """A request with the product's API, as the specification decides it, at its end. Never raises."""
    try:
        from app.acceptance.api_reference import api_reference

        reference = api_reference(state.get("technical_specification"), getattr(state.get("document"), "text", "") or "")
        if reference:
            request["messages"][-1]["content"] += "\n\n" + reference
    except Exception:  # noqa: BLE001 - the request stands without it
        pass
    return request


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


def _no_review_has_read_the_code(state: Any) -> bool:
    """Whether the run has code and no security or milestone review has run on any of it yet."""
    if state.get("milestone_review") is not None or state.get("security_review") is not None:
        return False
    try:
        return _changes_any_code(_the_whole_product(state["repository"].root_path))
    except Exception as error:  # noqa: BLE001 - unknown: close the sprint as before
        degraded("gate.code_no_review_read", error)
        return False


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
    if _no_review_has_read_the_code(state):
        # Passing the suite is evidence, not a review. Measured on one run: a
        # setup stage wrote the whole product, this sprint was accepted without
        # new work, and no code, milestone or security review ever read it. The
        # sprint goes through the reviews instead, with a plan of no work
        # orders: a review that asks for changes sends it to the lead as any
        # review does.
        record_decision(
            state, accepted, point="sprint",
            question=f"Is sprint {index + 1} done?",
            options=["accept without new work", "review it before accepting"],
            decision="review it before accepting",
            rationale="Every criterion due already passes, but no review has read this code yet.\n" + why,
        )
        logger.info("Sprint %d needs no new work, but no review has read its code; reviewing it first", index + 1)
        from app.agents.technical_lead import MilestonePlanOutput

        return _handing_on(
            **accepted,
            stage="security_review",
            milestone_plan=MilestonePlanOutput(
                selected_sprint_goal=goal,
                # Context, not scope: a scope with no work order is refused as
                # a plan nobody builds, and nothing here is to be built.
                integration_notes=[
                    "No new work: every criterion due already passes. The code was written "
                    "before this sprint planned any, and no review has read it yet."
                ],
            ),
            specialist_outputs={},
            nothing_left_but_carried=None,
        )
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
        rationale=(
            "Nobody answered within the gate's time, so the run went on by itself."
            if decision.get("decided_by") == "timeout" else "Decided by the reviewer at the review gate."
        ),
        decided_by="timeout" if decision.get("decided_by") == "timeout" else "user",
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


def _the_revision_limit() -> int:
    """How many design revisions this run has: two in fast delivery, else `MAX_ARCHITECTURE_REVISIONS`.

    One helper for the escalation and every harness finding's guard (HR2.D.4): the guards compared with the full
    limit while fast delivery escalated at two, so a harness finding first raised on the last revision passed its
    guard and escalated unrevised.
    """
    return 2 if _fast_delivery() else MAX_ARCHITECTURE_REVISIONS


def _fast_delivery() -> bool:
    """Whether this deployment delivers fast (`app.delivery`).

    A function rather than the module: inside the graph builder `delivery`
    is `app.graph.delivery`, the sprint-evidence module, and a node that
    called `delivery.fast()` there failed on its first review.
    """
    from app import delivery

    return delivery.fast()


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

    from app.models.roles import plans_on_the_judgement_model

    #: The plan and the specification are what every other stage builds from;
    #: the judgement model writes them unless the owner turned that off. In
    #: fast delivery the specification and the reviews stay with it and the
    #: rest of planning - intake, comparison, stack, consultations, sprint
    #: plan, work orders, acceptance tests - is the build model's: they turn
    #: the brief and the specification into records. See `app.delivery`.
    planning_model = judgement_model if plans_on_the_judgement_model() and not _fast_delivery() else model

    # Fast delivery builds and fixes without reasoning: the specification has
    # decided what each stage writes. See `app.delivery`.
    building_model = model
    if _fast_delivery() and (model is None or isinstance(model, BaseChatModel)):
        try:
            from app.agents.thinking import without_reasoning
            from app.models import build_default_chat_model as _default_model

            building_model = without_reasoning(model if model is not None else _default_model())
        except Exception:  # noqa: BLE001 - the build model reasons as configured
            logger.warning("Could not switch reasoning off for building; it runs as configured", exc_info=True)
            building_model = model
    # In every delivery mode, a stage on the judgement model gathers on the
    # build model with reasoning off and writes on the judgement model: what
    # it writes is the judgement model's as before. See `app.agents.gathering`.
    if isinstance(judgement_model, BaseChatModel) and judgement_model is not model:
        try:
            from app.agents.gathering import gather_with
            from app.agents.thinking import without_reasoning
            from app.models import build_default_chat_model as _gathering_default

            gather_with(judgement_model, building_model if building_model is not model
                        else without_reasoning(model if model is not None else _gathering_default()))
        except Exception:  # noqa: BLE001 - the judgement model gathers for itself
            logger.warning("Could not set up gathering on the build model", exc_info=True)

    # What every node is built with. The nodes in `app.graph.nodes` take it as
    # their last argument (`_a_node`), and so do the stages kept in their own
    # modules (`_a_stage`).
    from app.graph.context import GraphContext
    from app.graph.nodes import (
        building, closing, fixes, gates, milestone, planning, reviews, specification, triage,
    )

    ctx = GraphContext(
        model=model,
        judgement_model=judgement_model,
        planning_model=planning_model,
        building_model=building_model,
        checkpointer=shared_checkpointer,
        repo_root=repo_root,
        allow_subdirectories=allow_subdirectories,
    )

    # The stages between an approved architecture and the sprint plan, and the
    # QA lead's review. See `app.graph.acceptance_nodes`.
    from app.graph import acceptance_nodes

    # Shipping: the release gate and change requests. See `app.graph.delivery`.
    from app.graph import delivery

    # CI and code review between a batch and its test rounds. See
    # `app.graph.engineering`.
    from app.graph import engineering

    # The last rung of the ladder. See `app.graph.escalation`.
    from app.graph import escalation as stuck

    graph = StateGraph(WorkflowGraphState)
    # Every stage snapshots the workspace as it starts, so a run can be
    # rewound to it with its files as they were (`rewind_to`).
    _add_node = graph.add_node

    def add_node(name: str, action: Any, **kwargs: Any) -> Any:
        return _add_node(name, _snapshotting(name, action), **kwargs)

    graph.add_node = add_node  # type: ignore[method-assign]
    from langgraph.types import RetryPolicy, default_retry_on

    from app.models.quota import out_of_quota

    # A provider out of quota refuses every attempt alike; the runner parks
    # the run for a person instead (`runner._explain_failure`).
    agent_retry_policy = RetryPolicy(
        initial_interval=2.0,
        backoff_factor=2.0,
        max_interval=30.0,
        max_attempts=3,
        retry_on=lambda error: not out_of_quota(error) and default_retry_on(error),
    )

    graph.add_node("product_manager", _a_node(planning.product_manager_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("user_review_product_intake", gates.user_review_product_intake_node)
    graph.add_node("tools_models", _a_node(planning.tools_models_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("stack_selector", _a_node(planning.stack_selector_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("specialist_consultation", _a_node(planning.specialist_consultation_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("principal_architect", _a_node(specification.principal_architect_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("architecture_review", _a_node(specification.architecture_review_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("user_review_specification", gates.user_review_specification_node)
    graph.add_node("scaffold", _a_stage(acceptance_nodes, "scaffold", ctx), retry_policy=agent_retry_policy)
    graph.add_node("acceptance_author", _a_stage(acceptance_nodes, "acceptance_author", ctx), retry_policy=agent_retry_policy)
    graph.add_node("acceptance_review", _a_stage(acceptance_nodes, "acceptance_review", ctx), retry_policy=agent_retry_policy)
    graph.add_node("user_review_acceptance", gates.user_review_acceptance_node)
    graph.add_node("scrum_master", _a_node(planning.scrum_master_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("user_review_sprint_plan", gates.user_review_sprint_plan_node)
    graph.add_node("sprint_acceptance", _a_stage(acceptance_nodes, "sprint_acceptance", ctx))
    graph.add_node("technical_lead", _a_node(building.technical_lead_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("specialist_dispatch", _a_node(building.specialist_dispatch_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("specialist_worker", _a_node(building.specialist_worker_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("specialist_gather", building.specialist_gather_node)
    # A static edge, not the shared router: every `Send` branch converges
    # here and LangGraph runs the target once for the whole superstep,
    # which is what gives the fan-out a single writer for `stage`.
    graph.add_edge("specialist_worker", "specialist_gather")
    graph.add_node("ci_gate", _a_stage(engineering, "ci_gate", ctx))
    graph.add_node("code_review", _a_stage(engineering, "code_review", ctx), retry_policy=agent_retry_policy)
    graph.add_node("test_and_triage", _a_node(triage.test_and_triage_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("defect_remediation", _a_node(fixes.defect_remediation_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("defect_fix_worker", _a_node(fixes.defect_fix_worker_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("defect_fix_gather", fixes.defect_fix_gather_node)
    # A static edge, as for `specialist_worker`: one writer of `stage` per batch.
    graph.add_edge("defect_fix_worker", "defect_fix_gather")
    graph.add_node("security_review", _a_node(reviews.security_review_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("advice_review", _a_node(reviews.advice_review_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("review_worker", _a_node(reviews.review_worker_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("review_gather", reviews.review_gather_node)
    graph.add_edge("review_worker", "review_gather")
    graph.add_node("acceptance_dispute", _a_node(reviews.acceptance_dispute_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("milestone_review", _a_node(milestone.milestone_review_node, ctx), retry_policy=agent_retry_policy)
    graph.add_node("user_review_sprint", gates.user_review_sprint_node)
    graph.add_node("sprint_advance", closing.sprint_advance_node)
    graph.add_node("change_request", _a_stage(delivery, "change_request", ctx))
    graph.add_node("escalation", _a_stage(stuck, "escalation", ctx))
    graph.add_node("user_review_escalation", gates.user_review_escalation_node)
    graph.add_node("escalation_accept", _a_stage(stuck, "accept", ctx))
    graph.add_node("escalation_retry", _a_stage(stuck, "retry", ctx))
    graph.add_node("release", _a_stage(delivery, "release", ctx))
    graph.add_node("user_review_release", gates.user_review_release_node)
    graph.add_node("complete", closing.complete_node)
    graph.add_node("failed", closing.failed_node)

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
        "user_review_sprint_plan",
        "sprint_acceptance",
        "technical_lead",
        "specialist_dispatch",
        "specialist_gather",
        "ci_gate",
        "code_review",
        "test_and_triage",
        "defect_remediation",
        "defect_fix_gather",
        "review_gather",
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

#: Nodes a run is never rewound to: the side-by-side workers and the steps that
#: gather them run only inside the stage that sent them, and the ends of a run
#: are not stages.
_NOT_A_REWIND_POINT = frozenset({"complete", "failed", "__start__", "__input__"})


def _not_a_stage_of_its_own(node: str) -> bool:
    return node in _NOT_A_REWIND_POINT or node.endswith(("_worker", "_gather"))


def _a_node(action: Any, ctx: Any) -> Any:
    """`action(state, config, ctx)` as a graph node of `(state, config)`.

    The node keeps the name and the annotations `action` has, so the graph,
    its snapshots (`_snapshotting`) and its traces see the same node as when it
    was a closure inside `build_workflow_graph`.
    """

    def node(state: Any, config: RunnableConfig) -> Any:
        return action(state, config, ctx)

    hints = getattr(action, "__annotations__", {})
    node.__annotations__ = {
        key: hints[key] for key in ("state", "config", "return") if key in hints
    }
    node.__name__ = getattr(action, "__name__", "node")
    node.__qualname__ = node.__name__
    node.__doc__ = getattr(action, "__doc__", None)
    return node


def _a_stage(module: Any, name: str, ctx: Any) -> Any:
    """`module.<name>(state, config, ctx)` as a graph node, the function looked up when the node runs.

    For the stages kept in their own modules (`acceptance_nodes`, `engineering`,
    `escalation`, `delivery`): looked up at each call, as the closures that
    wrapped them did, so a patch of the module's function reaches a graph built
    before it.
    """

    def node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        return getattr(module, name)(state, config, ctx)

    node.__name__ = f"{name}_node"
    node.__qualname__ = node.__name__
    return node


def _snapshotting(name: str, action: Any) -> Any:
    """`action`, after a snapshot of the workspace under its stage's name.

    Not for the side-by-side workers: several run at once, and a run is never
    rewound to one (`_not_a_stage_of_its_own`).
    """
    import inspect

    if _not_a_stage_of_its_own(name) or not callable(action):
        return action
    try:
        parameters = list(inspect.signature(action).parameters.values())
    except (TypeError, ValueError):
        return action
    takes_config = len(parameters) >= 2

    def node(state: Any, config: RunnableConfig) -> Any:
        root = _repository_root(state) if isinstance(state, dict) else None
        if root:
            try:
                from app.tools.version_control import is_repository, snapshot_workspace

                # The checkpoint this stage starts from: a rewind to it finds
                # this snapshot by that id, not by the clock (`rewind_to`).
                started_from = ((config or {}).get("configurable") or {}).get("checkpoint_map", {}).get("")
                if snapshot_workspace(root, name, started_from) is None and is_repository(root):
                    # A rewind to this point refuses: nothing holds its files.
                    degraded("workspace_snapshot", None, of=name)
            except Exception as error:  # noqa: BLE001 - a snapshot is never a reason to stop a stage
                degraded("workspace_snapshot", error, of=name)
        return action(state, config) if takes_config else action(state)

    if parameters and parameters[0].annotation is not inspect.Parameter.empty:
        node.__annotations__ = {"state": parameters[0].annotation, "config": RunnableConfig}
    node.__name__ = getattr(action, "__name__", name)
    return node


def _checkpoint_millis(snapshot: Any) -> int | None:
    created = getattr(snapshot, "created_at", None)
    if not created:
        return None
    try:
        return int(datetime.fromisoformat(str(created).replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


def rewind_points(graph: Any, thread_id: str) -> list[dict[str, Any]]:
    """Each stage this run started, oldest first, as a point it can be rewound to.

    One point per time a stage was entered: the checkpoint just before it ran.
    A stage entered again straight after itself (an approval answered, a retry)
    is the same point.
    """
    # One checkpoint at a time, kept as the few fields a point needs. Measured
    # on 2026-10-20: a run 11 hours long had thousands of checkpoints, and
    # holding every snapshot whole got the API's workers killed for memory
    # three times over - the rewind it was asked for could not be made.
    entries: list[tuple[str | None, bool, str, int | None, str]] = []
    for snapshot in graph.get_state_history(_run_config(thread_id, DEFAULT_RECURSION_LIMIT)):
        values = snapshot.values or {}
        entries.append((
            snapshot.next[0] if len(snapshot.next or ()) == 1 else None,
            bool(snapshot.next),
            snapshot.config["configurable"]["checkpoint_id"],
            int(values.get("current_sprint_index") or 0) + 1 if values.get("sprint_plan") else None,
            str(getattr(snapshot, "created_at", "") or ""),
        ))
        del snapshot, values
    points: list[dict[str, Any]] = []
    previous: str | None = None
    for node, has_next, checkpoint_id, sprint, at in reversed(entries):
        # Each resume and each answered approval begins with a bookkeeping
        # checkpoint of its own; the stage it goes back into is the same entry.
        if node in _SYNTHETIC_NODES or not has_next:
            continue
        # The side-by-side workers and the step gathering them belong to the
        # stage that sent them: a dispatch that goes round its workers forty
        # times is one stage entered once.
        if node is None or node.endswith(("_worker", "_gather")):
            continue
        if _not_a_stage_of_its_own(node):
            previous = None
            continue
        if node == previous:
            continue
        previous = node
        points.append({"checkpoint_id": checkpoint_id, "stage": node, "sprint": sprint, "at": at})
    return points


class RewindError(ValueError):
    """A rewind that cannot be made, with the reason a person can act on."""


def rewind_to(graph: Any, thread_id: str, checkpoint_id: str, repo_root: str | None = None) -> dict[str, Any]:
    """Make the checkpoint before a stage the run's latest, with the workspace as it was then.

    The run's history is kept: the rewound run continues on a branch from
    that checkpoint, and the workspace it leaves is snapshotted first. Returns
    what was done: the stage, and whether the files were put back.
    """
    config = _run_config(thread_id, DEFAULT_RECURSION_LIMIT)
    # That one checkpoint, read by its id. Measured on 2026-10-20: scanning the
    # history for it - the checkpoint store reads the history whole - got the
    # API's workers killed for memory on an 11-hour run, and the rewind failed.
    at = {**config, "configurable": {**config.get("configurable", {}), "checkpoint_ns": "", "checkpoint_id": checkpoint_id}}
    try:
        target = graph.get_state(at)
    except Exception:  # noqa: BLE001 - an unreadable checkpoint is one this run does not have
        target = None
    if target is None or (target.config or {}).get("configurable", {}).get("checkpoint_id") != checkpoint_id:
        raise RewindError(f"This run has no checkpoint {checkpoint_id}.")
    node = target.next[0] if len(target.next or ()) == 1 else None
    if node is None or _not_a_stage_of_its_own(node):
        raise RewindError("A run is rewound only to the start of a stage.")
    restored = False
    if repo_root:
        from app.tools.version_control import (
            SnapshotNotTaken,
            restore_snapshot,
            snapshot_for_checkpoint,
            stage_snapshots,
        )

        try:
            taken = snapshot_for_checkpoint(stage_snapshots(repo_root), node, checkpoint_id, _checkpoint_millis(target))
        except SnapshotNotTaken:
            # No snapshot was expected of a stage with no workspace yet, nor of
            # the point the run stands at (its stage has not started): the
            # files as they are are that point's.
            latest = graph.get_state(config)
            standing = (latest.config or {}).get("configurable", {}).get("checkpoint_id") if latest else None
            if _repository_root(target.values or {}) and standing != checkpoint_id:
                raise RewindError(
                    f"The workspace was not snapshotted when {node} started at this point, so its files "
                    "cannot be put back as they were then. Rewind to an earlier point of this stage or "
                    "to an earlier stage."
                ) from None
            taken = None
        if taken:
            restored = restore_snapshot(repo_root, taken)
            if not restored:
                degraded("rewind.files_restored", None, of=node)
        # A rewound stage is a new attempt, never a conversation a stopped
        # worker cut off - whatever notes the files put back hold.
        from app.graph import abandoned_threads

        abandoned_threads.forget_every_stage(repo_root, thread_id)
    # The start of a stage answers no gate: whatever a later point was parked
    # on is not this one's.
    graph.update_state(target.config, {
        "error": None, "pending_decision": None, "pending_inner_thread_id": None, "pending_approval": None,
    })
    logger.info(
        "Rewound to %s; the workspace %s", node,
        "was put back as it was then" if restored else "was left as it is (no snapshot of it then)",
    )
    return {"stage": node, "files_restored": restored, "point_at": str(getattr(target, "created_at", "") or "")}

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


def approve_decision(
    comment: str | None = None, edited_content: str | None = None, *, by_timeout: bool = False
) -> dict[str, Any]:
    """Build a review decision that accepts the current artifact revision.

    `by_timeout`: nobody answered and the gate's time ran out, so the run goes on by itself; its decision record says
    so rather than naming a reviewer who never looked.
    """
    decision: dict[str, Any] = {"type": "approve", "comment": comment, "edited_content": edited_content}
    if by_timeout:
        decision["decided_by"] = "timeout"
    return decision


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
    "SPRINT_PLAN_REVIEW",
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
