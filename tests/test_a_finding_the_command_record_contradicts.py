"""A gating finding that a command fails, when its last run passed, does not gate.

Measured on one run. Its milestone reviewer found that `npm test` could not
run; a fix stage repaired it, and the ledger recorded `npm test` passing. The
reviewer was shown its own earlier finding and returned it word for word on the
last revision allowed, so the run ended with nothing delivered - on a claim the
command record in the same request disproved.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.graph import workflow
from app.graph.workflow import (
    _findings_the_command_record_contradicts,
    _the_passing_command_it_says_fails,
)

STANDING = {"npm test": True, "npm run test:e2e": False}

STALE = (
    "npm test script uses invalid relative path to Jest binary, blocking unit tests."
)


class _Finding(SimpleNamespace):
    def model_copy(self, update):
        return _Finding(**{**self.__dict__, **update})


class _Review(SimpleNamespace):
    def model_copy(self, update):
        return _Review(**{**self.__dict__, **update})


def test_a_command_said_to_fail_whose_last_run_passed_is_named() -> None:
    assert _the_passing_command_it_says_fails(STALE, STANDING) == "npm test"


@pytest.mark.parametrize("description", [
    # Says the command passes; the failure is something else.
    "npm test passes, but the form fails to submit a task in the page.",
    # Names a command that is still failing: it has a failure of its own.
    "npm test fails and npm run test:e2e exits 1 because the server never starts.",
    "npm run test:e2e fails: the webServer command uses an undeclared binary.",
    # Names no command at all.
    "Editing a task does not update its title.",
    # A longer command that merely starts the same way.
    "npm test:unit fails with a missing module.",
    # Mentions the command without saying it fails.
    "The suite run by npm test covers only the storage module.",
])
def test_anything_else_is_left_alone(description) -> None:
    assert _the_passing_command_it_says_fails(description, STANDING) == ""


def test_the_finding_is_kept_and_stops_gating(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "_where_each_command_stands", lambda root: STANDING)
    review = _Review(findings=[
        _Finding(severity="major", description=STALE),
        _Finding(severity="major", description="npm run test:e2e fails: no server."),
    ])

    after = _findings_the_command_record_contradicts(review, "/somewhere")

    assert [finding.severity for finding in after.findings] == ["minor", "major"]
    assert after.findings[0].description.startswith(
        "The most recent run of `npm test` in this workspace passed"
    )
    assert STALE in after.findings[0].description


def test_a_finding_that_does_not_gate_is_not_touched(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "_where_each_command_stands", lambda root: STANDING)
    review = _Review(findings=[_Finding(severity="minor", description=STALE)])

    assert _findings_the_command_record_contradicts(review, "/somewhere") is review


def test_with_no_command_record_the_review_stands(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "_where_each_command_stands", lambda root: {})
    review = _Review(findings=[_Finding(severity="major", description=STALE)])

    assert _findings_the_command_record_contradicts(review, "/somewhere") is review


from app.graph.workflow import _the_passing_suite_it_says_fails

PASSING = {"npm test": True}

READ_NOT_RUN = (
    "jest.setup.js uses CommonJS `require` statements in an ES module context due to "
    'package.json "type": "module". This causes test suites to fail with ReferenceError '
    "before any tests run."
)


def test_a_claim_that_the_tests_fail_is_checked_against_the_suite_s_last_run() -> None:
    """One run's reviewer read a setup file and wrote that the suites fail. The
    suite's last run had passed: nine suites, eighteen tests."""
    assert _the_passing_suite_it_says_fails(READ_NOT_RUN, PASSING) == "npm test"


@pytest.mark.parametrize("description", [
    # A kind of test the passing command is not.
    "The Playwright end-to-end tests fail because the server never starts.",
    "Browser tests fail to find the task list.",
    # Not about the tests failing.
    "The delete button does nothing when clicked.",
    "Unit tests pass but do not cover deleteTask.",
    "There are no tests for the filter.",
])
def test_other_findings_are_left_alone(description) -> None:
    assert _the_passing_suite_it_says_fails(description, PASSING) == ""


def test_a_kind_of_test_that_did_pass_is_answered() -> None:
    both = {"npm test": True, "npx playwright test": True}

    assert _the_passing_suite_it_says_fails(
        "The Playwright tests fail on load with a ReferenceError.", both
    ) == "npx playwright test"


def test_one_failing_test_command_and_nothing_is_contradicted() -> None:
    assert _the_passing_suite_it_says_fails(READ_NOT_RUN, {"npm test": True, "npm run e2e": False}) == ""
    assert _the_passing_suite_it_says_fails(READ_NOT_RUN, {}) == ""


def test_such_a_finding_stops_gating(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "_where_each_command_stands", lambda root: PASSING)
    monkeypatch.setattr(workflow, "_where_each_test_command_stands", lambda root: PASSING)
    review = _Review(findings=[_Finding(severity="major", description=READ_NOT_RUN)])

    after = _findings_the_command_record_contradicts(review, "/somewhere")

    assert after.findings[0].severity == "minor"
    assert "most recent run of `npm test`" in after.findings[0].description
