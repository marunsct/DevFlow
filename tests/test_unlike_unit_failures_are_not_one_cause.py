"""Failing unit tests are grouped by what they compared, not by the assertion's generic header (LF.1451).

Measured over saved unit runs (deep review 2026-11-25, parsers finding 5): 7 of 34 groups of two or more failures were
one generic line - Rust's "assertion `left == right` failed" for 18 tests that wanted 422, 404, 201 and 400, C#'s
"Assert.Equal() Failure: Values differ" for an error status and an empty list alike, and every Go failure "Failed".
The fixer of the unit-test defect was told one cause where there were several. Fixtures are the runners' real reports,
copied verbatim from three workspaces.
"""
from __future__ import annotations

from pathlib import Path

from app import ci
from app.acceptance import junit

CAPTURED = Path(__file__).parent / "captured"


def _causes(report: str) -> list[str]:
    parsed = junit.read(CAPTURED / report)
    text = ci.the_distinct_causes(ci.what_the_failing_unit_tests_say(parsed.tests))
    return [line for line in text.splitlines() if line.startswith("- ")]


def test_rust_failures_that_wanted_different_statuses_are_different_causes():
    causes = _causes("nextest-junit-failing-axum.xml")

    wanted = {status for status in ("right: 422", "right: 404", "right: 201", "right: 400") if
              any(status in line for line in causes)}
    assert wanted == {"right: 422", "right: 404", "right: 201", "right: 400"}
    assert all("left: 500" in line for line in causes if "assertion `left == right` failed" in line)


def test_csharp_failures_carry_what_was_expected_and_what_came():
    causes = _causes("dotnet-junit-failing-aspnet.xml")

    assert any("Expected: BadRequest" in line and "Actual: InternalServerError" in line for line in causes)
    assert any("Expected: 2" in line and "Actual: 0" in line for line in causes)
    assert not any(line.endswith("Values differ") for line in causes)


def test_a_go_failure_is_read_past_its_bare_failed_line():
    causes = _causes("gotestsum-junit-failing-http.xml")

    assert any('Content-Type = ""; want "application/json"' in line for line in causes)
