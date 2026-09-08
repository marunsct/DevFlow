"""Typed workflow state for the product-development orchestration graph.

This module is the runtime contract layer: every graph node receives or returns
state represented by these models instead of ad-hoc dictionaries. That matters in
agent workflows because a later node should not guess whether "status" is a
string, an enum, or a nested object. By giving each field a semantic meaning and
clear failure behavior, the graph can safely gate stages, approvals, and retries
without a hidden contract between nodes.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# Graph nodes pass this state object from one stage to the next. Enums keep the
# values stable and help prevent tiny typos such as "intake " or "reviewed"
# from silently breaking routing logic.
class WorkflowStage(str, Enum):
    """Lifecycle stages used by the orchestration graph."""

    INTAKE = "intake"
    TOOLS_MODELS = "tools_models"
    ARCHITECTURE = "architecture"
    REVIEW = "review"
    SPRINT_PLANNING = "sprint_planning"
    IMPLEMENTATION = "implementation"
    VALIDATION = "validation"
    COMPLETE = "complete"
    FAILED = "failed"


class ReviewRequestStatus(str, Enum):
    """Current state of a human or automated review request."""

    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    SKIPPED = "skipped"


class ApprovalDecision(str, Enum):
    """Available decisions for a pending human approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class ProductInputMetadata(BaseModel):
    """Normalized metadata about the product brief submitted to the workflow."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        description=(
            "Purpose: human-readable product name. Producer: upload or intake node. "
            "Consumer: PM and architecture roles. Failure meaning: a run cannot be "
            "triaged without a clear product identity."
        ),
    )
    source_path: str = Field(
        ...,
        description=(
            "Purpose: original file location on disk. Producer: document reader or API. "
            "Consumer: traceability and replay. Failure meaning: the input cannot be "
            "referenced or audited later without a source path."
        ),
    )
    source_type: Literal["markdown", "text", "docx"] = Field(
        ...,
        description=(
            "Purpose: normalized document type. Producer: document reader. Consumer: "
            "safe parsing logic. Failure meaning: an unsupported input type should be "
            "rejected before model reasoning."
        ),
    )
    uploaded_by: str = Field(
        ...,
        description=(
            "Purpose: identity of the user or system that supplied the product input. "
            "Producer: web/API layer or CLI. Consumer: audit trails and review routing. "
            "Failure meaning: missing provenance weakens accountability and review."
        ),
    )
    uploaded_at: str = Field(
        ...,
        description=(
            "Purpose: timestamp of upload or intake. Producer: API or CLI. Consumer: "
            "audit and progress UI. Failure meaning: the run has no reliable creation time."
        ),
    )
    file_size_bytes: int | None = Field(
        default=None,
        description=(
            "Purpose: original document size for validation and limit enforcement. "
            "Producer: upload layer. Consumer: document reader and UI. Failure meaning: "
            "oversized files may fail to parse or be truncated unexpectedly."
        ),
    )


class RepositoryContext(BaseModel):
    """Repository facts that are safe to inspect and share across workflow nodes."""

    model_config = ConfigDict(extra="forbid")

    root_path: str = Field(
        ...,
        description=(
            "Purpose: repository root used for safely scoped reads and writes. Producer: "
            "repository inspection tool. Consumer: all downstream role agents. Failure "
            "meaning: no trusted repository boundary exists for file- and tool-scoped work."
        ),
    )
    branch: str = Field(
        ...,
        description=(
            "Purpose: active git branch or working branch. Producer: repository tool. "
            "Consumer: architecture and implementation planning. Failure meaning: branch "
            "alignment is unknown and may produce conflicting artifacts."
        ),
    )
    commit: str = Field(
        ...,
        description=(
            "Purpose: commit SHA used as a reproducible repository state anchor. Producer: "
            "repository tool. Consumer: traceability and debugging. Failure meaning: the "
            "workspace cannot be tied to a known revision."
        ),
    )
    status: str = Field(
        ...,
        description=(
            "Purpose: current repository cleanliness or readiness signal. Producer: repo "
            "inspection layer. Consumer: workflow gating and implementation planning. "
            "Failure meaning: a dirty or partially updated repository should not be treated "
            "as stable."
        ),
    )
    allow_subdirectories: bool = Field(
        default=True,
        description=(
            "Purpose: whether agents are allowed to inspect and modify subdirectories of the repository. "
            "Producer: UI toggle. Consumer: repository tools. Failure meaning: agents may operate "
            "outside the intended scope."
        ),
    )
    dependency_files: list[str] = Field(
        default_factory=list,
        description=(
            "Purpose: files that define the project dependency surface. Producer: repo "
            "inspection. Consumer: tool/model selection and architecture composition. "
            "Failure meaning: the system cannot evaluate compatibility without dependency inputs."
        ),
    )
    entry_points: list[str] = Field(
        default_factory=list,
        description=(
            "Purpose: likely application entry points to understand start-up and runtime. "
            "Producer: repo inspection or project conventions. Consumer: implementation and "
            "deployment planning. Failure meaning: the workflow lacks a trusted startup boundary."
        ),
    )


class ArtifactReference(BaseModel):
    """Reference to a generated artifact managed by the workflow."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        ...,
        description=(
            "Purpose: canonical artifact location inside approved output directories. "
            "Producer: agent or controlled artifact writer. Consumer: UI, reviews, and "
            "resume logic. Failure meaning: the artifact cannot be shown or audited by later stages."
        ),
    )
    kind: Literal["markdown", "json", "text", "yaml", "csv", "binary"] = Field(
        ...,
        description=(
            "Purpose: content type to support reader and renderer selection. Producer: "
            "artifact creator. Consumer: UI and review tools. Failure meaning: a file with "
            "unknown semantics may not render or be versioned correctly."
        ),
    )
    revision: int = Field(
        default=1,
        description=(
            "Purpose: monotonically increasing version for safe overwrite control. Producer: "
            "artifact writer. Consumer: review and rerun logic. Failure meaning: stale artifacts "
            "may overwrite newer content without a revision trail."
        ),
    )
    created_by: str = Field(
        ...,
        description=(
            "Purpose: role or agent responsible for creating the artifact. Producer: "
            "authoring agent. Consumer: accountability and debugging. Failure meaning: there "
            "is no ownership to route follow-up questions or fixes."
        ),
    )
    status: str = Field(
        ...,
        description=(
            "Purpose: lifecycle state such as draft, ready, approved, or rejected. Producer: "
            "role agent or reviewer. Consumer: progress and gating logic. Failure meaning: "
            "a stage may claim completion without a verifiable artifact state."
        ),
    )
    created_at: str | None = Field(
        default=None,
        description=(
            "Purpose: creation timestamp for ordering and auditability. Producer: artifact writer. "
            "Consumer: UI and historical review. Failure meaning: revision history is harder to "
            "reconstruct under pressure."
        ),
    )


