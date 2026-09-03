from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateRunResponse(BaseModel):
    """Response returned when a new run is created."""
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="Unique identifier for the run.")
    thread_id: str = Field(description="The thread ID associated with the run.")
    status: str = Field(description="The initial status of the run.")
    created_at: datetime = Field(description="Timestamp when the run was created.")


class StartRunRequest(BaseModel):
    """Request to start or resume a run."""
    model_config = ConfigDict(extra="forbid")

    review_policy: dict[str, bool] | None = Field(
        default=None,
        description="Optional overrides for review policies.",
    )
    reviewer: str | None = Field(
        default=None,
        description="The identity of the assigned reviewer.",
    )
    model_override: str | None = Field(
        default=None,
        description="Optional model override for the LLM to use.",
    )


class RunStage(BaseModel):
    """Information about a specific stage in the run."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Name of the stage.")
    meaning: str = Field(description="Human-readable description of what this stage does.")
    started_at: datetime | None = Field(default=None, description="When the stage started.")
    ended_at: datetime | None = Field(default=None, description="When the stage ended.")
    status: str = Field(description="Current status of the stage.")
    duration_seconds: float | None = Field(default=None, description="Duration of the stage in seconds.")
    retry_count: int = Field(default=0, description="Number of times the stage was retried.")


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
        "paused",
        "failed",
        "cancelled",
        "completed",
    ] = Field(description="Current overarching status of the run.")
    current_stage: str | None = Field(default=None, description="The currently active stage.")
    stage_meaning: str | None = Field(default=None, description="Meaning of the current stage.")
    created_at: datetime = Field(description="Timestamp when the run was created.")
    updated_at: datetime = Field(description="Timestamp when the run was last updated.")
    stages: list[RunStage] = Field(default_factory=list, description="History and status of stages.")
    artifacts: list[ArtifactInfo] = Field(default_factory=list, description="Artifacts produced by the run.")
    reviews: list[ReviewInfo] = Field(default_factory=list, description="Reviews associated with the run.")
    remediation: RemediationInfo | None = Field(default=None, description="Remediation information if applicable.")
    error: str | None = Field(default=None, description="Error message if the run failed.")


class RunSummary(BaseModel):
    """A brief summary of a run."""
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="Unique identifier for the run.")
    status: str = Field(description="Current overarching status of the run.")
    current_stage: str | None = Field(default=None, description="The currently active stage.")
    created_at: datetime = Field(description="Timestamp when the run was created.")
    document_name: str | None = Field(default=None, description="Name of the document associated with the run.")


class RunListResponse(BaseModel):
    """Response containing a list of run summaries."""
    model_config = ConfigDict(extra="forbid")

    runs: list[RunSummary] = Field(description="List of run summaries.")


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


class ReviewDecisionRequest(BaseModel):
    """Request to submit a review decision."""
    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "changes", "skip"] = Field(description="The review decision.")
    comment: str | None = Field(default=None, description="Comment detailing the decision.")


class EventResponse(BaseModel):
    """Response containing events for polling clients."""
    model_config = ConfigDict(extra="forbid")

    events: list[dict] = Field(description="List of serialized events.")
    cursor: int = Field(description="Sequence cursor for fetching subsequent events.")


class SpinnerResponse(BaseModel):
    """Response containing spinner status."""
    model_config = ConfigDict(extra="forbid")

    stage: str = Field(description="The current stage.")
    stage_meaning: str = Field(description="Meaning of the current stage.")
    last_updated: datetime = Field(description="When the spinner was last updated.")
    is_terminal: bool = Field(description="Whether the current state is terminal.")
