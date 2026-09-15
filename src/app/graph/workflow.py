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
from app.agents.review_document import render_architecture_review
from app.agents.artifact_document import render_artifact
from app.agents.specification_document import render_specification
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

    That reasoning was incomplete, and run-c4f17841 showed why. The reviewer was
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

INNER_AGENT_RECURSION_LIMIT = 60
"""Superstep ceiling for one role agent's own graph.

The outer workflow has had a ceiling since it was written; the agent invoked
inside a stage had none, so it ran on LangGraph's default. A stage that loops
internally - model emits text, tools run, model emits the same text - never
returns, so no workflow guard applies to it: not the structured-response retry,
not the repeat guard, not the approval ceiling. All of those are checked when a
stage *ends*.

Measured on run-2192f23b, whose principal architect spent twenty-two minutes
and 184 events printing the same specification into the conversation and
re-reading the same three documents, with zero restarts recorded because the
stage never finished one. The only ceiling it would have met is the Celery task
timeout, six hours away.

60 is roughly twice the longest healthy stage observed across fourteen runs and
well under the outer limit, so a working stage never meets it and a spinning one
surfaces as an error the workflow can report.
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
    # Per-stage count of attempts that ended without a structured response.
    structured_retries: dict[str, int]
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
    # Measured on run-cbd22a34: "Failed to parse tool call arguments as JSON:
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
        return _owning_node(inner_stage_name)
    return stage


#: State belonging to a stage's pause, which must not outlive that stage.
#:
#: `_run_gated_agent` clears these on success, but a node that pops its private
#: result key and then returns a *fresh* dict silently drops that reset. The
#: next stage inherits `pending_decision` and `pending_inner_thread_id` from the
#: stage before it - and `_run_gated_agent`, seeing a pending decision, resumes
#: that inherited thread instead of starting its own.
#:
#: Observed on run-0b55ad49: `milestone_review` finished with `changes_required`
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
    changes nothing: on run-0b55ad49 a review named the exact file, line and fix
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

    # Not every model fills a bespoke field. Measured on run-95ca3f72, this one
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


def _max_structured_retries() -> int:
    """How many times a stage may be restarted for producing no structured answer.

    A retry here is not a repeat of the same request: the previous attempt's
    conversation is abandoned and the stage starts a fresh one. That distinction
    is the whole reason retrying works. The failure is not "the model cannot do
    this" but "this particular conversation went somewhere it could not come
    back from" - on run-0b55ad49 a specialist answered in 431,441 characters of
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
    on run-c826ae90 `product_manager_node` overwrote the retry's
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
    Measured on run-2b5def74: two such messages, 2,027 and 2,028 characters,
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
    return None


def _answer_written_into_the_conversation(result: dict[str, Any], schema: Any) -> Any | None:
    """The structured response, recovered from a message that contains it.

    The failure this exists for is not a model that could not answer. It is a
    model that answered correctly and sent it down the wrong channel: on
    run-2b5def74 `specialist_backend_0` emitted its complete response object as
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
            continue
        if not isinstance(payload, dict):
            continue
        try:
            return schema.model_validate(payload)
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

    Measured on run-2192f23b: forty minutes and 266 events, every cycle
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


def _spun_without_finishing(stage_name: str, exc: Exception) -> str | None:
    """Explain a stage that hit its superstep ceiling, or None if it did not.

    A `GraphRecursionError` from an inner agent reads as a LangGraph internal,
    and the operator is left with a stack trace for a condition that has a plain
    description: the stage went round in a circle and never produced an answer.

    Measured on run-2192f23b: the principal architect spent twenty-two minutes
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


