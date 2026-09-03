"""Tests for the per-sprint test and bug-remediation loop (Step 5.4).

Pure, fast unit tests: no agent, model, or LangGraph invocation needed.
"""

from __future__ import annotations

import pytest

from app.sprint import (
    Defect,
    RemediationLimitExceeded,
    accept_risk,
    is_sprint_acceptable,
    mark_defect_fixed,
    record_test_run,
    start_remediation,
)


def _sample_defect(**overrides: object) -> Defect:
    fields = {
        "description": "Login button does nothing on mobile Safari",
        "severity": "major",
        "reproduction_steps": "Open the login page on mobile Safari and tap Login.",
        "expected_behavior": "The login flow starts.",
        "actual_behavior": "Nothing happens.",
        "affected_files": ["src/web/login.tsx"],
        "owner": "ui_ux",
    }
    fields.update(overrides)
    return Defect(**fields)


def test_start_remediation_begins_at_zero_attempts() -> None:
    cycle = start_remediation("Sprint 1: login")

    assert cycle.attempt == 0
    assert cycle.defects == []
    assert not cycle.escalated


def test_passing_test_run_does_not_consume_an_attempt() -> None:
    cycle = start_remediation("Sprint 1: login")

    cycle = record_test_run(cycle, command=["pytest", "-q"], passed=True, summary="12 passed")

    assert cycle.attempt == 0
    assert cycle.test_runs[0].passed is True


def test_failing_test_run_records_defect_and_consumes_an_attempt() -> None:
    cycle = start_remediation("Sprint 1: login")
    defect = _sample_defect()

    cycle = record_test_run(cycle, command=["pytest", "-q"], passed=False, new_defects=[defect])

    assert cycle.attempt == 1
    assert cycle.defects[0].status == "open"
    assert is_sprint_acceptable(cycle) is False


def test_remediation_escalates_after_max_attempts() -> None:
    cycle = start_remediation("Sprint 1: login", max_attempts=2)
    cycle = record_test_run(cycle, command=["pytest"], passed=False, new_defects=[_sample_defect()])
    assert cycle.attempt == 1
    assert cycle.escalated is False

    cycle = record_test_run(cycle, command=["pytest"], passed=False)
    assert cycle.attempt == 2
    assert cycle.escalated is True

    with pytest.raises(RemediationLimitExceeded):
        record_test_run(cycle, command=["pytest"], passed=False)


def test_mark_defect_fixed_requires_a_regression_test() -> None:
    cycle = start_remediation("Sprint 1: login")
    cycle = record_test_run(cycle, command=["pytest"], passed=False, new_defects=[_sample_defect()])

    with pytest.raises(ValueError):
        mark_defect_fixed(cycle, 0, regression_test="")


def test_mark_defect_fixed_with_regression_test_makes_sprint_acceptable() -> None:
    cycle = start_remediation("Sprint 1: login")
    cycle = record_test_run(cycle, command=["pytest"], passed=False, new_defects=[_sample_defect()])

    cycle = mark_defect_fixed(cycle, 0, regression_test="tests/test_login_mobile_safari.py")

    assert is_sprint_acceptable(cycle) is True


def test_accepted_risk_requires_a_reason() -> None:
    cycle = start_remediation("Sprint 1: login")
    cycle = record_test_run(cycle, command=["pytest"], passed=False, new_defects=[_sample_defect()])

    with pytest.raises(ValueError):
        accept_risk(cycle, 0, reason="")

    cycle = accept_risk(cycle, 0, reason="Low-traffic browser; scheduled for next sprint.")
    assert is_sprint_acceptable(cycle) is True
