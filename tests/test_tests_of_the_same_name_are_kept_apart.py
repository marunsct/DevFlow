"""Two tests of the same name are two tests in a CI snapshot.

By name alone, "does not mutate the original array" - written once per function
- was one entry and the last outcome overwrote the others. One run's 37 unit
tests were recorded as 29, its sprint summaries counted 42 tests where there
were 50, and a failing test could hide behind a passing one of the same name.
"""

from __future__ import annotations

from app import ci
from app.acceptance.junit import TestResult as Case


def test_same_named_tests_in_different_files_are_counted_apart() -> None:
    found = ci.outcomes_of([
        Case(name="does not mutate the original array", file="tests/add.test.js"),
        Case(name="does not mutate the original array", file="tests/delete.test.js"),
        Case(name="adds", suite="addTask"),
    ])
    assert len(found) == 3


def test_a_failure_is_not_hidden_by_a_pass_of_the_same_key() -> None:
    found = ci.outcomes_of([
        Case(name="works", outcome="failed"),
        Case(name="works", outcome="passed"),
    ])
    assert found == {"works": "failed"}


def test_a_same_named_test_that_breaks_is_a_regression() -> None:
    before = ci.Snapshot(label="b", unit=ci.outcomes_of([
        Case(name="keeps the input", file="a.test.js"), Case(name="keeps the input", file="b.test.js"),
    ]), unit_ran=True)
    after = ci.Snapshot(label="a", unit=ci.outcomes_of([
        Case(name="keeps the input", file="a.test.js"),
        Case(name="keeps the input", file="b.test.js", outcome="failed"),
    ]), unit_ran=True)

    assert ci.regressions(before, after) == [f"unit: b.test.js{ci.WHERE}keeps the input"]


def test_a_snapshot_keyed_by_name_alone_is_compared_by_name() -> None:
    """An accepted snapshot saved before keys carried a file must not read as
    every test lost."""
    before = ci.Snapshot(label="old", unit={"keeps the input": "passed", "adds": "passed"}, unit_ran=True)
    after = ci.Snapshot(label="new", unit=ci.outcomes_of([
        Case(name="keeps the input", file="a.test.js"),
        Case(name="keeps the input", file="b.test.js"),
        Case(name="adds", file="a.test.js", outcome="failed"),
    ]), unit_ran=True)

    assert ci.regressions(before, after) == ["unit: adds"]