def _nudge_for_the_structured_response(
    agent: Any, inner_thread_id: str, callbacks: Any
) -> dict[str, Any] | None:
    """Ask the same conversation for the answer it already worked out.

    The retry below starts the stage over on a clean conversation, which works
    but throws away everything the stage learned. Measured on run-61c5a5b6:
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
        result = agent.invoke(
            {"messages": [{"role": "user", "content": _STRUCTURED_RESPONSE_NUDGE}]},
            config={"configurable": {"thread_id": inner_thread_id}, "callbacks": callbacks},
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
    return None


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

    detail = (
        f"Its last message was {len(text):,} characters."
        if text
        else "It produced no final message at all."
    )
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
        try:
            result = agent.invoke(
                initial_request,
                config={
                    "configurable": {"thread_id": inner_thread_id},
                    "callbacks": activity,
                    "recursion_limit": INNER_AGENT_RECURSION_LIMIT,
                },
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
        nudged = _nudge_for_the_structured_response(agent, inner_thread_id, activity)
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
        # Start the stage over on a clean conversation rather than failing the
        # run. Clearing `pending_inner_thread_id` is what makes this a retry
        # instead of a loop: without it the resume path re-enters the very
        # conversation that failed, replays it, and fails identically - which is
        # exactly what happened on run-0b55ad49 until this existed.
        retries = dict(state.get("structured_retries") or {})
        attempted = retries.get(stage_name, 0)
        if attempted < _max_structured_retries():
            retries[stage_name] = attempted + 1
            logger.warning(
                "Stage %s produced no structured response; retrying on a fresh "
                "conversation (attempt %d of %d)",
                stage_name, attempted + 2, _max_structured_retries() + 1,
            )
            return {
                # The node that owns this stage, never the stage's own name:
                # `specialist_ui_ux_0` is not a graph node.
                "stage": _owning_node(stage_name),
                "structured_retries": retries,
                "pending_approval": None,
                "pending_inner_thread_id": None,
                "pending_decision": None,
                "inner_thread_ids": [*state.get("inner_thread_ids", []), inner_thread_id],
            }
        raise ValueError(
            _missing_structured_response(stage_name, result, attempts=attempted + 1)
        )

    succeeded = dict(state.get("structured_retries") or {})
    succeeded.pop(stage_name, None)

    return {
        output_key: structured_response,
        "stage": next_stage,
        "structured_retries": succeeded,
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


_GATING_SEVERITIES = frozenset({"blocking", "major"})
"""Severities that force `changes_required`; see `ArchitectureReviewOutput`."""


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
    from app.tools.repository import write_approved_artifact

    try:
        write_approved_artifact(state["repository"].root_path, relative_path, content)
    except Exception:  # noqa: BLE001 - the decision matters more than the record
        logger.warning("Could not write %s", relative_path, exc_info=True)


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
    one run returned its structured response, the other wrote "# Product Intake
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

    Observed on run-95ca3f72: the reviewer returned `changes_required` with
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
        return "\n".join(
            f"[{f.severity}] {f.category}: {f.description} -> {f.required_remediation}"
            for f in findings
        )

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

        _record_document(
            state,
            "docs/product_intake.md",
            render_artifact(update["product_intake"], title="Product Intake"),
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
            # could not work. Measured on run-c826ae90: resumed once, failed
            # again in the same place.
            retries = dict(state.get("structured_retries") or {})
            key = "product_manager:intake"
            attempted = retries.get(key, 0)
            if attempted < _max_structured_retries():
                retries[key] = attempted + 1
                return _handing_on(stage="product_manager", structured_retries=retries)
            # The stage before this one finished without returning its
            # structured response - on run-c826ae90 the product manager wrote
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
                render_artifact(update["tools_models"], title="Tools and Models"),
            )
        return update

    def stack_selector_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        agent = create_stack_selector_agent(model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
        request = {"messages": [{"role": "user", "content": f"Product Intake: {state['product_intake']}\nTools: {state.get('tools_models')}"}]}
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

        # Rendered from the decision, like every other document the workflow
        # keeps. On run-0b18e403 this stage still wrote its own: it printed the
        # selection into the conversation, wrote `docs/technology_stack.md`,
        # printed it again, wrote again - five identical writes, and the repeat
        # guard ended the run at stage three. The same shape that cost
        # run-78804673 its technical lead and run-c826ae90 its architecture
        # reviewer, in the one stage that had not been converted.
        _record_document(
            state,
            "docs/technology_stack.md",
            render_artifact(update["stack_selection"], title="Technology Stack"),
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
                update["specification_repair_count"] = 0
        return update

    def architecture_review_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        missing = _missing_upstream(state, "technical_specification")
        if missing is not None:
            return missing
        agent = create_architecture_reviewer_agent(model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories)
        spec_text = _as_text(state.get("technical_specification"))
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
        if _hand_back(update, "architecture_review"):
            return update

        review: ArchitectureReviewOutput = update["architecture_review"]

        # Rendered from the decision, not written by the reviewer as a second
        # copy that can disagree with it. See `app.agents.review_document`.
        _record_document(state, "docs/architecture_review.md", render_architecture_review(review))

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
                # Name what is still wrong. The bare "reached the limit" message
                # told a reader that the run died but not what to do about it,
                # even though the reviewer had just written the answer down.
                outstanding = [
                    _format_finding(f)
                    for f in review.findings
                    if f.severity in _GATING_SEVERITIES
                ]
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
        if not _hand_back(update, "sprint_plan"):
            update["current_sprint_index"] = 0
            _record_document(
                state,
                "docs/sprint_plan.md",
                render_artifact(update["sprint_plan"], title="Sprint Plan"),
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
        if _hand_back(update, "milestone_plan"):
            return update

        _record_document(
            state,
            "docs/milestone_plan.md",
            render_artifact(update["milestone_plan"], title="Milestone Plan"),
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
            key = "technical_lead:assignments"
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

        update["remediation"] = start_remediation(milestone.selected_sprint_goal, max_attempts=MAX_REMEDIATION_ATTEMPTS)
        update["specialist_task_index"] = 0
        update["revision_comments"] = []
        return update

    def specialist_dispatch_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        missing = _missing_upstream(state, "milestone_plan")
        if missing is not None:
            return missing
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
        changed_files = sorted({name for output in outputs.values() for name in output.changed_files})

        agent = create_specialist_agent(
            "testing", model=model, checkpointer=shared_checkpointer, repo_root=repo_root, allow_subdirectories=allow_subdirectories
        )
        request = build_test_run_request(
            milestone.selected_sprint_goal,
            changed_files,
            state["repository"].root_path,
            getattr(state.get("stack_selection"), "technology_stack", None),
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
            return _handing_on(
                stage="user_review_sprint",
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
            return _handing_on(
                **base_update,
                stage="failed",
                error=(
                    f"Sprint '{cycle.sprint_goal}' exhausted its {cycle.max_attempts} remediation attempts "
                    f"with defects still open. A human must intervene.\n\n{build_defect_report(cycle)}"
                ),
            )

        if any(defect.status == "open" for defect in cycle.defects):
            return _handing_on(**base_update, stage="defect_remediation", defect_cursor=0)

        # Tests pass and nothing is open. The acceptance gate is still the
        # authority on whether this sprint may be accepted - it also refuses a
        # fix with missing regression coverage or an undocumented accepted risk.
        if not is_sprint_acceptable(cycle):
            return _handing_on(
                **base_update,
                stage="failed",
                error=(
                    "The sprint cannot be accepted despite passing tests; a defect is missing "
                    f"regression coverage or a documented accepted risk.\n\n{build_defect_report(cycle)}"
                ),
            )

        return _handing_on(**base_update, stage="security_review")

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
        return _handing_on(stage="milestone_review", security_review=review)

    def milestone_review_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
        missing = _missing_upstream(state, "milestone_plan")
        if missing is not None:
            return missing
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
            getattr(state.get("stack_selection"), "technology_stack", None),
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

        # The document is rendered here, from the decision the workflow routes
        # on, rather than written by the reviewer as a second copy that can
        # disagree with it. See `app.agents.review_document`.
        _record_review_document(state, review, milestone.selected_sprint_goal)
        
        if review.status == "blocked":
            return _handing_on(
                stage="failed",
                error="Milestone review blocked the sprint from continuing. See findings.",
                milestone_review=review,
            )
        elif review.status == "changes_required":
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
            revision_count = state.get("milestone_revision_count", 0) + 1
            if revision_count >= MAX_MILESTONE_REVISIONS:
                return _handing_on(
                    stage="user_review_sprint",
                    milestone_revision_count=revision_count,
                    milestone_review=review,
                )
            return _handing_on(
                stage="technical_lead",
                revision_comments=state.get("revision_comments", []) + [findings_text],
                milestone_revision_count=revision_count,
                milestone_review=review,
            )
        
        sprint_index = state.get("current_sprint_index", 0)
        sprints = state.get("sprint_plan").sprints if state.get("sprint_plan") else []
        has_more_sprints = sprint_index < len(sprints) - 1

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
    return graph.invoke({"pending_decision": decision}, config=_run_config(thread_id, recursion_limit, metadata=metadata, run_id=run_id))


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
    "build_workflow_graph",
    "request_changes_decision",
    "resume_failed_run",
    "resume_pending_approval",
    "resume_pending_review",
    "skip_decision",
    "start_workflow",
]
