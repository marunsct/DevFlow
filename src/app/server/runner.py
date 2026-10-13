"""Async bridge between the web control plane and the synchronous LangGraph workflow.

The workflow graph is invoked synchronously (``graph.invoke(...)``), but the
web server is async (FastAPI/Starlette).  This module runs each invoke in a
thread pool so the event loop stays responsive, publishes events to the
``EventBus`` on every state change, and uses ``asyncio.Event`` objects to
hand off human decisions (approval, review) without polling.

Design note: the graph itself is unchanged — it still returns state dicts and
pauses by setting a ``stage`` prefix.  The runner just wraps that same
invoke-loop pattern from ``main.py`` in an async harness that emits events
instead of printing to stdout.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from app.agents.approval import approve_write_decision, reject_write_decision
from app.documents import DocumentContent
from app.graph.workflow import (
    APPROVAL_PAUSE_PREFIX,
    REVIEW_PAUSE_PREFIX,
    RunCancelled,
    approve_decision,
    build_workflow_graph,
    queued_parallel_pauses,
    request_changes_decision,
    resume_pending_approval,
    resume_pending_review,
    skip_decision,
    start_workflow,
)
from app.models.quota import OUT_OF_QUOTA_PHRASES, out_of_quota
from app.observability.cost_tracker import RunCost, forget_run, run_cost
from app.observability.metrics import MetricsTracker
from app.server.events import EventBus, RunEvent, redact_metadata
from app.state import RepositoryContext
from app.tracing import is_tracing_enabled, trace_metadata

logger = logging.getLogger(__name__)

def _max_gates() -> int:
    """The automatic-approval ceiling, read from the environment.

    Exposed as a function as well as a constant so a test can exercise the
    parsing without `importlib.reload`. Reloading this module rebinds every
    class in it - `RunConflict`, `RunRecord`, `WorkflowRunner` - to new objects
    while leaving every module that already imported one holding the old one, so
    a later `except RunConflict` silently stops matching.
    """
    return int(os.environ.get("WORKFLOW_MAX_GATES", "1000"))


MAX_GATES = _max_gates()


def _max_gates_per_stage() -> int:
    """How many auto-approvals one stage may take before the run is stopped.

    `MAX_GATES` bounds the whole run, which is the wrong shape for the failure
    that actually happens: an agent that re-requests a write at the same gate
    forever. One real run spent all 1000 of its gates on
    `awaiting_approval:product_manager` - a thousand model calls, every one
    auto-approved, no progress - and only stopped at the global ceiling.

    This is now a backstop, not the loop detector. `MAX_IDENTICAL_GATES` catches
    the real failure - the same write requested over and over - precisely and
    within a few rounds, so this only has to stop a stage that is expensive
    rather than stuck.

    It was 25, chosen when "a stage writes a handful of artifacts" was true.
    Gating command execution as well as writes made it false: a testing
    specialist writes a test, runs the suite, fixes what broke and runs it
    again, and each of those is one gate. One was killed at 26 rounds of real
    progress and told it was looping. The ceiling has to clear that kind of work
    comfortably, because a stage that trips it loses everything it did.
    """
    default = 120
    try:
        return int(os.environ.get("WORKFLOW_MAX_GATES_PER_STAGE", str(default)))
    except ValueError:
        logger.warning("Malformed WORKFLOW_MAX_GATES_PER_STAGE; using %d", default)
        return default


MAX_GATES_PER_STAGE = _max_gates_per_stage()
"""Safety ceiling: stop after this many invoke rounds in one run segment.

Only auto-approved runs get anywhere near this - a supervised run returns to the
human at each gate, ending the segment. An unattended run does the opposite: it
answers every gate itself and does the whole build in one segment, and every
artifact write by every specialist across every sprint is one round. The old
ceiling of 200 was sized for a mostly-supervised run and would stop a real
unattended build part-way through.

It exists to catch a stage that is genuinely looping, not to bound normal work,
so it is set high and made configurable rather than tuned.
"""

# Stage-meaning map, matching main.py's _STAGE_MEANINGS.
_STAGE_MEANINGS: dict[str, str] = {
    "product_manager": "Reading the product document and extracting product understanding.",
    "tools_models": "Comparing frameworks, model providers, and infrastructure options.",
    "principal_architect": "Writing the technical specification and architecture decisions.",
    "architecture_review": "The architecture reviewer is checking security and feasibility.",
    "user_review_specification": "Waiting for your review of the technical specification.",
    "scrum_master": "Breaking approved architecture into independent vertical sprints.",
    "technical_lead": "Selecting one sprint and planning a small milestone.",
    "specialist_dispatch": "Specialists are implementing and testing the milestone.",
    "test_and_triage": "Running tests and triaging any failures into tracked defects.",
    "defect_remediation": "Routing defects to their owners for fixing.",
    "milestone_review": "The milestone reviewer is checking the completed work.",
    "user_review_sprint": "Waiting for your review of the completed sprint.",
    "complete": "The run finished successfully.",
    "failed": "The run stopped and needs a human decision.",
}


def _stage_meaning(stage: str) -> str:
    """Human-readable meaning for a stage."""
    if stage.startswith(APPROVAL_PAUSE_PREFIX):
        return f"Waiting for approval: {stage.removeprefix(APPROVAL_PAUSE_PREFIX)}"
    if stage.startswith(REVIEW_PAUSE_PREFIX):
        return f"Waiting for review: {stage.removeprefix(REVIEW_PAUSE_PREFIX)}"
    return _STAGE_MEANINGS.get(stage, stage)


def _api_status(stage: str) -> str:
    """Map a raw stage string to one of the API's status enum values."""
    if stage == "complete":
        return "completed"
    if stage == "failed":
        return "failed"
    if stage.startswith(APPROVAL_PAUSE_PREFIX):
        return "waiting_for_approval"
    if stage.startswith(REVIEW_PAUSE_PREFIX):
        return "waiting_for_review"
    return "running"


def _the_stage_itself(stage: str) -> str:
    """`specialist_ui_ux_0` from `awaiting_approval:specialist_ui_ux_0`.

    The gate loop only ever sees a *paused* stage value - the graph runs its
    nodes internally and returns at an interrupt - so the string handed to the
    histogram carried the pause prefix. Measured live on 2026-09-21::

        stage_duration_seconds_sum{stage="awaiting_approval:specialist_ui_ux_0"} 78.5

    A dashboard grouping by `stage` therefore sees a series per *pause*, and the
    stage names an operator would look for never appear at all. `_derive_stages`
    already folds a pause into its parent for exactly this reason - its docstring
    opens with "A pause is not a stage" - and the histogram was the one reader
    that did not.

    **What this does not fix, and cannot from here.** A stage that never pauses
    is never observed: the loop sees one returned state per interrupt, so five
    of run 2's first six stages - `tools_models`, `principal_architect`,
    `architecture_review`, `scrum_master`, `technical_lead`, none of which took
    an approval - produced no observation at all. The histogram is a record of
    gated stages, correctly named. Timing every stage needs an observation point
    inside the graph, where the transitions actually happen.
    """
    for prefix in (APPROVAL_PAUSE_PREFIX, REVIEW_PAUSE_PREFIX):
        if stage.startswith(prefix):
            return stage.removeprefix(prefix)
    return stage


def _record_stage_duration(timed: dict[str, object]) -> None:
    """Observe how long the previously-timed stage ran, on the metrics histogram.

    Called at the moment a *different* stage appears, because that is the first
    moment the previous one's duration is known. `timed` is the
    ``{"stage": ..., "started_at": time.monotonic()}`` dict carried across the
    gate loop's iterations; an empty dict is the loop's initial state and means
    nothing has been timed yet.

    Failures here must never kill a run: a metric is not worth a run. The
    histogram is best-effort, so anything unexpected is logged and swallowed.
    """
    if not timed:
        return
    stage = timed.get("stage")
    started_at = timed.get("started_at")
    if not stage or not isinstance(started_at, (int, float)):
        return
    try:
        MetricsTracker.record_stage_duration(
            _the_stage_itself(str(stage)), time.monotonic() - started_at
        )
    except Exception:  # noqa: BLE001 - see the docstring: metrics must not break a run
        logger.warning("Could not record the stage-duration metric", exc_info=True)


#: Status of a run parked because it reached its spending ceiling.
#:
#: Named like `waiting_for_approval` and `waiting_for_review` because it is the
#: same kind of state: the run is intact, its work is good, and it is waiting
#: for a person. It is deliberately not `failed` - nothing went wrong.
BUDGET_PAUSE_STATUS = "waiting_for_budget"


