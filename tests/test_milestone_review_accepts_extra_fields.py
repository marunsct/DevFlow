"""Milestone reviewer outputs ignore harmless extra fields.

When a language model returns structured output, it sometimes includes extra
keys such as `changes_required_note`, `notes`, `summary`, or `reasoning`.
Rejecting the whole tool call with `extra_forbidden` causes the structured
response parsing to fail, leading to repeated failed attempts and stage retries.
"""

from __future__ import annotations

import pytest

from app.agents.milestone_reviewer import MilestoneReviewFinding, MilestoneReviewOutput


def test_milestone_review_output_ignores_extra_fields() -> None:
    data = {
        "status": "changes_required",
        "findings": [],
        "acceptance_evidence": "All 15 acceptance tests pass.",
        "documentation_reviewed": True,
        "tests_reviewed": True,
        "changes_required_note": "The product itself is solid, but docs/milestone_plan.md was never completed.",
        "notes": "Extra commentary from model",
    }
    output = MilestoneReviewOutput.model_validate(data)
    assert output.status == "changes_required"
    assert output.acceptance_evidence == "All 15 acceptance tests pass."
    assert output.documentation_reviewed is True
    assert output.tests_reviewed is True


def test_milestone_review_finding_ignores_extra_fields() -> None:
    data = {
        "severity": "minor",
        "category": "code_quality",
        "description": "Harmless comment duplication.",
        "affected_files": ["simple-to-do-list-app/styles.css"],
        "required_remediation": "Remove redundant duplicate comment block.",
        "commentary": "Found during visual inspection",
    }
    finding = MilestoneReviewFinding.model_validate(data)
    assert finding.severity == "minor"
    assert finding.category == "code_quality"
    assert finding.description == "Harmless comment duplication."
