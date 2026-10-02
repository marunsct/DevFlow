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
