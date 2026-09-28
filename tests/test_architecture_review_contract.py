"""The review decision the model keeps forgetting to write down."""

from __future__ import annotations

import pytest

from app.agents.architecture_reviewer import ArchitectureReviewOutput


def _finding(severity: str) -> dict:
    return {
        "severity": severity,
        "description": "d",
        "evidence": "e",
        "required_remediation": "r",
    }


def test_a_missing_status_is_derived_from_the_findings() -> None:
    """Measured on one run: the reviewer answered `{"findings": [...]}`
    with no `status` four times in one stage, costing two stage restarts and
    reaching "attempt 3 of 3" - the last retry before the stage fails. Across
    all stored runs, 8 of 74 answers carrying findings omit the field.

    This is not a guess. The system prompt states the rule as mandatory: any
    blocking or major finding forces `changes_required`.
    """
    assert (
        ArchitectureReviewOutput.model_validate({"findings": [_finding("blocking")]}).status
        == "changes_required"
    )
    assert (
        ArchitectureReviewOutput.model_validate({"findings": [_finding("major")]}).status
        == "changes_required"
    )
    assert (
        ArchitectureReviewOutput.model_validate({"findings": [_finding("minor")]}).status
        == "approved"
    )
    assert ArchitectureReviewOutput.model_validate({"findings": []}).status == "approved"


def test_a_status_the_model_wrote_is_never_changed() -> None:
    """Only what is ABSENT is filled.

    Across every stored run there are zero verdicts approving around their own
    blocking finding, so there is nothing to enforce - and overriding a stated
    decision on no evidence would be the worse error.
    """
    written = ArchitectureReviewOutput.model_validate(
        {"status": "approved", "findings": [_finding("blocking")]}
    )

    assert written.status == "approved"


def test_the_severity_of_a_finding_still_decides_nothing_by_itself() -> None:
    """A malformed findings list must not silently produce a status."""
    assert (
        ArchitectureReviewOutput.model_validate(
            {"status": "changes_required", "findings": []}
        ).status
        == "changes_required"
    )
    with pytest.raises(Exception):
        ArchitectureReviewOutput.model_validate({"findings": "not a list"})


# --- the decision the model keeps forgetting to write down ----------------


def _a_finding(severity: str) -> dict:
    return {
        "severity": severity,
        "description": "d",
        "evidence": "e",
        "required_remediation": "r",
    }


def test_a_missing_status_is_derived_from_the_findings() -> None:
    """Measured on one run: the reviewer answered `{"findings": [...]}`
    with no `status` four times in one stage, costing two stage restarts and
    reaching "attempt 3 of 3" - the last retry before the stage fails outright.
    Across all stored runs, 8 of 74 answers carrying findings omit the field.

    Not a guess: the system prompt states the rule as mandatory - any blocking
    or major finding forces `changes_required`.
    """
    from app.agents.architecture_reviewer import ArchitectureReviewOutput

    assert (
        ArchitectureReviewOutput.model_validate(
            {"findings": [_a_finding("blocking")]}
        ).status
        == "changes_required"
    )
    assert (
        ArchitectureReviewOutput.model_validate({"findings": [_a_finding("major")]}).status
        == "changes_required"
    )
    assert (
        ArchitectureReviewOutput.model_validate({"findings": [_a_finding("minor")]}).status
        == "approved"
    )
    assert ArchitectureReviewOutput.model_validate({"findings": []}).status == "approved"


def test_a_status_the_model_wrote_is_never_changed() -> None:
    """Only what is ABSENT is filled.

    Across every stored run there are zero verdicts approving around their own
    blocking finding, so there is nothing to enforce, and overriding a stated
    decision on no evidence would be the worse error.
    """
    from app.agents.architecture_reviewer import ArchitectureReviewOutput

    written = ArchitectureReviewOutput.model_validate(
        {"status": "approved", "findings": [_a_finding("blocking")]}
    )

    assert written.status == "approved"


def test_a_malformed_findings_list_produces_no_status() -> None:
    import pytest

    from app.agents.architecture_reviewer import ArchitectureReviewOutput

    with pytest.raises(Exception):
        ArchitectureReviewOutput.model_validate({"findings": "not a list"})
