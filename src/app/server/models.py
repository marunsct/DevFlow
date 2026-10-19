from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RewindRequest(BaseModel):
    """Which point of a run's history to rewind it to (`GET /runs/{id}/rewind-points`)."""
    model_config = ConfigDict(extra="forbid")

    checkpoint_id: str = Field(min_length=1, max_length=200, description="The checkpoint before the stage.")


class CreateRunResponse(BaseModel):
    """Response returned when a new run is created."""
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="Unique identifier for the run.")
    thread_id: str = Field(description="The thread ID associated with the run.")
    status: str = Field(description="The initial status of the run.")
    created_at: datetime = Field(description="Timestamp when the run was created.")


class WorkspaceSource(BaseModel):
    """Where a run's workspace content comes from.

    Two scenarios use this platform. Greenfield - no existing code, the agents
    create it - is the default and needs nothing here. Brownfield - adding
    features to something that already exists - needs that code materialised
    into the workspace before the first agent reads it.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["empty", "git", "archive"] = Field(
        default="empty",
        description="empty: greenfield. git: clone a repository. archive: extract an upload.",
    )
    url: str | None = Field(
        default=None, max_length=2048,
        description="Repository URL, for type=git. HTTPS unless the operator widened it.",
    )
    ref: str | None = Field(
        default=None, max_length=255,
        description="Branch or tag to clone, for type=git. Defaults to the remote's HEAD.",
    )
    token: str | None = Field(
        default=None, max_length=512, repr=False,
        description=(
            "Access token for a private repository, for type=git. Used for this "
            "clone only: it is never written to the run record, the audit log or "
            "the Celery broker."
        ),
    )
    depth: int = Field(
        default=1, ge=0, le=1000,
        description="Clone depth; 0 for full history. Shallow by default - the agents need the code, not the history.",
    )
    upload_id: str | None = Field(
        default=None, max_length=255,
        description="Identifier returned by the codebase upload endpoint, for type=archive.",
    )


class CodebaseUploadResponse(BaseModel):
    """Response after storing a codebase archive for a run."""

    model_config = ConfigDict(extra="forbid")

    upload_id: str = Field(description="Pass this as WorkspaceSource.upload_id when starting the run.")
    original_name: str = Field(description="The archive's original filename.")
    file_size_bytes: int = Field(description="Stored size in bytes.")


class StartRunRequest(BaseModel):
    """Request to start a run.

    Credentials are deliberately absent. They used to be accepted here, which put
    provider API keys into request bodies and access logs; the worker now
    resolves them from its own environment or the secret store.

    ``artifact_directory`` is gone for the same class of reason: it named a
    server path that became the repository root for every agent tool and the
    sandbox bind mount, so a caller could point the whole run at any directory on
    the host. A label is accepted instead, and the server derives the path.
    """

    model_config = ConfigDict(extra="forbid")

    review_policy: dict[str, bool] | None = Field(
        default=None, description="Which optional human review gates to enable."
    )
    reviewer: str | None = Field(default=None, description="Identity recorded on review decisions.")
    llm_provider: str | None = Field(default=None, description="Override the provider for this run.")
    openai_base_url: str | None = Field(default=None, description="Override the OpenAI-compatible base URL.")
    model_name: str | None = Field(default=None, description="Override the model for this run.")
    workspace_label: str | None = Field(
        default=None,
        max_length=48,
        description="Optional human-readable label for this run's workspace directory.",
    )
    allow_subdirectories: bool = Field(
        default=True, description="Whether agents may work in subdirectories of the workspace."
    )
    source: WorkspaceSource | None = Field(
        default=None,
        description="Seed the workspace from an existing codebase. Omit for a greenfield run.",
    )
    delivery_mode: Literal["fast", "thorough"] | None = Field(
        default=None,
        description=(
            "Fast: fewer, leaner stages. Thorough: every stage in full. Omit to keep what the "
            "run was registered with, else the deployment's default."
        ),
    )
    use_frontier_model: bool | None = Field(
        default=None,
        description=(
            "Whether stages that need judgement (specification, reviews, escalated fixes) use the "
            "frontier model. False keeps every stage on the build model. Omit for the frontier "
            "model as configured."
        ),
    )
    approval_timeout_minutes: int | None = Field(
        default=None, ge=1, le=10_080,
        description=(
            "Minutes a gate that asks a person (an approval or a review) waits before it is approved "
            "automatically. Omit to wait for the person however long it takes."
        ),
    )
    auto_approve: bool | None = Field(
        default=None,
        description=(
            "Approve artifact writes automatically. Does not bypass execution gates. "
            "Omit to keep whatever the run was registered with - which is what a clone "
            "of an unattended run needs."
        ),
    )


class RunStage(BaseModel):
    """Information about a specific stage in the run."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Name of the stage.")
    meaning: str = Field(
        default="",
        description=(
            "Human-readable description of what this stage does. Empty until the "
            "stage publishes one: a stage whose first event is a tool call has no "
            "narration yet, and requiring one here took the whole run-detail "
            "endpoint down with a 500."
        ),
    )
    started_at: datetime | None = Field(default=None, description="When the stage started.")
    ended_at: datetime | None = Field(default=None, description="When the stage ended.")
    status: str = Field(description="Current status of the stage.")
    duration_seconds: float | None = Field(default=None, description="Duration of the stage in seconds.")
    retry_count: int = Field(
        default=0,
        description=(
            "Times the stage started over without having produced its output. "
            "An approval is not a retry: a gated stage returns to itself after "
            "every approval, and counting those told operators a run with two "
            "retries had sixty-six."
        ),
    )
    approval_count: int = Field(
        default=0, description="Approvals this stage passed through - progress, not repetition."
    )
    sprint: int = Field(
        default=0,
        description=(
            "Which sprint this stage belongs to; 0 is the planning that precedes "
            "the first. Stage names recur every sprint, so this is what makes an "
            "entry identifiable."
        ),
    )