#: Statuses a run is resumed from, from its last checkpoint.
RESUMABLE_STATUSES = ("failed", BUDGET_PAUSE_STATUS, "paused", "cancelled")


CANCELLABLE_WHILE_PARKED = (
    "created",
    "waiting_for_approval",
    "waiting_for_review",
    "paused",
    BUDGET_PAUSE_STATUS,
)
"""Statuses in which a run is parked with no worker driving it.

Cancelling one of these has to mark it terminal here, because there is nobody
else left to notice the cancel flag.
"""


def _max_concurrent_runs() -> int:
    """How many runs may execute at once; 0 or less disables the limit.

    Item 6 of Part III of the hardening plan (`docs/harness-improvement-plan.md`), and the gate on Part I's
    item 2. Nothing bounded this: two unattended runs against one local model
    server shared that server's queue and neither could know its latency was
    being caused by the other.

    Observed on 2026-09-20. Orphan recovery resumed one run at the moment
    one run was started, and both executed - throughput halved and the 524
    rate rose, on a deployment whose model server answers one request at a time.

    Why Part I's probe needs this. That item derives a request timeout from a
    *measured* generation rate. A probe run on a contended server measures a
    rate the run will not see, or the reverse, and the derived timeout is wrong
    in whichever direction the contention happened to push it. Measuring the
    model requires being the only load.

    Read on every dispatch rather than captured at import, for the reason
    `_max_run_cost_usd` gives: the answer to "the queue is full" is to raise the
    limit, and that should not need a worker restart.

    Off by default, because a deployment with a worker pool sized for the work
    already has its answer and a second ceiling underneath the first is a
    surprise.
    """
    raw = os.environ.get("MAX_CONCURRENT_RUNS", "").strip()
    if not raw:
        return 0
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        logger.warning("MAX_CONCURRENT_RUNS is not a number: %r; ignoring it", raw)
        return 0


def _max_run_cost_usd() -> float:
    """The per-run spending ceiling in US dollars; 0 or less disables it.

    Read on every check rather than captured at import, which is what makes
    `MAX_GATES` and this setting differently shaped. A gate ceiling is consulted
    by a run that is already moving; this one is consulted by a run an operator
    has just been asked to make a decision about, and the decision on offer is
    "raise it and resume". Captured at import, raising it would need a worker
    restart, which turns a one-line answer into an outage.

    Off by default. A deployment on a local model spends nothing, and a ceiling
    that fires on a run costing nothing would be the third fabricated number
    plan-part3 §3.2 set out to remove.
    """
    raw = os.environ.get("MAX_RUN_COST_USD", "").strip()
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        logger.warning("Malformed MAX_RUN_COST_USD (%r); no ceiling applied", raw)
        return 0.0


def _budget_exceeded(run_id: str) -> tuple[bool, RunCost]:
    """Whether this run has passed its ceiling, and the total it passed it with.

    Returns the total either way so the caller can name the spend in the pause
    message without reading it twice - the number that triggers the pause must
    be the number the operator is shown, or they are being asked to decide about
    a different run than the one that stopped.

    An unpriced call is not counted against the ceiling, because its cost is
    unknown rather than zero. That is the safe direction for a *pause*: a
    ceiling that fires on a number it invented would stop good work for a reason
    that is not true. `unpriced_requests` on the summary is how an operator sees
    that the total is partial, and the dashboard shows it beside the spend.

    So the ceiling is a hard cap only over priced models: a run is refused at
    start when a configured model has no price (`_require_a_ceiling_that_can_hold`).
    A reply that comes back without usage is still unpriced and still uncounted.
    """
    ceiling = _max_run_cost_usd()
    total = run_cost(run_id)
    if ceiling <= 0:
        return False, total
    return total.usd >= ceiling, total


def _stage_narration(stage: str, *, auto_approve: bool) -> tuple[str, str]:
    """The message and API status to report for a stage.

    Returns `(message, status)`.

    An unattended run is not waiting for anyone. Reporting
    `waiting_for_approval` for a gate the run is about to clear itself is wrong
    three times over: the dashboard renders an approval modal nobody needs to
    answer, the log narrates a pause that is not happening, and - the reason
    this is not merely cosmetic - `submit_approval`'s
    compare-and-set guard accepts the transition, dispatching a second Celery
    task onto a graph thread the first task is still driving.
    """
    status = _api_status(stage)
    if auto_approve and status == "waiting_for_approval":
        return (f"Auto-approving: {stage.removeprefix(APPROVAL_PAUSE_PREFIX)}", "running")
    return (_stage_meaning(stage), status)


class RunConflict(RuntimeError):
    """A lifecycle transition was attempted from the wrong status."""


class RunQueueFull(RunConflict):
    """Every worker slot is taken. A queueing signal, not a failure.

    A subclass of `RunConflict` so existing handlers keep returning 409 without
    change, and its own type so a caller that wants to distinguish "you cannot
    do that" from "not yet" can.
    """


_SECRET_OVERRIDE_KEYS = frozenset({"openai_api_key", "anthropic_api_key", "google_api_key"})

_DEPLOYMENT_OVERRIDE_KEYS = frozenset({"openai_base_url"})
"""Overrides that describe *where the model is hosted*, not what the run chose.

`llm_provider` and `model_name` are experiment choices worth pinning to a run:
re-running it later should use the same model. A base URL is not - it is
deployment configuration, and the host moves.

Pinning it meant that moving the model server broke every run that already
existed, permanently: the stored URL won over the corrected setting on every
resume, so there was no way to point an existing run at the new address.
"""

_UNPINNED_OVERRIDE_KEYS = _SECRET_OVERRIDE_KEYS | _DEPLOYMENT_OVERRIDE_KEYS


