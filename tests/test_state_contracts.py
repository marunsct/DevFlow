"""Contract tests for the workflow state model.

These tests do not just assert syntax; they prove the state objects produce the
expected behavior when the graph is assembled. A valid workflow state should be
constructible from real inputs, while a missing required field should fail early
so the bug is caught before a graph node tries to operate on incomplete data.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.state import (
    ArtifactReference,
    Assumption,
    ErrorInfo,
    HumanApprovalRequest,
    ProductInputMetadata,
    RepositoryContext,
    ReviewRequestStatus,
    ReviewStatus,
    RetryInfo,
    RiskEntry,
    SprintStatus,
    WorkflowStage,
    WorkflowState,
)


@pytest.fixture
def valid_state() -> WorkflowState:
    return WorkflowState(
        product=ProductInputMetadata(
            name="Acme launch brief",
            source_path="docs/product/brief.md",
            source_type="markdown",
            uploaded_by="user",
            uploaded_at="2026-09-03T00:00:00Z",
        ),
        repository=RepositoryContext(
            root_path="/workspace/repo",
            branch="main",
            commit="abc123",
            status="clean",
            dependency_files=["pyproject.toml"],
            entry_points=["src/app/main.py"],
        ),
        stage=WorkflowStage.INTAKE,
        artifacts={
            "product_brief": ArtifactReference(
                path="docs/generated/product-intake.md",
                kind="markdown",
                revision=1,
                created_by="product_manager",
                status="ready",
            )
        },
        review=ReviewStatus(
            stage=WorkflowStage.INTAKE,
            status=ReviewRequestStatus.PENDING,
            reviewer="product_manager",
            revision=1,
            updated_at="2026-09-03T00:00:00Z",
        ),
        sprint=SprintStatus(
            current_sprint=1,
            goal="Establish product intake and architecture proof",
            status="planned",
            in_scope=["product intake"],
            out_of_scope=["deployment"],
        ),
        assumptions=[
            Assumption(
                description="The product brief is the authoritative source of scope.",
                owner="product_manager",
                confidence="medium",
            )
        ],
        risks=[
            RiskEntry(
                description="The initial brief may omit non-functional constraints.",
                severity="medium",
                mitigation="Capture open questions before architecture approval.",
            )
        ],
        approval_requests=[
            HumanApprovalRequest(
                request_id="approval-1",
                stage="artifact_write",
                artifact_path="docs/generated/product-intake.md",
                risk_level="medium",
                requested_by="system",
                decision="pending",
                requested_at="2026-09-03T00:00:00Z",
            )
        ],
        errors=[
            ErrorInfo(
                code="E_NO_PRODUCT",
                message="No product brief could be decoded from the uploaded file.",
                stage=WorkflowStage.INTAKE,
                retryable=False,
            )
        ],
        retry=RetryInfo(
            attempt=1,
            max_attempts=3,
            next_delay_seconds=10,
        ),
    )


def test_workflow_state_accepts_valid_contract(valid_state: WorkflowState) -> None:
    # A real state object should carry all required runtime context so later nodes
    # can route correctly without checking raw dictionaries or stringly-typed fields.
    assert valid_state.product.name == "Acme launch brief"
    assert valid_state.stage == WorkflowStage.INTAKE
    assert valid_state.review.status == ReviewRequestStatus.PENDING
    assert valid_state.artifacts["product_brief"].kind == "markdown"


def test_product_metadata_requires_core_fields() -> None:
    # Missing required fields should fail immediately at the model boundary. This
    # catches bad inputs before a deeper workflow node tries to interpret partial data.
    with pytest.raises(ValidationError):
        ProductInputMetadata(
            name="Missing source path",
            source_type="markdown",
            uploaded_by="user",
            uploaded_at="2026-09-03T00:00:00Z",
        )


def test_review_status_rejects_invalid_decision() -> None:
    # Enums make review routing predictable. If a value is not one of the allowed
    # statuses, the graph should stop and ask for a corrected state instead of
    # continuing on an invalid review decision.
    with pytest.raises(ValidationError):
        ReviewStatus(
            stage=WorkflowStage.INTAKE,
            status="not-a-real-status",
            reviewer="product_manager",
            revision=1,
            updated_at="2026-09-03T00:00:00Z",
        )


def test_human_approval_requires_decision_and_path() -> None:
    # Safety approvals are a control point. If the route is missing its target path
    # or final decision, the system must refuse to continue because the approval is
    # not actionable.
    with pytest.raises(ValidationError):
        HumanApprovalRequest(
            request_id="approval-2",
            stage="artifact_write",
            risk_level="low",
            requested_by="system",
            requested_at="2026-09-03T00:00:00Z",
        )