class ArtifactInfo(BaseModel):
    """Information about an artifact produced during a run."""
    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Path to the artifact.")
    kind: str = Field(description="Type of the artifact.")
    revision: int = Field(description="Revision number of the artifact.")
    created_by: str = Field(description="The entity that created the artifact.")
    stage: str = Field(description="The stage that produced the artifact.")


class ReviewInfo(BaseModel):
    """Information about a review performed during a run."""
    model_config = ConfigDict(extra="forbid")

    point: str = Field(description="The review point identifier.")
    status: str = Field(description="Current status of the review.")
    reviewer: str = Field(description="Identity of the reviewer.")
    revision: int = Field(description="The revision being reviewed.")
    comments: str | None = Field(default=None, description="Reviewer comments.")
    updated_at: datetime = Field(description="Timestamp when the review was last updated.")


class RemediationInfo(BaseModel):
    """Information about remediation efforts within a run."""
    model_config = ConfigDict(extra="forbid")

    attempt: int = Field(description="Current remediation attempt number.")
    max_attempts: int = Field(description="Maximum allowed remediation attempts.")
    escalated: bool = Field(description="Whether the remediation has been escalated.")
    defect_count: int = Field(description="Number of defects found.")
    test_runs: int = Field(description="Number of test runs performed.")
    open_defects: int = Field(default=0, description="Defects found and still open.")


class SprintDefectView(BaseModel):
    """One defect of a sprint's latest attempt, as its summary lists it."""
    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="open, fixed or accepted_risk.")
    description: str = Field(description="What is wrong.")
    owner: str = Field(description="Who fixes it.")