def _public_model_overrides(overrides: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only the parts of a model override worth persisting on the run.

    API keys must not be persisted in the metadata table or shipped through the
    Celery broker; the worker resolves credentials from its own environment or
    the secret store. The base URL is dropped for a different reason - see
    `_DEPLOYMENT_OVERRIDE_KEYS`.
    """
    if not overrides:
        return {}
    return {k: v for k, v in overrides.items() if v and k not in _UNPINNED_OVERRIDE_KEYS}


def _applicable_overrides(overrides: dict[str, Any] | None) -> dict[str, Any]:
    """Filter overrides at the point of use, so rows written earlier self-heal.

    Runs created before the base URL stopped being pinned still carry one in
    their stored overrides. Dropping it here means those runs pick up the
    current setting on their next attempt instead of staying pointed at a host
    that may no longer exist.
    """
    return _public_model_overrides(overrides)


#: Recognised backend problems, and what the operator can do about each.
#:
#: A run that stops because the model server is not ready has nothing wrong with
#: it: the checkpoint, the artifacts and the pending gate are all intact, and it
#: continues the moment the server does. What reached the dashboard, though, was
#: the raw exception - `OpenAIInvalidRequestError: Error code: 400 - {'error':
#: {'message': 'No model loaded...'}}` - which asks the reader to pick a
#: sentence out of a nested dict to find out that they need to load a model.
#:
#: This is the same treatment `_context_overflow_update` already gives the one
#: other failure an operator can act on, applied to the ones that come from the
#: provider rather than from the conversation.
_PROVIDER_FAILURE_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        OUT_OF_QUOTA_PHRASES,
        "The model provider refused the call because the account's quota or credit "
        "is used up. Nothing in the run failed: it is paused at its last checkpoint. "
        "Add funds or change the plan with the provider, or point the model setting "
        "at another model, then resume.",
    ),
    (
        ("no model loaded", "inference/load", "model_not_found", "no models loaded",
         "downloaded but not loaded", "switch model by request", "is not loaded"),
        "The model server would not serve the model this run asked for: either "
        "nothing is loaded, or a different model is loaded and the server is not "
        "set to switch on request. Load the configured model there, turn on "
        "load-on-request, or point the model setting at whatever is already "
        "loaded - then resume. No work has been lost.",
    ),
    (
        ("connection refused", "failed to connect", "connection error",
         "name or service not known", "max retries exceeded"),
        "The model server could not be reached at the configured address. Check "
        "that it is running and that the base URL is right, then resume this run.",
    ),
    (
        ("invalid api key", "incorrect api key", "unauthorized", "authentication_error"),
        "The model server rejected the API key. Correct it in settings, then "
        "resume this run.",
    ),
    (
        ("softtimelimitexceeded", "timelimitexceeded", "task timed out"),
        "This run hit the worker's task time limit while it was still making "
        "progress. It stopped at a checkpoint, so resuming continues from there "
        "rather than starting over. If it keeps hitting the limit, raise "
        "CELERY_TASK_SOFT_TIME_LIMIT - a slow local model needs hours for a "
        "full run.",
    ),
)

RUN_ERROR_MAX_CHARS = 500
"""Ceiling on the error text stored on a run; it is rendered in the browser."""


def _explain_failure(exc: BaseException) -> str:
    """Describe a failed run in terms the person reading it can act on.

    Falls back to the exception itself whenever the cause is not one of the
    recognised backend problems, because an unrecognised failure is better shown
    verbatim than paraphrased into something that might not be true.

    The guidance is placed first so that it survives the length cap: the raw
    text is the part that can run to hundreds of characters of nested JSON, and
    it is the part the reader needs least.
    """
    raw = f"{type(exc).__name__}: {exc}"
    haystack = raw.lower()
    for markers, guidance in _PROVIDER_FAILURE_HINTS:
        if any(marker in haystack for marker in markers):
            room = RUN_ERROR_MAX_CHARS - len(guidance) - len("\n\nThe server said: ")
            return f"{guidance}\n\nThe server said: {raw[:max(room, 0)]}"
    return raw[:RUN_ERROR_MAX_CHARS]


MAX_IDLE_REINVOKES = 2
"""Re-invokes returning the same stage with nothing run before calling it stuck.

Two, because a graph that has work to do makes progress on the first re-invoke.
More rounds only delay a diagnosis that is already certain, and each round
publishes an event - the spin this catches wrote 1000 of them in five seconds.
"""

MAX_IDENTICAL_GATES = 4
"""Consecutive identical approval requests before a stage is called a loop.

A stage that asks for the same write over and over is making no progress, and
four rounds is well past any legitimate retry. This is the check that actually
catches looping; `MAX_GATES_PER_STAGE` is a blunt ceiling on total work and was
never a good loop detector - a testing specialist writing code, running the
suite, and fixing what broke tripped it after 26 rounds of real progress, and
the run then reported itself as looping when it was not.
"""

MAX_LOOPS_ANSWERED_BY_DENIAL = 4
"""How many times a looping stage is answered before the run is ended.

Ending the whole run was the first and only response, and it is the harshest
available. Measured on one run: `specialist_backend_8` wrote
`docs/blocker.md` five times - a perfectly reasonable document, written by a
model that had correctly worked out it was blocked and had no other move - and
that killed a run which had already completed a full sprint, a test round, a
security review and a milestone review.

The gate is a decision point, and a decision has two answers. Denying the
request tells the agent, in the one channel it is certainly reading, that this
write will not happen and why; the stage then either moves on or ends on its
own guards, and the workflow's existing handling for a stage that finishes
without an answer takes over. Only a stage that goes on looping after being
told ends the run, which is what the original check was for.

Raised from 2 to 4 on 2026-09-19, from the first measurement of what this
denial is worth. It reached a model in 18 of the 50 stored runs, and:

    the stage stopped within 3 calls        9 of 18   (50%)
    the run went on for 50+ more calls     12 of 18
    calls the run spent afterwards         median 90, max 541

So it rescues about half the time, and when it does not end the stage it
still almost always leaves the run alive to finish. Against that, 14 of the
60 most recent failures are runs ended by this guard after the allowance ran
out - the single largest cause after a worker restart.

Each denial resets the repeat counter, so another `MAX_IDENTICAL_GATES + 1`
identical gates must accumulate before the next one. Two more allowances is
therefore at most ten extra gates in the worst case, against a 50% chance
each of saving a run that has already completed sprints, test rounds and
reviews. `MAX_GATES_PER_STAGE` and the task timeout still bound the whole.

This is a measured constant now rather than a chosen one, and the numbers
above are what to re-derive it against.
"""


def _what_was_asked_for(signature: tuple[str, str]) -> str:
    """The repeated request, named the way a person would name it.

    An approval signature is (path, notes); a command approval has no path, so
    the path half is a placeholder. Prefer whichever half says something.
    """
    path, notes = signature if signature else ("", "")
    for part in (path, notes):
        if part and "unknown" not in part.lower():
            return part[:120]
    return "an artifact write"


def _approval_signature(approval: Any) -> tuple[str, str]:
    """Identify what an approval is asking for, so repeats can be recognised.

    `notes` carries the head of the content being written, so two requests share
    a signature only when they target the same path with the same opening text.
    """
    return (
        getattr(approval, "artifact_path", "") if approval else "",
        (getattr(approval, "notes", "") or "") if approval else "",
    )


def _repeat_is_a_loop(approval: Any) -> bool:
    """Whether repeating this request means the stage has stopped progressing.

    Only a write. Re-requesting an identical write means nothing changed between
    attempts - `write_approved_artifact` reports exactly that, as `unchanged`.

    Re-running an identical *command* is the opposite: it is the build/fix cycle
    working. On one run `specialist_backend_1` ran `npm test`, read
    `app.js`, ran it again, read four more files, ran it again - real diagnosis
    between every run, with the tests passing - and was stopped as a loop after
    five. Commands stay bounded by `MAX_GATES_PER_STAGE`, which is the right
    ceiling for work that is expensive rather than stuck.
    """
    return getattr(approval, "action_kind", "unknown") != "command"


@dataclass
class _GateCount:
    """One paused stage's auto-approvals: its gate budget and its loop check.

    Kept per stage, so a parallel fan-out's workers each have their own count
    when several of their pauses are answered in one resume. It used to be one
    set of counters for "the current stage", reset whenever the surfaced stage
    changed - which in a fan-out, where the surfaced stage alternates between
    workers, reset it nearly every gate.
    """

    gates: int = 0
    repeats: int = 0
    last: tuple[str, str] | None = None
    signatures: dict[Any, int] = field(default_factory=dict)
    loops_answered: int = 0
    looping: bool = False

    def observe(self, approval: Any) -> tuple[str, tuple[str, str]]:
        """Count one gate: ("approve" | "deny" | "fail", what it asked for).

        A read-only look at the workspace is approved and recorded, but does
        not spend the budget meant for writes and builds. On one run a testing
        specialist used all 120 gates on `ls -la`, `find` and `cat` - work its
        ungated filesystem tools could have done - and was stopped before
        writing anything.
        """
        signature = _approval_signature(approval)
        if getattr(approval, "action_kind", "") != "read":
            self.gates += 1
        self.repeats = self.repeats + 1 if signature == self.last else 0
        self.signatures[signature] = self.signatures.get(signature, 0) + 1
        self.last = signature
        self.looping = self.repeats >= MAX_IDENTICAL_GATES and _repeat_is_a_loop(approval)
        if self.looping and self.loops_answered < MAX_LOOPS_ANSWERED_BY_DENIAL:
            # Answer the request instead of ending the run. See
            # `MAX_LOOPS_ANSWERED_BY_DENIAL`.
            self.loops_answered += 1
            self.repeats = 0
            return "deny", signature
        if self.looping or self.gates > MAX_GATES_PER_STAGE:
            return "fail", signature
        return "approve", signature


def _gate_failure_message(stage_name: str, count: _GateCount, signature: tuple[str, str]) -> str:
    """Why a stage was stopped at its gates: a loop, or its budget spent."""
    if count.looping:
        return (
            f"The '{stage_name}' stage asked to write the same thing "
            f"{count.repeats + 1} times in a row without moving on, so it was "
            f"stopped. The repeated request was: "
            f"{signature[0] if signature[0] and 'unknown' not in signature[0] else (signature[1] or 'an artifact write')}. "
            "An agent re-requesting an identical write is looping, and every "
            "attempt costs a model call."
        )
    # What it kept doing is the part worth reporting. "Raise the ceiling" alone
    # was the whole message, and on one run that was the wrong advice: the stage
    # ran `node test.js` over and over against a test whose assertion could not
    # be satisfied, so a larger budget would only have bought more of it.
    busiest = max(count.signatures.items(), key=lambda kv: kv[1], default=(None, 0))
    repeated = ""
    if busiest[0] and busiest[1] > 2:
        # A command approval carries no artifact path, so the path half is a
        # placeholder. Prefer whichever half actually says something: on one run
        # this read "<unknown path>, 21 times", which names the repetition
        # without naming the thing.
        path, notes = busiest[0]
        what = next(
            (part for part in (path, notes) if part and "unknown" not in part.lower()),
            "",
        )
        if what:
            repeated = f" Its most repeated request was {what[:120]}, {busiest[1]} times."
        else:
            repeated = (
                f" It made the same request {busiest[1]} times; "
                "the event log for this stage says which."
            )
    return (
        f"The '{stage_name}' stage used all "
        f"{MAX_GATES_PER_STAGE} of its approvals without finishing, so it "
        "was stopped. The requests were not identical, so this is either a "
        "stage doing more work than the ceiling allows, or an edit-and-retest "
        f"cycle that is not converging.{repeated} Check whether the same "
        "check keeps failing before raising WORKFLOW_MAX_GATES_PER_STAGE - "
        "a larger budget only helps the first case."
    )


def _approval_metadata(approval: Any) -> dict[str, Any]:
    return {
        "artifact_path": getattr(approval, "artifact_path", "") if approval else "",
        "risk_level": getattr(approval, "risk_level", "unknown") if approval else "unknown",
        "requested_by": getattr(approval, "requested_by", "") if approval else "",
    }


def _resume_config(thread_id: str, metadata: dict[str, Any] | None) -> dict[str, Any]:
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    if metadata:
        config["metadata"] = metadata
    return config


@dataclass
class RunRecord:
    """Metadata envelope for one workflow run.

    Graph state is deliberately *not* stored here. It lives in the checkpointer
    keyed by ``thread_id`` and is read from there on demand - keeping a second
    copy meant the two drifted, and in practice the copy was never written, so
    every API read saw an empty dict.
    """

    run_id: str
    thread_id: str
    document_names: list[str]
    document_paths: list[str]
    owner: str = "unknown"
    tenant_id: str = "default"
    status: str = "created"
    current_stage: str = ""
    stage_meaning: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: str | None = None

    # Settings captured at start time.
    repo_root: str | None = None
    review_policy: dict[str, bool] = field(default_factory=dict)
    reviewer: str = "unassigned"
    auto_approve: bool = False
    model_overrides: dict[str, Any] = field(default_factory=dict)

    # Execution bookkeeping.
    task_id: str | None = None
    cancel_requested: bool = False

    # Decision handoff: set by the API when enqueuing a resume task.
    pending_decision_payload: dict[str, Any] | None = field(default=None, repr=False)

    def graph_state(self, checkpointer: Any = None) -> dict[str, Any]:
        """Read this run's live graph state from the checkpointer.

        Returns an empty dict when the run has not started or the checkpoint is
        unavailable, so callers can treat "no state yet" and "cannot reach the
        store" the same way: nothing to show.
        """
        from app.graph.workflow import load_thread_state

        try:
            return load_thread_state(self.thread_id, checkpointer=checkpointer)
        except Exception:  # noqa: BLE001
            logger.warning("Could not load graph state for run %s", self.run_id, exc_info=True)
            return {}


class WorkflowRunner:
    """Manages workflow runs for the web server.

    Each run gets its own background task that drives the graph invoke-loop.
    The runner publishes events and pauses for human decisions without
    blocking the event loop.

    Thread safety: all state mutation happens inside asyncio tasks on the
    same event loop.  The ``asyncio.Event`` handoff ensures the runner and
    the API endpoint never race on the decision payload.
    """

    def __init__(
        self,
        event_bus: EventBus,
        *,
        model: str | None = None,
        repo_root: str | None = None,
        run_store: Any | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.model = model
        self.repo_root = repo_root
        self.run_store = run_store

        # Built through app.graph.checkpointing so the deserialization allowlist
        # and the configured backend actually apply. The previous hardcoded
        # `sqlite3.connect("workflow_state.db")` bypassed both: it ignored
        # DATA_DIR, put the database in each container's ephemeral layer, and
        # meant the API and the worker held separate invisible checkpoint stores.
        from app.graph.checkpointing import build_checkpointer

        self.checkpointer = build_checkpointer()





    def register_run(
        self,
        run_id: str,
        thread_id: str,
        document_names: list[str],
        document_paths: list[str],
        *,
        owner: str = "unknown",
        tenant_id: str = "default",
        review_policy: dict[str, bool] | None = None,
        reviewer: str | None = None,
        auto_approve: bool = False,
        model_overrides: dict[str, Any] | None = None,
    ) -> RunRecord:
        """Register a new run without starting it.

        The settings parameters exist so the API can register *and* start in one
        step instead of a separate ``start_run`` call. All are keyword-only and
        optional - registering on its own (the only thing this method was ever
        called for) behaves exactly as before, with attended defaults.

        ``repo_root`` is deliberately not a parameter: it comes from the
        repository context at start time, not from the caller's request body.
        """
        record = RunRecord(
            run_id=run_id,
            thread_id=thread_id,
            document_names=document_names,
            document_paths=document_paths,
            owner=owner,
            tenant_id=tenant_id,
        )
        if review_policy is not None:
            record.review_policy = dict(review_policy)
        if reviewer is not None:
            record.reviewer = reviewer
        record.auto_approve = bool(auto_approve)
        if model_overrides is not None:
            record.model_overrides = dict(model_overrides)
        self._persist(record)
        return record

    def discard_run_threads(self, record: RunRecord) -> None:
        """Delete the checkpoints this run created, outer and inner.

        Each agent attempt mints a fresh inner thread id to get a clean context
        window, so without this they accumulate unreachable forever.
        """
        from app.graph.workflow import discard_thread

        state = record.graph_state(self.checkpointer)
        for thread_id in [*state.get("inner_thread_ids", []), record.thread_id]:
            discard_thread(thread_id, checkpointer=self.checkpointer)

    async def _say_if_the_judgement_model_was_replaced(self, record: RunRecord) -> None:
        """Put a configured judgement model that could not be built into the run's history."""
        from app.models.roles import judgement_downgrade

        note = judgement_downgrade()
        if not note:
            return
        try:
            await self.event_bus.publish(
                record.run_id,
                RunEvent(
                    run_id=record.run_id,
                    sequence=await self.event_bus.next_sequence(record.run_id),
                    stage=record.current_stage or "",
                    event_type="log",
                    message=note,
                    metadata={"kind": "judgement_model_replaced"},
                ),
            )
        except Exception:  # noqa: BLE001 - the note never stops the run
            logger.warning("Could not record that the judgement model was replaced", exc_info=True)

    async def _require_command_execution(self) -> None:
        """Refuse to start when the workers reported that they cannot run commands.

        See `app.server.execution_readiness`. A record that cannot be read
        refuses nothing: this stops a run that was certain to fail, never one
        that might work.
        """
        from app.server.execution_readiness import READINESS_KEY, why_commands_cannot_run
        from app.server.redis_client import get_async_redis_client

        try:
            stored = await get_async_redis_client().get(READINESS_KEY)
        except Exception:  # noqa: BLE001 - never block on the store being down
            logger.warning("Could not read whether the workers can run commands", exc_info=True)
            return
        reason = why_commands_cannot_run(stored)
        if reason:
            raise RunConflict(reason)

    def _require_a_ceiling_that_can_hold(self) -> None:
        """Refuse to start under a spending ceiling that could not stop this run.

        `_budget_exceeded` counts only calls it could price, so a ceiling over a
        hosted model with no known rate reads as a hard cap and is none: every
        call goes unpriced and the total stays at zero. A local model is priced
        at nothing, which is a measurement, so it never trips this.
        """
        if _max_run_cost_usd() <= 0:
            return
        from app.models.roles import judgement_environment
        from app.observability.cost_tracker import price_for
        from app.server.runtime_settings import effective_environment

        try:
            environment = dict(effective_environment())
        except Exception:  # noqa: BLE001 - never block on reading settings
            logger.warning("Could not read settings to check the spending ceiling", exc_info=True)
            return
        unpriced = []
        for settings in (environment, judgement_environment(environment)):
            if not settings:
                continue
            provider = str(settings.get("LLM_PROVIDER") or "local").strip().lower()
            model = str(settings.get("OPENAI_MODEL") or "").strip()
            if model and price_for(provider, model) is None:
                unpriced.append(model)
        if unpriced:
            raise RunConflict(
                f"MAX_RUN_COST_USD is set to ${_max_run_cost_usd():.2f}, but "
                f"{', '.join(sorted(set(unpriced)))} has no known price, so its calls would "
                "not count toward the ceiling and nothing would stop the run. Add its rates "
                "to MODEL_PRICES_JSON, or unset MAX_RUN_COST_USD to run without a ceiling."
            )

    def _require_a_reachable_model(self) -> None:
        """Refuse to start when nothing is serving the configured endpoint.

        A model server that is not there and one that is merely slow produce
        the same symptom: the first call blocks and the run sits at `running`.

        Measured on one run: Docker Desktop wedged, the worker died, and
        the run reported `running` at the same stage for about ten hours.
        Telling the operator which address failed turns that into a one-line
        fix.

        The probe only reports absence on a transport failure - an auth
        challenge, a missing route, or a probe that cannot run all count as
        serving - so this refuses a run that was going to stall, not one that
        was going to work.
        """
        from app.config import load_settings
        from app.models.endpoint_probe import describe_model_endpoint
        from app.server.runtime_settings import effective_environment

        try:
            settings = load_settings(dict(effective_environment()))
        except Exception:  # noqa: BLE001 - never block on reading settings
            logger.warning("Could not read settings for the endpoint probe", exc_info=True)
            return

        status = describe_model_endpoint(settings)
        if not status.reachable:
            raise RunConflict(status.detail)

        # Reachable is not the same as usable. A proxy with a fixed origin
        # timeout can answer a probe in milliseconds and still cut off every
        # full-length reply the run will ask for. Warned, never refused: the
        # run works, it just truncates long answers and pays a retry for each,
        # and that is the operator's trade to make - but it has to be made
        # knowingly. One run made it unknowingly and spent 74 of its 130
        # minutes waiting out retries that could not succeed.
        try:
            from app.observability.proxy_timeouts import (
                reply_budget_that_cannot_arrive,
            )

            complaint = reply_budget_that_cannot_arrive(
                getattr(settings, "openai_base_url", "") or ""
            )
        except Exception:  # noqa: BLE001 - a warning never blocks a run
            complaint = ""
        if complaint:
            logger.warning("%s", complaint)

    async def start_run(
        self,
        run_id: str,
        document: DocumentContent,
        repository: RepositoryContext,
        *,
        review_policy: dict[str, bool] | None = None,
        reviewer: str = "unassigned",
        auto_approve: bool = False,
        model_overrides: dict[str, str | None] | None = None,
    ) -> None:
        """Persist start settings and dispatch the run to a worker.

        The status transition is atomic: two concurrent starts cannot both win,
        because only one UPDATE can match ``status = 'created'``.
        """
        record = self.run_store.load(run_id)
        if record is None:
            raise ValueError(f"Run {run_id} is not registered")

        await self._require_command_execution()
        self._require_a_ceiling_that_can_hold()
        self._require_a_reachable_model()

        record.repo_root = str(repository.root_path)
        record.review_policy = review_policy or {}
        record.reviewer = reviewer
        record.auto_approve = auto_approve
        # Overrides are persisted so the worker can apply them. They were
        # previously built here and then dropped, so choosing a model in the UI
        # had no effect at all. Secrets are filtered out: they must not travel
        # through the broker or sit in the metadata table.
        record.model_overrides = _public_model_overrides(model_overrides)
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(record)

        if not self.run_store.compare_and_set_status(
            run_id, "created", "running", updated_at=record.updated_at
        ):
            raise RunConflict(f"Run {run_id} is not in the 'created' state.")

        # Counted after the status transition succeeds, so a run that loses the
        # race to start is not counted as one that ran. This is the only place a
        # run begins; the counter is what makes `/metrics` show throughput.
        # See plan-part3 §3.1.
        from app.observability.metrics import MetricsTracker

        MetricsTracker.record_run()

        self._dispatch(run_id, resume=False, decision_payload=None)

    UNRESUMABLE_ERROR_MARKER = "Interrupted:"
    """Prefix on the error of a run whose checkpoint history cannot be trusted.

    Set by the out-of-band repair for runs damaged by the auto-approve status
    bug, where two Celery tasks wrote to one graph thread. Their history may be
    interleaved, so resuming reads a state no single run ever produced.
    """

    async def resume_run(self, run_id: str) -> None:
        """Resume a failed or budget-paused run from its last checkpoint."""
        record = self.run_store.load(run_id)
        if record is not None and (record.error or "").startswith(self.UNRESUMABLE_ERROR_MARKER):
            raise RunConflict(
                f"Run {run_id} was interrupted in a way that may have left its checkpoint "
                "history inconsistent, so resuming it would read a state no single run "
                "produced. Clone it to repeat the attempt from the beginning."
            )

        await self._require_command_execution()
        self._require_a_ceiling_that_can_hold()
        self._require_a_reachable_model()

        now = datetime.now(timezone.utc).isoformat()
        # A run parked at its spending ceiling, paused by its owner or cancelled
        # resumes by the same path as a failed one: each continues from the last
        # checkpoint and none carries a decision. They are tried in turn rather
        # than read-then-written so the status change stays a single
        # compare-and-set, which is what stops two resumes dispatching two
        # tasks onto one thread. A cancelled run keeps its checkpoints; a
        # cancel is final only until its owner says otherwise.
        for resumable in RESUMABLE_STATUSES:
            if self.run_store.compare_and_set_status(
                run_id, resumable, "running", updated_at=now, clear_error=True
            ):
                break
        else:
            raise RunConflict(
                f"Run {run_id} is not in one of the states a run resumes from: {', '.join(RESUMABLE_STATUSES)}."
            )
        # The stop flag a pause or a cancel raised would stop it again at once.
        self.run_store.clear_stop(run_id)
        self._dispatch(run_id, resume=True, decision_payload=None)

    async def pause_run(self, run_id: str) -> None:
        """Stop a running run at a stage boundary, keeping it to be resumed.

        The same two mechanisms as a cancel: the flag stops it cleanly at the
        next checkpoint, and the revoke stops a task mid-stage now - the stage
        it was in runs again on resume, as after a redeploy. Only the status
        recorded differs (`_finish_stopped`), and nothing is cleaned up.
        """
        record = self.run_store.load(run_id)
        if record is None:
            raise ValueError(f"Run {run_id} not found")
        now = datetime.now(timezone.utc).isoformat()
        if not self.run_store.request_pause(run_id, now):
            raise RunConflict(
                f"Run {run_id} is {record.status}; only a running run can be paused."
            )
        if record.task_id:
            try:
                from app.server.tasks import celery_app

                celery_app.control.revoke(record.task_id, terminate=True, signal="SIGTERM")
            except Exception:  # noqa: BLE001 - the flag still stops it at the next check
                logger.warning("Could not revoke task %s for run %s", record.task_id, run_id, exc_info=True)
        await self.event_bus.publish(
            run_id,
            RunEvent(
                run_id=run_id,
                sequence=await self.event_bus.next_sequence(run_id),
                stage=record.current_stage,
                event_type="stage_change",
                message="Run paused by user; resume it to continue from where it stopped.",
            ),
        )

    async def submit_approval(self, run_id: str, decision: dict[str, Any]) -> None:
        # Defence in depth against a stale status row. An unattended run answers
        # its own gates inside the worker; accepting a decision here would
        # dispatch a second task onto a thread that one is still driving, and
        # both would write checkpoints to it.
        record = self.run_store.load(run_id)
        if record is not None and record.auto_approve:
            raise RunConflict(
                f"Run {run_id} is unattended and approves its own gates. "
                "There is nothing to decide; cancel it if you want it to stop."
            )

        now = datetime.now(timezone.utc).isoformat()
        if not self.run_store.compare_and_set_status(
            run_id, "waiting_for_approval", "running", updated_at=now
        ):
            raise RunConflict(f"Run {run_id} is not waiting for approval.")
        self._dispatch(run_id, resume=True, decision_payload={"type": "approval", "decision": decision})

    async def submit_review(self, run_id: str, decision: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.run_store.compare_and_set_status(
            run_id, "waiting_for_review", "running", updated_at=now
        ):
            raise RunConflict(f"Run {run_id} is not waiting for review.")
        self._dispatch(run_id, resume=True, decision_payload={"type": "review", "decision": decision})

    async def cancel_run(self, run_id: str) -> None:
        """Request cancellation and revoke the worker task.

        Two mechanisms, because neither alone is sufficient: revoke stops a task
        that has not started or kills one that has, while the cancel flag lets a
        task that is mid-superstep stop cleanly at the next checkpoint rather
        than being killed halfway through a graph write.
        """
        record = self.run_store.load(run_id)
        if record is None:
            raise ValueError(f"Run {run_id} not found")
        if record.status in ("completed", "failed", "cancelled"):
            return

        now = datetime.now(timezone.utc).isoformat()
        self.run_store.request_cancel(run_id, now)

        if record.task_id:
            try:
                from app.server.tasks import celery_app

                celery_app.control.revoke(record.task_id, terminate=True, signal="SIGTERM")
            except Exception:  # noqa: BLE001 - the flag still stops it at the next check
                logger.warning("Could not revoke task %s for run %s", record.task_id, run_id, exc_info=True)

        # A run that is paused has no worker to notice the flag, so mark it
        # terminal here. A running one is left to the worker, which will see the
        # flag and record the cancellation itself.
        #
        # `BUDGET_PAUSE_STATUS` belongs in this set for the same reason as the
        # rest: the run is parked with no worker, so nothing else will ever act
        # on the flag, and the pause message offers cancelling as one of the two
        # ways out. Named in one tuple and reused, rather than written twice -
        # the two lists drifting apart is how a status becomes cancellable in
        # the test and not in the branch.
        if record.status in CANCELLABLE_WHILE_PARKED:
            self.run_store.compare_and_set_status(
                run_id,
                CANCELLABLE_WHILE_PARKED,
                "cancelled",
                updated_at=now,
            )

        await self.event_bus.publish(
            run_id,
            RunEvent(
                run_id=run_id,
                sequence=await self.event_bus.next_sequence(run_id),
                stage=record.current_stage,
                event_type="complete",
                message="Run was cancelled by user.",
            ),
        )
        await self.event_bus.close(run_id)

    def _dispatch(self, run_id: str, *, resume: bool, decision_payload: dict[str, Any] | None) -> None:
        """Hand the run to a Celery worker and remember the task id.

        Refuses rather than queues when every slot is taken. Celery would
        happily accept the message and hold it, which is the behaviour that
        made two runs contend for one model server in the first place: the
        second run looked started, and was in fact competing.
        """
        from app.server.tasks import execute_workflow_run

        limit = _max_concurrent_runs()
        if limit > 0:
            try:
                in_flight = self.run_store.count_in_flight()
            except Exception:  # noqa: BLE001 - a limit must never be the reason a run cannot start
                logger.warning("Could not count in-flight runs; dispatching", exc_info=True)
            else:
                if in_flight >= limit:
                    raise RunQueueFull(
                        f"{in_flight} of {limit} run slots are in use. This "
                        "deployment runs one model server, and a second run "
                        "started now would contend with the first rather than "
                        "go faster. Wait for a slot, or raise "
                        "MAX_CONCURRENT_RUNS."
                    )

        async_result = execute_workflow_run.delay(
            run_id=run_id, resume=resume, decision_payload=decision_payload
        )
        try:
            self.run_store.set_task_id(run_id, async_result.id)
        except Exception:  # noqa: BLE001 - dispatch succeeded; cancel is just less precise
            logger.warning("Could not record task id for run %s", run_id, exc_info=True)

    async def _run_loop(
        self,
        record: RunRecord,
        document: DocumentContent | None,
        repository: RepositoryContext | None,
        resume: bool = False,
        model_overrides: dict[str, str | None] | None = None,
    ) -> None:
        """Drive one segment of the graph, publishing events as it goes.

        One invoke per call. The graph runs until it pauses for a human or
        reaches a terminal stage, and this method then returns so the Celery task
        finishes; a later decision dispatches a fresh task. The previous version
        wrapped this in a 200-iteration loop whose non-terminal branch fell
        through to `continue` without re-invoking anything, so it republished the
        same event 200 times and then reported a gate-limit failure that had not
        happened.
        """
        run_id = record.run_id
        repo_root = repository.root_path if repository else record.repo_root
        allow_subs = repository.allow_subdirectories if repository else True
        overrides = _applicable_overrides(
            model_overrides if model_overrides is not None else record.model_overrides
        )

        try:
            if self.run_store.is_cancel_requested(run_id):
                await self._finish_cancelled(record)
                return
            from app.graph.workflow import forget_the_stop

            forget_the_stop(run_id)

            graph = build_workflow_graph(
                model=self.model,
                repo_root=repo_root,
                allow_subdirectories=allow_subs,
                model_overrides=overrides or None,
                checkpointer=self.checkpointer,
            )
            await self._say_if_the_judgement_model_was_replaced(record)

            trace_meta = (
                trace_metadata(
                    run_id=run_id, stage="start", role="controller", thread_id=record.thread_id
                )
                if is_tracing_enabled()
                else {}
            )

            if resume:
                decision = getattr(record, "pending_decision_payload", None)
                if decision and decision.get("type") == "approval":
                    state = await asyncio.to_thread(
                        resume_pending_approval, graph, record.thread_id, decision["decision"],
                        metadata=trace_meta, run_id=run_id,
                    )
                elif decision and decision.get("type") == "review":
                    state = await asyncio.to_thread(
                        resume_pending_review, graph, record.thread_id, decision["decision"],
                        metadata=trace_meta, run_id=run_id,
                    )
                elif self._resume_means_answering_own_gate(record):
                    state = await asyncio.to_thread(
                        resume_pending_approval, graph, record.thread_id,
                        approve_write_decision(), metadata=trace_meta, run_id=run_id,
                    )
                else:
                    from app.graph.workflow import resume_failed_run

                    state = await asyncio.to_thread(
                        resume_failed_run, graph, record.thread_id, metadata=trace_meta,
                        run_id=run_id,
                    )
            else:
                state = await asyncio.to_thread(
                    start_workflow, graph, document, repository, record.thread_id,
                    review_policy=record.review_policy, reviewer=record.reviewer,
                    metadata=trace_meta, run_id=run_id,
                )

            await self._handle_state(record, graph, state, trace_meta)

        except asyncio.CancelledError:
            await self._finish_cancelled(record)
            raise
        except RunCancelled:
            # Not a failure. The graph saw the cancel flag at a stage boundary
            # and stopped there, with the previous stage already checkpointed -
            # which is the whole point of item 7: a SIGTERM would have killed
            # the turn wherever it was and lost it back to that same checkpoint,
            # only messily and with a traceback.
            logger.info("Run %s stopped at a stage boundary after cancellation", run_id)
            await self._finish_cancelled(record)
            return
        except Exception as exc:
            # The full traceback goes to the log, keyed by correlation id. Only a
            # short message reaches the API, because run.error is rendered in the
            # browser and a traceback leaks paths, versions and module layout.
            # A provider out of quota is not a failure of the work: the run waits
            # for a person, as at its spending ceiling, and resumes from here.
            parked = out_of_quota(exc)
            if parked:
                logger.warning("Run %s is waiting: its model provider is out of quota", run_id)
            else:
                logger.exception("Run %s failed", run_id)
            record.status = BUDGET_PAUSE_STATUS if parked else self._status_after_failure(record)
            record.error = _explain_failure(exc)
            record.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist(record)
            await self.event_bus.publish(
                run_id,
                RunEvent(
                    run_id=run_id,
                    sequence=await self.event_bus.next_sequence(run_id),
                    stage=record.current_stage,
                    event_type="error",
                    message=f"Run {'paused' if parked else 'failed'}: {record.error}",
                ),
            )
            await self.event_bus.close(run_id)

    async def _handle_state(
        self,
        record: RunRecord,
        graph: Any,
        state: dict[str, Any],
        trace_meta: dict[str, Any],
    ) -> None:
        """Interpret the state the graph returned and settle the run's status.

        Auto-approval is the one case that legitimately loops, and it is bounded
        by MAX_GATES with a real re-invoke on each pass.
        """
        run_id = record.run_id
        # Each paused stage's auto-approvals, for its gate budget and its loop
        # check (`_GateCount`). A stage's counts go when it has nothing paused,
        # so a long but progressing run is unaffected.
        gate_counts: dict[str, _GateCount] = {}
        # The decision given to a queued parallel pause, by stage, with the
        # pause's queue time - so a pause seen twice is answered once.
        answered: dict[str, tuple[Any, dict[str, Any]]] = {}
        # Consecutive re-invokes that returned the same stage without running
        # anything. Distinct from `repeats`, which counts *gates*; this counts
        # rounds where the graph did not even reach one.
        stalled_at_stage = 0
        # The stage currently being timed, and when it started. Stage duration
        # is observed on transition, so this is carried across the loop's
        # iterations rather than measured per iteration.
        stage_timed_at: dict[str, object] = {}

        for _ in range(MAX_GATES):
            stage = state.get("stage", "")
            self._update_record(record, state)
            # A stage transition is the moment the previous stage's duration is
            # known, so the observation is made here rather than in the graph.
            # Timing starts when a stage is first seen and ends when a different
            # one replaces it; a stage that returns several times in a row
            # (auto-approval loops) accumulates one observation per pass, which
            # is what a histogram of stage cost should show. See plan-part3 §3.1.
            if stage != stage_timed_at.get("stage"):
                _record_stage_duration(stage_timed_at)
                stage_timed_at = {"stage": stage, "started_at": time.monotonic()}

            narration, narrated_status = _stage_narration(
                stage, auto_approve=bool(record.auto_approve)
            )

            await self.event_bus.publish(
                run_id,
                RunEvent(
                    run_id=run_id,
                    sequence=await self.event_bus.next_sequence(run_id),
                    stage=stage,
                    event_type="stage_change",
                    message=narration,
                    metadata=redact_metadata({"status": narrated_status}),
                ),
            )

            if self.run_store.is_cancel_requested(run_id):
                await self._finish_cancelled(record)
                return

            if stage in ("complete", "failed"):
                record.status = "completed" if stage == "complete" else "failed"
                # A failed run must never be recorded with nothing to say. The
                # graph's `failed_node` names the route it came from, and this is
                # the second line of defence for any path that reaches here
                # without one - one run was stored with a null error, and
                # nothing in the row, the events or the log said why.
                record.error = state.get("error") or (
                    None if stage == "complete" else
                    "The run failed and no reason reached the run record. Its last "
                    "stage and its transcript are what remain to go on."
                )
                record.updated_at = datetime.now(timezone.utc).isoformat()
                self._persist(record)
                await asyncio.to_thread(self._archive_artifacts, record)
                await asyncio.to_thread(self._prune_scratch)
                await self.event_bus.publish(
                    run_id,
                    RunEvent(
                        run_id=run_id,
                        sequence=await self.event_bus.next_sequence(run_id),
                        stage=stage,
                        event_type="complete" if stage == "complete" else "error",
                        message=record.error or "Run completed successfully.",
                    ),
                )
                await self.event_bus.close(run_id)
                forget_run(run_id)
                return

            # The spending ceiling, checked at the stage boundary. After the
            # terminal check, so a run that has already finished is never parked
            # for a bill it is not going to add to, and after the cancel check,
            # because an operator who asked for a stop should get a stop rather
            # than a question. See plan-part3 §5.2.
            over_budget, spent = _budget_exceeded(run_id)
            if over_budget:
                record.status = BUDGET_PAUSE_STATUS
                record.updated_at = datetime.now(timezone.utc).isoformat()
                self._persist(record)
                summary = spent.summary()
                partial = (
                    ""
                    if spent.fully_priced
                    else (
                        f" This is a partial total: {spent.unpriced_requests} of "
                        f"{spent.successful_requests} model calls used a model with no "
                        f"published rate ({', '.join(sorted(spent.unpriced_models)) or 'unknown'}), "
                        "so the real spend is higher than the figure above."
                    )
                )
                message = (
                    f"Paused at ${spent.usd:.2f}, which has reached the "
                    f"MAX_RUN_COST_USD ceiling of ${_max_run_cost_usd():.2f}, across "
                    f"{spent.successful_requests} model calls and "
                    f"{spent.total_tokens:,} tokens.{partial}\n\n"
                    "The run is intact and paused at a stage boundary - nothing has "
                    "failed. Raise MAX_RUN_COST_USD and resume to continue, or cancel "
                    "it. Resuming without raising the ceiling pauses again at the next "
                    "stage boundary, because the spend that triggered this does not go "
                    "down."
                )
                await self.event_bus.publish(
                    run_id,
                    RunEvent(
                        run_id=run_id,
                        sequence=await self.event_bus.next_sequence(run_id),
                        stage=stage,
                        event_type="budget_pause",
                        message=message,
                        metadata=redact_metadata(summary),
                    ),
                )
                logger.warning("Run %s paused at its cost ceiling: %s", run_id, message)
                return

            if stage.startswith(APPROVAL_PAUSE_PREFIX):
                approval = state.get("pending_approval")
                if record.auto_approve:
                    # Every pause this resume can answer: the surfaced one and,
                    # in a parallel fan-out, every pause queued behind it - so
                    # the workers go on together instead of one per superstep.
                    # Each is counted against its own stage's gate budget and
                    # loop check, exactly as a lone pause always was.
                    batch: list[tuple[str, Any, Any]] = [
                        (stage.removeprefix(APPROVAL_PAUSE_PREFIX), approval, None)
                    ]
                    for queued_stage, pause in queued_parallel_pauses(state).items():
                        batch.append((queued_stage, pause.get("pending_approval"), pause.get("queued_at")))
                    # A stage with nothing paused has finished: its counts go,
                    # as they always did when the stage changed. One stage at a
                    # time - linear mode, or a fan-out down to its last worker -
                    # is exactly the old reset.
                    live = {name for name, _, _ in batch}
                    for name in list(gate_counts):
                        if name not in live:
                            gate_counts.pop(name, None)
                            answered.pop(name, None)
                    decisions: dict[str, dict[str, Any]] = {}
                    for name, pending, queued_at in batch:
                        remembered = answered.get(name)
                        if queued_at is not None and remembered and remembered[0] == queued_at:
                            # The same pause, not yet consumed: the same answer,
                            # not counted a second time.
                            decisions[name] = remembered[1]
                            continue
                        paused_stage = f"{APPROVAL_PAUSE_PREFIX}{name}"
                        await self.event_bus.publish(
                            run_id,
                            RunEvent(
                                run_id=run_id,
                                sequence=await self.event_bus.next_sequence(run_id),
                                stage=paused_stage,
                                event_type="approval_auto",
                                message=f"Auto-approved: {getattr(pending, 'notes', None) or 'artifact write'}",
                                metadata=redact_metadata(_approval_metadata(pending)),
                            ),
                        )
                        count = gate_counts.setdefault(name, _GateCount())
                        verdict, signature = count.observe(pending)
                        if verdict == "deny":
                            what = _what_was_asked_for(signature)
                            await self.event_bus.publish(
                                run_id,
                                RunEvent(
                                    run_id=run_id,
                                    sequence=await self.event_bus.next_sequence(run_id),
                                    stage=paused_stage,
                                    event_type="approval_denied",
                                    message=f"Denied a repeated request: {what}",
                                ),
                            )
                            decision = reject_write_decision(
                                f"Denied. You have asked for this same thing "
                                f"{MAX_IDENTICAL_GATES + 1} times in a row ({what}) and "
                                "nothing has changed between the attempts, so it will be "
                                "denied again. It is already saved if it was ever going to "
                                "be. Stop repeating it and return your structured response "
                                "now, with whatever you have - put anything you could not "
                                "do in `blockers`."
                            )
                        elif verdict == "fail":
                            record.status = "failed"
                            record.error = _gate_failure_message(name, count, signature)
                            record.updated_at = datetime.now(timezone.utc).isoformat()
                            self._persist(record)
                            await self.event_bus.publish(
                                run_id,
                                RunEvent(
                                    run_id=run_id,
                                    sequence=await self.event_bus.next_sequence(run_id),
                                    stage=paused_stage,
                                    event_type="error",
                                    message=record.error,
                                ),
                            )
                            await self.event_bus.close(run_id)
                            return
                        else:
                            decision = approve_write_decision()
                        decisions[name] = decision
                        if queued_at is not None:
                            answered[name] = (queued_at, decision)

                    surfaced = batch[0][0]
                    state = await asyncio.to_thread(
                        resume_pending_approval, graph, record.thread_id,
                        decisions.pop(surfaced), metadata=trace_meta, run_id=run_id,
                        queued_decisions=decisions or None,
                    )
                    continue

                record.status = "waiting_for_approval"
                record.updated_at = datetime.now(timezone.utc).isoformat()
                self._persist(record)
                await self.event_bus.publish(
                    run_id,
                    RunEvent(
                        run_id=run_id,
                        sequence=await self.event_bus.next_sequence(run_id),
                        stage=stage,
                        event_type="approval_request",
                        message=f"Approval required: {approval.notes if approval else 'artifact write'}",
                        metadata=redact_metadata(_approval_metadata(approval)),
                    ),
                )
                return

            if stage.startswith(REVIEW_PAUSE_PREFIX):
                record.status = "waiting_for_review"
                record.updated_at = datetime.now(timezone.utc).isoformat()
                self._persist(record)
                review_point = stage.removeprefix(REVIEW_PAUSE_PREFIX)
                review = state.get("pending_review")
                await self.event_bus.publish(
                    run_id,
                    RunEvent(
                        run_id=run_id,
                        sequence=await self.event_bus.next_sequence(run_id),
                        stage=stage,
                        event_type="review_request",
                        message=f"Review open: {review_point}",
                        metadata=redact_metadata({
                            "review_point": review_point,
                            "artifact_id": review.artifact_id if review else "",
                            "revision": review.revision if review else 0,
                        }),
                    ),
                )
                return

            # A stage that is neither terminal nor a pause means the graph
            # returned mid-flight. Re-invoke to make progress.
            #
            # `graph.invoke(None, ...)` only runs something when the thread has a
            # task pending. A checkpoint written with values but no scheduled
            # node - which `update_state` produces unless it is told `as_node` -
            # has none, so this returns the same state forever. Bounded only by
            # MAX_GATES, that spun 1000 times in five seconds and then reported
            # "Stopped after 1000 automatic approvals", when not one approval had
            # happened. Catching it here costs two iterations and says what is
            # actually wrong.
            previous_stage = stage
            state = await asyncio.to_thread(graph.invoke, None, _resume_config(record.thread_id, trace_meta))
            if state.get("stage", "") == previous_stage:
                stalled_at_stage += 1
            else:
                stalled_at_stage = 0
            if stalled_at_stage >= MAX_IDLE_REINVOKES:
                record.status = "failed"
                record.error = (
                    f"The graph returned at stage '{previous_stage}' without running "
                    f"anything, {stalled_at_stage + 1} times in a row. The checkpoint has "
                    "no pending work to resume, so re-invoking cannot move it. This "
                    "usually means the state was edited without scheduling a node to act "
                    "on it. Clone the run, or set the stage through a node that routes "
                    "onward."
                )
                record.updated_at = datetime.now(timezone.utc).isoformat()
                self._persist(record)
                await self.event_bus.publish(
                    run_id,
                    RunEvent(
                        run_id=run_id,
                        sequence=await self.event_bus.next_sequence(run_id),
                        stage=previous_stage,
                        event_type="error",
                        message=record.error,
                    ),
                )
                await self.event_bus.close(run_id)
                return

        # Reaching here means the auto-approval loop ran out of rounds. This is
        # the one failure an unattended run is most likely to hit, and it used
        # to be recorded silently: the row said "failed" while no event was
        # published and the stream was never closed, so a UI watching the run
        # simply waited forever. Report it like any other terminal state.
        record.status = "failed"
        record.error = (
            f"Stopped after {MAX_GATES} automatic approvals without finishing. "
            "Raise WORKFLOW_MAX_GATES if this run legitimately needs more, or "
            "inspect the log for a stage that is repeating."
        )
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(record)
        await self.event_bus.publish(
            run_id,
            RunEvent(
                run_id=run_id,
                sequence=await self.event_bus.next_sequence(run_id),
                stage=record.current_stage,
                event_type="error",
                message=record.error,
            ),
        )
        await self.event_bus.close(run_id)

    def _archive_artifacts(self, record: RunRecord) -> None:
        """Push this run's produced files to object storage, if configured.

        Runs once, when the run reaches a terminal stage. Two reasons this is
        worth doing at all: the workspace volume is the only copy that exists,
        and the API serves downloads by reading the workspace - which is a
        different disk from this worker's as soon as there is more than one
        node. Failures are logged, never raised: the run is finished and its
        files are on disk, so a storage outage must not turn a completed run
        into a failed one.
        """
        if not record.repo_root:
            return
        try:
            from app.server.object_store import archive_directory
            from app.tools.repository import list_repository_files

            workspace = Path(record.repo_root)
            if not workspace.is_dir():
                return
            # The same pruned listing the status page shows, so what is archived
            # is exactly what the run reports as its artifacts.
            relative = list_repository_files(workspace)
            stored = archive_directory(
                f"runs/{record.run_id}", workspace, relative_paths=relative
            )
            logger.info("Archived %d artifact(s) for run %s", stored, record.run_id)
        except Exception:  # noqa: BLE001 - archiving is never load-bearing
            logger.warning("Could not archive artifacts for run %s", record.run_id, exc_info=True)

    def _prune_scratch(self) -> None:
        """Age out the journal and the compaction context store.

        Run at a terminal stage because that is a moment this worker is already
        doing filesystem work and nothing is waiting on it. Both trees live
        under `DATA_DIR`, which is one shared volume across the API and every
        worker, and neither had any retention: the journal grows by one >50 KB
        file per truncated stream, the context store by one evicted-history file
        per inner-thread attempt.

        Deliberately age-based rather than run-scoped - two runs share the
        per-agent context directories under worker concurrency, so nothing here
        may key off the run that happens to have just finished. Failures are
        logged, never raised: the run is over and its artifacts are safe.
        """
        try:
            from app.agents.context_store import prune as prune_context
            from app.tools.journal import prune as prune_journal

            removed = prune_journal() + prune_context()
            if removed:
                logger.info("Pruned %d expired scratch file(s)", removed)
        except Exception:  # noqa: BLE001 - cleanup is never load-bearing
            logger.warning("Could not prune scratch storage", exc_info=True)

    def _resume_means_answering_own_gate(self, record: RunRecord) -> bool:
        """Whether resuming this run should answer its approval gate itself.

        An unattended run that stopped while parked on its own gate has nobody
        to clear it. `submit_approval` refuses the run for being unattended
        ("there is nothing to decide"), and `resume_failed_run` refuses it for
        being parked ("waiting for a decision, not a retry") - so between them
        the run had no way forward at all and its work could only be abandoned.

        Answering the gate is exactly what this run does for itself every other
        time it reaches one. Doing it here too is not a special case so much as
        the absence of one.

        Read from `current_stage` rather than the checkpoint deliberately: it is
        the same field `_status_after_failure` uses to decide which route the UI
        offers, so the route offered and the route taken cannot disagree.
        """
        return bool(record.auto_approve) and (record.current_stage or "").startswith(
            APPROVAL_PAUSE_PREFIX
        )

    def _status_after_failure(self, record: RunRecord) -> str:
        """The status to record when an invoke raised.

        A raising node is not checkpointed, so the graph is still parked exactly
        where it was before the attempt - and if that was a human gate, the gate
        is still the only thing that can move the run forward.

        Recording a flat "failed" in that case desynchronised the row from the
        graph: `status` said failed while `current_stage` still said
        `awaiting_approval:...`. The API gates each lifecycle route on `status`
        and the UI picks its controls from it, so the run became unreachable -
        /resume was offered but could not clear an approval gate, and /approve
        was rejected because the status was not `waiting_for_approval`. Keeping
        the status derived from the stage keeps exactly one route open, and it is
        the route that actually works. The error is still surfaced in `error`.
        """
        stage = record.current_stage or ""
        if record.auto_approve and stage.startswith(APPROVAL_PAUSE_PREFIX):
            # An unattended run answers its own approval gates, so `submit_approval`
            # refuses it outright ("there is nothing to decide"). Reporting
            # `waiting_for_approval` here therefore closes the only door it left
            # open: /approve rejects the run for being unattended and /resume
            # rejects it for not being `failed`, so the run is strandable by
            # nothing more than a mid-stage exception. A review gate still needs a
            # human whether or not writes are auto-approved, so only the approval
            # prefix is special-cased.
            return "failed"
        if stage.startswith((APPROVAL_PAUSE_PREFIX, REVIEW_PAUSE_PREFIX)):
            return _api_status(stage)
        return "failed"

    async def _finish_cancelled(self, record: RunRecord) -> None:
        if self.run_store.stop_reason(record.run_id) == "pause":
            await self._finish_paused(record)
            return
        forget_run(record.run_id)
        record.status = "cancelled"
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(record)
        logger.info("Run %s cancelled", record.run_id)
        # Cancellation is a terminal outcome like any other, and leaves the same
        # journal and context files behind. Pruning only on complete/failed meant
        # a deployment where runs are frequently cancelled never pruned at all.
        await asyncio.to_thread(self._prune_scratch)
        await self.event_bus.close(record.run_id)

    async def _finish_paused(self, record: RunRecord) -> None:
        """Record a run stopped by a pause: waiting to be resumed, with everything kept."""
        record.status = "paused"
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(record)
        logger.info("Run %s paused", record.run_id)

    def _update_record(self, record: RunRecord, state: dict[str, Any]) -> None:
        """Sync the run record with the latest graph state."""
        stage = state.get("stage", "")
        meaning, status = _stage_narration(stage, auto_approve=bool(record.auto_approve))
        record.current_stage = stage
        record.stage_meaning = meaning
        record.status = status
        record.error = state.get("error")
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(record)

    def _persist(self, record: RunRecord) -> None:
        """Persist a run record to the store, if one is configured."""
        if self.run_store is not None:
            self.run_store.save(record)


__all__ = [
    "RunRecord",
    "WorkflowRunner",
]