class ReviewStatus(BaseModel):
    """State for a review gate attached to a workflow stage or artifact."""

    model_config = ConfigDict(extra="forbid")

    stage: WorkflowStage = Field(
        ...,
        description=(
            "Purpose: stage that requires or produced review. Producer: workflow controller. "
            "Consumer: gating and resume handlers. Failure meaning: review status is not connected "
            "to a workflow stage and may be acted on out of order."
        ),
    )
    status: ReviewRequestStatus = Field(
        ...,
        description=(
            "Purpose: whether review is pending, approved, rejected, or skipped. Producer: "
            "human reviewer or workflow. Consumer: routing and next-step gating. Failure meaning: "
            "work may move forward without a valid approval decision."
        ),
    )
    reviewer: str = Field(
        ...,
        description=(
            "Purpose: reviewer identity or role performing the decision. Producer: UI or workflow. "
            "Consumer: audit trail and follow-up. Failure meaning: no accountable reviewer exists."
        ),
    )
    revision: int = Field(
        ...,
        description=(
            "Purpose: artifact revision under review. Producer: artifact writer. Consumer: "
            "review-specific rerun logic. Failure meaning: the review may reference a stale artifact."
        ),
    )
    updated_at: str = Field(
        ...,
        description=(
            "Purpose: last update time for review status. Producer: review handler. Consumer: "
            "UI, duplicate detection, and stale-submission checks. Failure meaning: review status "
            "cannot be trusted for ordering."
        ),
    )
    comments: list[str] = Field(
        default_factory=list,
        description=(
            "Purpose: reviewer comments or requested changes. Producer: review UI or reviewer. "
            "Consumer: rerun routing and remediation. Failure meaning: requested changes are lost."
        ),
    )
    run_id: str | None = Field(
        default=None,
        description=(
            "Purpose: identifies the workflow run this optional review belongs to. Producer: "
            "workflow controller. Consumer: UI and audit trail. Failure meaning: a review cannot "
            "be tied back to the run that produced the reviewed artifact. Optional so existing "
            "mandatory review-gate usages of this model are unaffected."
        ),
    )
    thread_id: str | None = Field(
        default=None,
        description=(
            "Purpose: identifies the paused LangGraph thread waiting on this review decision. "
            "Producer: workflow controller. Consumer: resume handlers. Failure meaning: the "
            "workflow cannot be resumed after a human submits a review decision."
        ),
    )
    artifact_id: str | None = Field(
        default=None,
        description=(
            "Purpose: identifies which generated artifact this optional review covers. Producer: "
            "artifact writer. Consumer: review UI and revision routing. Failure meaning: a "
            "reviewer cannot tell which artifact their comments apply to."
        ),
    )
    created_at: str | None = Field(
        default=None,
        description=(
            "Purpose: when this review request was first created, distinct from `updated_at`. "
            "Producer: review handler. Consumer: audit trail and staleness checks. Failure "
            "meaning: the review's age and turnaround time cannot be measured."
        ),
    )