class SprintView(BaseModel):
    """One sprint, from the attempts the engine renders its summary document from (plan BG.6)."""
    model_config = ConfigDict(extra="forbid")

    number: int = Field(description="The sprint's place in the plan, from 1.")
    planned_total: int = Field(description="How many sprints the plan has.")
    goal: str = Field(description="The sprint plan's goal for this sprint.")
    status: str = Field(description="The latest attempt's status: Completed, Failed or another the engine records.")
    failure_reason: str = Field(default="", description="Why the latest attempt failed; '' when it did not.")
    attempts: int = Field(description="How many times this sprint was attempted. More than one is a re-run, not another sprint.")
    planned: list[str] = Field(default_factory=list, description="What the sprint promised, from the plan.")
    features: list[str] = Field(default_factory=list, description="What the latest attempt implemented.")
    test_cases: int | None = Field(default=None, description="Test cases measured at the end of the latest attempt, or null when none were.")
    cases_passed: int = Field(default=0, description="Of those, passed.")
    cases_failed: int = Field(default=0, description="Of those, failed.")
    test_rounds: int = Field(default=0, description="Test rounds the latest attempt ran.")
    total_bugs: int = Field(default=0, description="Defects found in the latest attempt.")
    fixed_bugs: int = Field(default=0, description="Of those, fixed.")
    open_bugs: int = Field(default=0, description="Of those, not fixed.")
    defects: list[SprintDefectView] = Field(default_factory=list, description="The latest attempt's defects.")
    attempt_history: list[str] = Field(default_factory=list, description="One line per attempt, when there was more than one.")


class BriefPreviewRequest(BaseModel):
    """A brief, before any run exists, to preview what it will be held to."""
    model_config = ConfigDict(extra="forbid")

    brief: str = Field(max_length=400_000, description="The brief's text, as written or read from its files.")


class PreviewCriterion(BaseModel):
    """One acceptance criterion as the run will number it."""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="AC-1, AC-2, ...")
    text: str = Field(description="The behaviour, in the brief's own words.")


class BriefPreview(BaseModel):
    """The acceptance criteria a brief gives a run, read without a model call (plan BG.10)."""
    model_config = ConfigDict(extra="forbid")

    criteria: list[PreviewCriterion] = Field(default_factory=list, description="AC-1..n from the brief, in its order.")
    from_brief: bool = Field(
        description="Whether the brief lists them: with fewer than two, the run draws them from its product intake instead."
    )


class StageUsage(BaseModel):
    """One stage's time, tokens and failures, from the run's transcript (plan BG.7)."""
    model_config = ConfigDict(extra="forbid")

    stage: str = Field(description="The stage's name; a stage that ran more than once is one row.")
    wall_seconds: float = Field(description="From the stage's first record to its last.")
    model_seconds: float = Field(description="Time spent waiting on model replies.")
    model_calls: int = Field(description="Model replies.")
    input_tokens: int = Field(description="Input tokens sent.")
    cached_tokens: int = Field(description="Of those, tokens the server had cached.")
    output_tokens: int = Field(description="Output tokens, reasoning included.")
    lost_replies: int = Field(description="Replies cut off at the output limit with no text and no call kept.")
    tool_calls: int = Field(description="Tool calls made.")
    tool_failures: int = Field(description="Tool calls that failed or were refused.")
    redundant_reads: int = Field(description="Reads answered with 'you already have this'.")


class CallUsage(BaseModel):
    """One model call: when it ended, which stage made it, its tokens, and how long it took (plan BG.15)."""
    model_config = ConfigDict(extra="forbid")

    at: datetime = Field(description="When the reply arrived.")
    stage: str = Field(description="The stage that made the call.")
    input_tokens: int = Field(description="Tokens sent: how full the context was.")
    output_tokens: int = Field(description="Tokens the reply had, reasoning included.")
    seconds: float = Field(description="From the request to the reply.")


class RunUsage(BaseModel):
    """A run's usage by stage, in the order the stages first ran, and its calls of the last hour."""
    model_config = ConfigDict(extra="forbid")

    stages: list[StageUsage] = Field(default_factory=list, description="One row per stage; empty before the transcript has any.")
    recent_calls: list[CallUsage] = Field(
        default_factory=list, description="The model calls of the run's last hour of calls, oldest first, at most 300."
    )


class SprintsResponse(BaseModel):
    """A run's sprints, in plan order; only those attempted so far."""
    model_config = ConfigDict(extra="forbid")

    sprints: list[SprintView] = Field(default_factory=list, description="The sprints attempted so far.")


