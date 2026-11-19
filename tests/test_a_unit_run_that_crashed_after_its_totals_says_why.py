"""A unit run whose test host crashed after printing its totals is described by the crash, not by "Failed: 0".

Measured on one C# run: nine tests passed, then the host crashed - "PORT is not set or is not a valid port" - and the
run was aborted. The defect's cause line read "Passed! - Failed: 0, Passed: 9, ..." (the word "Failed" counted as an
error) and the crash, which names no Error or FAIL, was left out: the fixers were told the tests fail beside a line
saying they pass.
"""
from __future__ import annotations

from app.graph import workflow

OUTPUT = """\
/workspace/notes-api/tests/UnitTests/ApiTests.cs(331,50): warning CS8602: Dereference of a possibly null reference.
  UnitTests -> /workspace/notes-api/tests/UnitTests/bin/Debug/net8.0/UnitTests.dll
Test run for /workspace/notes-api/tests/UnitTests/bin/Debug/net8.0/UnitTests.dll (.NETCoreApp,Version=v8.0)
Starting test execution, please wait...
Passed!  - Failed:     0, Passed:     9, Skipped:     0, Total:     9, Duration: 52 ms - UnitTests.dll (net8.0)
The active test run was aborted. Reason: Test host process crashed : PORT is not set or is not a valid port

Test Run Aborted.
"""


def test_the_crash_is_what_it_says():
    said = workflow._what_the_failure_says(OUTPUT)

    assert "PORT is not set" in said
    assert "Test Run Aborted" in said


def test_a_count_of_no_failures_is_not_a_failure():
    assert "Passed!" not in workflow._what_the_failure_says(OUTPUT)
    assert workflow._what_the_failure_says("Tests: 0 failed, 12 passed\nerrors=0\n") == ""


def test_a_line_that_names_failures_is_still_one():
    said = workflow._what_the_failure_says("Failed!  - Failed:     2, Passed:     7, Total: 9\n")

    assert "Failed:     2" in " ".join(said.split()) or "Failed: 2" in said