class SprintStatus(BaseModel):
    """Current sprint state for the active implementation plan."""

    model_config = ConfigDict(extra="forbid")

    current_sprint: int = Field(
        ...,
        description=(
            "Purpose: ordinal sprint number in the current workflow. Producer: scrum master. "
            "Consumer: technical lead and milestone reviewer. Failure meaning: there is no stable "
            "sprint context for acceptance gates."
        ),
    )
    goal: str = Field(
        ...,
        description=(
            "Purpose: user-facing outcome for the sprint. Producer: scrum master. Consumer: "
            "technical lead, specialists, and reviewers. Failure meaning: the team cannot converge "
            "on a shared sprint objective."
        ),
    )
    status: str = Field(
        ...,
        description=(
            "Purpose: sprint health such as planned, in_progress, blocked, or complete. "
            "Producer: technical lead or scrum master. Consumer: UI and review loops. Failure meaning: "
            "team members cannot tell whether work is ready for testing or blocked."
        ),
    )
    in_scope: list[str] = Field(
        default_factory=list,
        description=(
            "Purpose: explicit scope approved for this sprint. Producer: scrum master. "
            "Consumer: specialists and reviewers. Failure meaning: work may drift outside the architecture."
        ),
    )
    out_of_scope: list[str] = Field(
        default_factory=list,
        description=(
            "Purpose: items deliberately deferred to later work. Producer: scrum master. "
            "Consumer: planning and review. Failure meaning: expectations may be mismanaged."
        ),
    )


class Assumption(BaseModel):
    """Known assumption carried into planning and review."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(
        ...,
        description=(
            "Purpose: assumption being relied on without full evidence. Producer: any role "
            "agent or user. Consumer: architecture review and risk management. Failure meaning: "
            "the decision pipeline is making unsupported claims."
        ),
    )
    owner: str = Field(
        ...,
        description=(
            "Purpose: role or participant accountable for validating the assumption. Producer: "
            "role agent or decision owner. Consumer: clarifying questions and review. Failure meaning: "
            "the assumption can no longer be questioned or validated."
        ),
    )
    confidence: str = Field(
        ...,
        description=(
            "Purpose: confidence label for a decision or assumption. Producer: agent or reviewer. "
            "Consumer: risk and architecture decisions. Failure meaning: the team is acting on an "
            "unqualified assumption."
        ),
    )


class RiskEntry(BaseModel):
    """Project risk with mitigation guidance."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(
        ...,
        description=(
            "Purpose: risk narrative or trigger. Producer: security, architecture, or product roles. "
            "Consumer: reviewers and sprint planning. Failure meaning: a known risk is not surfaced "
            "to decision-makers."
        ),
    )
    severity: str = Field(
        ...,
        description=(
            "Purpose: seriousness level for escalation. Producer: reviewer or role agent. "
            "Consumer: risk triage and release blocking. Failure meaning: critical risk may be hidden."
        ),
    )
    mitigation: str = Field(
        ...,
        description=(
            "Purpose: recommended mitigation or fallback plan. Producer: relevant role agent. "
            "Consumer: technical lead and reviewers. Failure meaning: the workflow has no recovery path."
        ),
    )