class RunCostSummary(BaseModel):
    """What a run has spent on model calls, and how much of it was priced.

    `estimated_cost_usd` on its own is a trap: a run whose model is absent from
    the price table would report `0.0`, which reads as "this was free" rather
    than "this was not measured". `fully_priced` and `unpriced_requests` are
    what tell those two apart, so they are not optional extras here.
    """

    model_config = ConfigDict(extra="forbid")

    estimated_cost_usd: float = Field(description="Spend on calls that could be priced.")
    total_tokens: int = Field(description="Tokens across every call, priced or not.")
    prompt_tokens: int = Field(description="Input tokens across every call.")
    completion_tokens: int = Field(description="Output tokens across every call.")
    successful_requests: int = Field(description="Model calls that completed.")
    priced_requests: int = Field(description="Calls charged at a known rate.")
    unpriced_requests: int = Field(
        description="Calls whose model had no published rate; their cost is unknown, not zero."
    )
    unpriced_models: list[str] = Field(
        default_factory=list, description="Model ids that had no rate."
    )
    fully_priced: bool = Field(
        description="False when any call went unpriced, so the total is partial."
    )
    prices_as_of: str = Field(description="Month the built-in price table was current.")


class SteeringNote(BaseModel):
    """The owner's direction to a running run, carried by its next model calls."""

    text: str = Field(..., min_length=1, max_length=2000)
    scope: Literal["run", "next_stage"] = Field(
        default="run", description="For the rest of the run, or for the one stage that is working when it is first read."
    )


class RunStatusResponse(BaseModel):
    """Comprehensive status of a run."""
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="Unique identifier for the run.")
    thread_id: str = Field(description="The thread ID associated with the run.")
    status: Literal[
        "created",
        "running",
        "waiting_for_approval",
        "waiting_for_review",
        # Parked at `MAX_RUN_COST_USD`. Listed here and not only in the runner,
        # because a status this model does not accept makes *reading* the run
        # fail with a `ValidationError` - the run is fine and the page that would
        # show why it stopped is the thing that breaks. This is the shape of the
        # `approval_denied` defect that `test_event_types_are_registered` exists
        # to prevent, on the status field rather than the event field.
        "waiting_for_budget",
        "paused",
        "failed",
        "cancelled",
        "completed",
    ] = Field(description="Current overarching status of the run.")
    current_stage: str | None = Field(default=None, description="The currently active stage.")
    stage_meaning: str | None = Field(default=None, description="Meaning of the current stage.")
    created_at: datetime = Field(description="Timestamp when the run was created.")
    updated_at: datetime = Field(description="Timestamp when the run was last updated.")
    stages: list[RunStage] = Field(default_factory=list, description="Stage history, when available.")
    artifacts: list[ArtifactInfo] = Field(default_factory=list, description="Artifacts produced by the run.")
    reviews: list[ReviewInfo] = Field(default_factory=list, description="Reviews associated with the run.")
    remediation: RemediationInfo | None = Field(default=None, description="Remediation information if applicable.")
    error: str | None = Field(default=None, description="Error message if the run failed.")
    non_deliverable: str = Field(
        default="",
        description=(
            "What the workspace's NON-DELIVERABLE marker says, or '' when the "
            "workspace is marked deliverable. A terminal state other than a "
            "clean release writes it into the workspace root (Initiative J.6)."
        ),
    )
    gate_deadline: datetime | None = Field(
        default=None,
        description=(
            "When a gate that is waiting for a person approves itself (the run's approval timeout), "
            "or null when nothing waits or the gate waits for the person however long it takes."
        ),
    )
    approval_timeout_minutes: int | None = Field(
        default=None, description="The run's approval timeout in minutes; null waits for the person."
    )
    completion_gaps: list[str] = Field(
        default_factory=list,
        description=(
            "What this release knew it did not prove: deferred criteria, "
            "problems the suite was locked with, an unproven setup (Initiative "
            "J.4). Empty on a completed run that proved everything it claims; "
            "a completed run with gaps here is never plain 'completed' on any "
            "surface that shows it."
        ),
    )
    delivery_mode: str = Field(
        default="", description="`fast` or `thorough`: how this run delivers, chosen when it started.",
    )
    max_run_tokens: int | None = Field(
        default=None,
        description="The deployment's bound on the tokens a run uses (`MAX_RUN_TOKENS`), or null when none is set.",
    )
    max_run_cost_usd: float | None = Field(
        default=None,
        description="The deployment's ceiling on a run's priced spend (`MAX_RUN_COST_USD`), or null when none is set.",
    )
    use_frontier_model: bool = Field(
        default=True, description="Whether this run uses the frontier model; False is the build model only.",
    )
    auto_approve: bool = Field(
        default=False,
        description=(
            "Whether the run answers its own approval gates (unattended). The UI "
            "needs this to know whether a gate is waiting on a person or will "
            "clear itself, and the wizard uses it to label a paused stage."
        ),
    )
    cost: RunCostSummary | None = Field(
        default=None,
        description=(
            "What this run has spent on model calls so far, when the worker "
            "holding its total is this process. Absent rather than zero when it "
            "is not: a run whose accounting lives in another worker has an "
            "unknown cost, and reporting $0.00 for it would be the fabricated "
            "measurement this field was added to remove."
        ),
    )


