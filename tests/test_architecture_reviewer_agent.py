"""Tests for the Senior Architect Reviewer Deep Agent (Step 4.3)."""

from __future__ import annotations

from app.agents.architecture_reviewer import (
    ArchitectureReviewFinding,
    ArchitectureReviewOutput,
    create_architecture_reviewer_agent,
)


def test_architecture_review_output_schema_is_present() -> None:
    schema = ArchitectureReviewOutput.model_json_schema()

    required_fields = {"status", "findings", "approval_conditions", "accepted_risks"}
    assert required_fields.issubset(schema["properties"].keys())
    assert schema["properties"]["status"]["enum"] == ["approved", "changes_required"]


def test_architecture_review_finding_schema_is_present() -> None:
    schema = ArchitectureReviewFinding.model_json_schema()

    required_fields = {"severity", "description", "evidence", "required_remediation"}
    assert required_fields.issubset(schema["properties"].keys())


def test_architecture_reviewer_agent_factory_creates_graph() -> None:
    agent = create_architecture_reviewer_agent(model="openai:gpt-4o-mini")

    assert agent is not None
    assert hasattr(agent, "invoke")