class HumanApprovalRequest(BaseModel):
    """Human-in-the-loop approval request issued before a high-impact action."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(
        ...,
        description=(
            "Purpose: unique request identifier for resume and audit tracking. Producer: workflow. "
            "Consumer: approval handlers and UI. Failure meaning: the pending decision cannot be tied to a request."
        ),
    )
    stage: str = Field(
        ...,
        description=(
            "Purpose: workflow stage that is waiting for approval. Producer: workflow or agent. "
            "Consumer: routing and interruption logic. Failure meaning: the approval request is disconnected from the action."
        ),
    )
    artifact_path: str = Field(
        ...,
        description=(
            "Purpose: target artifact or file path that needs approval. Producer: controlled writer. "
            "Consumer: human approver and resume engine. Failure meaning: the approver cannot verify what will change."
        ),
    )
    risk_level: str = Field(
        ...,
        description=(
            "Purpose: risk level to assist prioritization. Producer: workflow or agent. Consumer: UI and approver triage. Failure meaning: the approver may make a high-risk decision without context."
        ),
    )
    requested_by: str = Field(
        ...,
        description=(
            "Purpose: role or system that requested the approval. Producer: workflow. Consumer: auditing and accountability. Failure meaning: ownership is unclear."
        ),
    )
    decision: ApprovalDecision = Field(
        ...,
        description=(
            "Purpose: result of the approval decision. Producer: human reviewer or workflow. Consumer: resume logic. Failure meaning: the workflow cannot resume safely without a terminal decision."
        ),
    )
    requested_at: str = Field(
        ...,
        description=(
            "Purpose: when the approval request was created. Producer: workflow. Consumer: audit and UI ordering. Failure meaning: the request has no reliable timestamp."
        ),
    )
    notes: str | None = Field(
        default=None,
        description=(
            "Purpose: human explanation or approved edit instruction. Producer: approver. Consumer: resume and re-run logic. Failure meaning: the approval may not capture the requested change."
        ),
    )


class ErrorInfo(BaseModel):
    """Structured runtime or validation error for tracked workflow failures."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        ...,
        description=(
            "Purpose: stable error code for logs and remediation. Producer: workflow or tool. "
            "Consumer: diagnostic routing and dashboards. Failure meaning: the failure is not indexable or actionable."
        ),
    )
    message: str = Field(
        ...,
        description=(
            "Purpose: brief human-readable explanation. Producer: exception or validation logic. "
            "Consumer: UI and retries. Failure meaning: users cannot understand what failed."
        ),
    )
    stage: WorkflowStage = Field(
        ...,
        description=(
            "Purpose: stage at which the error occurred. Producer: workflow or agent. Consumer: "
            "debugging and retry policy. Failure meaning: recovery decisions do not know which stage is impacted."
        ),
    )
    retryable: bool = Field(
        ...,
        description=(
            "Purpose: whether a retry is allowed without a different intervention. Producer: "
            "tool or workflow logic. Consumer: retry controller. Failure meaning: the system may keep retrying non-recoverable failures."
        ),
    )
    details: str | None = Field(
        default=None,
        description=(
            "Purpose: extra technical context or safe error details. Producer: tool or exception. "
            "Consumer: debugging and traces. Failure meaning: the failure lacks enough evidence for a precise fix."
        ),
    )