# ----------------------------------------------------------------------
# Wizard model
#
# The phase structure of a run - which sprint each stage belongs to, which
# revision of a sprint was rejected and why, how each review ended up - is
# derived here, in one place, from the event history. Before this existed the
# same derivation lived in TypeScript (the wizard view) *and* again in
# `_derive_stages` for the classic timeline: two readers of one truth, free to
# drift apart. The API now hands the browser a finished model and the browser
# only renders it.
# ----------------------------------------------------------------------


class WizardReview(BaseModel):
    """One review point inside a sprint revision."""

    model_config = ConfigDict(extra="forbid")

    point: str = Field(description="Which artifact was reviewed, e.g. 'sprint_review'.")
    revision: int = Field(default=1, description="Revision number the review covered.")
    requested_at: datetime | None = Field(
        default=None, description="When the run paused waiting for a decision."
    )
    outcome: Literal["approved", "changes", "skipped", "pending"] = Field(
        description=(
            "What happened at this review. 'changes' means sent back with a "
            "comment; 'pending' means the run is still waiting for it."
        )
    )
    comment: str | None = Field(
        default=None,
        description="The reviewer's comment - the rejection reason when outcome is 'changes'.",
    )


class WizardNote(BaseModel):
    """One log line that happened while a step was running.

    The wizard shows each step's notes on demand (an expandable list under the
    step), so they travel with the step rather than being re-fetched: the event
    history is already in memory when this model is built, and re-reading it per
    step would be a Redis round trip per render.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Event id - stable key for the UI list.")
    kind: str = Field(
        description=(
            "The event type ('log', 'tool_call', 'agent_message', 'error', ...). "
            "The UI only uses it to pick an icon."
        )
    )
    message: str = Field(description="The line as written for a human to read.")


class WizardStep(BaseModel):
    """One stage entry inside a revision or phase section."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Stage name, pause prefix stripped.")
    title: str = Field(description="Human-readable title for the stage.")
    blurb: str = Field(default="", description="One line on what the stage does.")
    started_at: datetime | None = Field(default=None)
    ended_at: datetime | None = Field(
        default=None, description="None while the step is still in flight."
    )
    status: Literal["done", "active", "waiting", "upcoming", "idle", "error"] = Field(
        description=(
            "'done' once a later step started; 'active' for the step in flight; "
            "'waiting' when the run is paused on it; 'error' if the run stopped "
            "there; 'idle' for a step that has not started (or was cancelled) "
            "- rendered as 'Up next'."
        )
    )
    status_label: str = Field(default="", description="Text for the badge, e.g. 'Working on it'.")
    duration_seconds: float | None = Field(default=None)
    events: list[WizardNote] = Field(
        default_factory=list,
        description=(
            "The log lines that happened while this step ran. The UI renders "
            "them in an expandable list - keeping them here means the wizard is "
            "a pure renderer with nothing left to derive."
        ),
    )


class SprintRevision(BaseModel):
    """One pass through a sprint. A rejected review starts a new revision of the same sprint."""

    model_config = ConfigDict(extra="forbid")

    number: int = Field(description="1 for the first pass; increments on each rejection.")
    steps: list[WizardStep] = Field(default_factory=list)
    review: WizardReview | None = Field(
        default=None, description="The end-of-sprint review, once one was requested."
    )
    rejection_comment: str | None = Field(
        default=None,
        description=(
            "Why this revision was rejected - the comment that started the next "
            "revision. Present only when a later revision exists."
        ),
    )
    saw_advance: bool = Field(
        default=False,
        description=(
            "The run moved on to the next sprint after this revision (the review "
            "was approved and `sprint_advance` ran). Used to resolve the review's "
            "outcome for runs whose history predates decision events."
        ),
    )


class WizardSection(BaseModel):
    """One phase of the build: intake, design, a sprint, or the final summary."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable identifier, e.g. 'design' or 'sprint-2'.")
    kind: Literal["intake", "design", "sprint", "summary"] = Field(
        description="Which phase this is; the UI renders each kind differently."
    )
    title: str = Field(description="Display name, e.g. 'Sprint 1'.")
    blurb: str = Field(default="", description="One line describing the phase.")
    status: Literal["done", "active", "waiting", "upcoming", "idle"] = Field(
        default="upcoming", description="Phase status in the same vocabulary as steps."
    )
    status_label: str = Field(default="Up next")
    sprint_number: int | None = Field(default=None, description="Set for kind='sprint' sections.")
    revisions: list[SprintRevision] = Field(
        default_factory=list, description="Present for kind='sprint' sections."
    )
    steps: list[WizardStep] = Field(
        default_factory=list,
        description="Steps that belong to the phase itself (intake/design), not a revision.",
    )


class WizardSummary(BaseModel):
    """The numbers the final summary panel reports.

    Every field here is one the panel renders - nothing extra, so the browser
    cannot need to compute a number itself. The counts come from two sources:
    the event walk (reviews and their outcomes) and the graph state (test runs
    and defects live in `remediation`, which the event stream only narrates).
    """

    model_config = ConfigDict(extra="forbid")

    sprints_planned: int | None = Field(
        default=None,
        description=(
            "From the sprint plan artifact, when it exists; None means 'not yet "
            "planned' and the UI falls back to sprints_executed."
        ),
    )
    sprints_executed: int = Field(description="Sprint sections that opened.")
    revisions_total: int = Field(description="All revision passes across all sprints.")
    test_runs: int = Field(
        default=0, description="Test rounds executed - from the remediation cycle in graph state."
    )
    defects_found: int = Field(
        default=0, description="Defects tracked so far - from the remediation cycle in graph state."
    )
    documents_produced: int = Field(default=0, description="Artifacts present for this run.")
    approvals_passed: int = Field(
        default=0, description="Approvals passed across all stages (progress, not retries)."
    )
    reviews_approved: int = Field(description="Reviews answered with approve or skip.")
    reviews_changes: int = Field(description="Reviews answered with 'changes'.")
    reviews_skipped: int = Field(description="Reviews the reviewer skipped.")
    reviews_pending: int = Field(description="Reviews still waiting for an answer.")
    started_at: datetime | None = Field(default=None, description="When the run was created.")
    ended_at: datetime | None = Field(
        default=None, description="When the run reached a terminal state; None while it is going."
    )
    status: str = Field(description="The run's status, same vocabulary as RunStatusResponse.status.")
    status_label: str = Field(default="", description="Plain-English label for that status.")
    error: str | None = Field(default=None, description="Error message when the run stopped.")


class WizardModel(BaseModel):
    """The full phase structure of one run, ready to render."""

    model_config = ConfigDict(extra="forbid")

    sections: list[WizardSection] = Field(
        description="In build order: intake, design, sprints 1..n, final summary."
    )
    summary: WizardSummary = Field(description="Aggregate numbers for the final panel.")
    current_section_id: str | None = Field(
        default=None, description="Which section the run is currently inside, if any."
    )


class RunSummary(BaseModel):
    """A brief summary of a run."""
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="Unique identifier for the run.")
    status: str = Field(description="Current overarching status of the run.")
    current_stage: str | None = Field(default=None, description="The currently active stage.")
    created_at: datetime = Field(description="Timestamp when the run was created.")
    document_names: list[str] = Field(default_factory=list, description="Names of the documents associated with the run.")
    updated_at: datetime | None = Field(default=None, description="When the run last moved.")
    delivery_mode: str | None = Field(default=None, description="fast or thorough.")
    local_only: bool | None = Field(default=None, description="Whether the run was started not to use the frontier model.")
    completion_gaps: int = Field(default=0, description="How many things the release knew it did not prove.")
    criteria_proven: int | None = Field(default=None, description="Acceptance criteria passing in the last measurement, or null before one.")
    criteria_total: int | None = Field(default=None, description="Acceptance criteria of the run, or null before the suite is written.")
    gate_deadline: datetime | None = Field(
        default=None,
        description="When a waiting gate approves itself, or null when nothing waits or it waits for the person.",
    )


class ServerHealth(BaseModel):
    """What the build model's server says of itself, read with one request for its status and never a model call (plan BG.5)."""
    model_config = ConfigDict(extra="forbid")

    hosted: bool = Field(description="The build model is a hosted API, which has no server status to read.")
    answered: bool = Field(description="The server answered its status request (`/props`) when it was read.")
    model: str = Field(default="", description="The model the server holds, from its file name; the configured name otherwise.")
    quantisation: str = Field(default="", description="The quantisation its file name names, such as Q4_K_M; '' when none.")
    slots: int | None = Field(default=None, description="How many requests it serves at once, or null when not reported.")
    slot_context: int | None = Field(default=None, description="Context tokens each request gets, as the server was started, or null.")
    checked_at: datetime = Field(description="When the status was read; it is read again at most once a minute.")
    busy_runs: list[str] = Field(default_factory=list, description="The runs running now, which hold the server's slots.")