class RetryInfo(BaseModel):
    """Retry policy and current count for a workflow node or request."""

    model_config = ConfigDict(extra="forbid")

    attempt: int = Field(
        ..., ge=0,
        description=(
            "Purpose: current retry count for the current action. Producer: workflow retry scheduler. "
            "Consumer: loops, escalation, and UI status. Failure meaning: the system cannot enforce retry limits."
        ),
    )
    max_attempts: int = Field(
        ..., gt=0,
        description=(
            "Purpose: allowed retry threshold before the workflow escalates or fails. Producer: "
            "workflow configuration. Consumer: retry policy. Failure meaning: no safe retry ceiling exists."
        ),
    )
    next_delay_seconds: int | None = Field(
        default=None,
        description=(
            "Purpose: next backoff value if the recovery loop should wait before retrying. "
            "Producer: retry scheduler. Consumer: retry runtime. Failure meaning: the workflow may spin excessively without pause."
        ),
    )


# Every node should receive the same top-level state shape. If a required field is
# absent, the graph cannot safely decide which stage to run next, whether a
# review is required, or whether a retry is allowed. This is the shared contract
# that keeps the workflow deterministic.
class WorkflowState(BaseModel):
    """Top-level graph contract for the product development workflow."""

    model_config = ConfigDict(extra="forbid")

    product: ProductInputMetadata = Field(
        ...,
        description=(
            "Purpose: the original product brief and provenance. Producer: upload or document reader. "
            "Consumer: PM, architecture, and review nodes. Failure meaning: there is no reliable product context."
        ),
    )
    repository: RepositoryContext = Field(
        ...,
        description=(
            "Purpose: repository boundary that safe tools and agents can inspect. Producer: repository reader. "
            "Consumer: architecture and implementation planning. Failure meaning: the run has no grounded project context."
        ),
    )
    stage: WorkflowStage = Field(
        ...,
        description=(
            "Purpose: current graph node or lifecycle progression. Producer: workflow controller. "
            "Consumer: routing decisions and progress UI. Failure meaning: the workflow lacks a valid operational state."
        ),
    )
    artifacts: dict[str, ArtifactReference] = Field(
        default_factory=dict,
        description=(
            "Purpose: generated output references that later stages may read or approve. Producer: role agents. "
            "Consumer: review, resume, and UI layers. Failure meaning: downstream stages cannot inspect or revisit generated output."
        ),
    )
    review: ReviewStatus = Field(
        ...,
        description=(
            "Purpose: review gate state for the current stage or artifact. Producer: review handler. "
            "Consumer: graph routing and UI. Failure meaning: stage transitions are not auditable or safely gated."
        ),
    )
    sprint: SprintStatus = Field(
        ...,
        description=(
            "Purpose: active sprint and scope metadata. Producer: scrum master or technical lead. Consumer: implementation and review gates. Failure meaning: there is no stable execution plan."
        ),
    )
    assumptions: list[Assumption] = Field(
        default_factory=list,
        description=(
            "Purpose: explicit assumptions that need validation later. Producer: role agents. "
            "Consumer: architecture and review loops. Failure meaning: the run is operating on hidden assumptions."
        ),
    )
    risks: list[RiskEntry] = Field(
        default_factory=list,
        description=(
            "Purpose: known risks and mitigations. Producer: architecture or security roles. Consumer: review and release gating. Failure meaning: unacceptable risk may go unaddressed."
        ),
    )
    approval_requests: list[HumanApprovalRequest] = Field(
        default_factory=list,
        description=(
            "Purpose: pending or completed approval requests guarding high-impact actions. Producer: workflow. Consumer: UI and resume handlers. Failure meaning: safety approvals may be missed."
        ),
    )
    errors: list[ErrorInfo] = Field(
        default_factory=list,
        description=(
            "Purpose: structured failure list for current or recent stages. Producer: workflow or tool errors. Consumer: retry and debugging logic. Failure meaning: the system may keep retrying without recorded evidence."
        ),
    )
    retry: RetryInfo = Field(
        ...,
        description=(
            "Purpose: retry state for the active workflow stage. Producer: workflow retry controller. Consumer: escalation and resume logic. Failure meaning: the system has no bounded retry policy."
        ),
    )


__all__ = [
    "ApprovalDecision",
    "ArtifactReference",
    "Assumption",
    "ErrorInfo",
    "HumanApprovalRequest",
    "ProductInputMetadata",
    "RepositoryContext",
    "RetryInfo",
    "ReviewRequestStatus",
    "ReviewStatus",
    "RiskEntry",
    "SprintStatus",
    "WorkflowStage",
    "WorkflowState",
]