class RunListResponse(BaseModel):
    """A page of run summaries."""
    model_config = ConfigDict(extra="forbid")

    runs: list[RunSummary] = Field(description="List of run summaries.")
    total: int = Field(default=0, description="Total runs visible to the caller.")


class ApprovalPayload(BaseModel):
    """Payload for requesting an approval."""
    model_config = ConfigDict(extra="forbid")

    artifact_path: str = Field(description="Path to the artifact requiring approval.")
    content_summary: str = Field(description="Summary of the content to be approved.")
    risk_level: str = Field(description="Assessed risk level.")
    requested_by: str = Field(description="Entity that requested the approval.")
    stage: str = Field(description="Stage where the approval was requested.")


class ApprovalDecisionRequest(BaseModel):
    """Request to submit an approval decision."""
    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "reject"] = Field(description="The approval decision.")
    reason: str | None = Field(default=None, description="Reason for the decision.")


class ReviewPayload(BaseModel):
    """Payload for requesting a review."""
    model_config = ConfigDict(extra="forbid")

    point: str = Field(description="The review point identifier.")
    artifact_id: str = Field(description="Identifier of the artifact to review.")
    revision: int = Field(description="The revision being reviewed.")
    comments: str | None = Field(default=None, description="Existing comments context.")
    available_actions: list[str] = Field(description="List of actions the reviewer can take.")
    document: str | None = Field(
        default=None, description="The workspace path of the document the review is about, when the workflow wrote one."
    )


class ReviewDecisionRequest(BaseModel):
    """Request to submit a review decision."""
    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "changes", "skip"] = Field(description="The review decision.")
    comment: str | None = Field(default=None, description="Comment detailing the decision.")


class SpinnerResponse(BaseModel):
    """Response containing spinner status."""
    model_config = ConfigDict(extra="forbid")

    stage: str = Field(description="The current stage.")
    stage_meaning: str = Field(description="Meaning of the current stage.")
    last_updated: datetime = Field(description="When the spinner was last updated.")
    is_terminal: bool = Field(description="Whether the current state is terminal.")
