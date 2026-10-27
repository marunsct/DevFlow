"""A criterion's test the runner skips proves nothing: the suite is not locked with it, and a re-measure does not close on it.

Measured on one run: a suite repair turned nine of the suite's tests into
`test.skip('[AC-n] ...', async () => {})` with empty bodies, deleting their
checks. The review locked the suite: each criterion still had a test of its
name. Every round then reported those criteria as not working, and the
re-measure taken at dispatch closed each one without a fixer, because its own
tests had all been reported skipped and a skipped test was counted as one
that passed. The sprint was planned again with nothing fixed.
"""
from __future__ import annotations

from pathlib import Path

from app.acceptance import junit, per_file, suite
from app.acceptance.criteria import number

BRIEF = "# Brief\n## Features\n- Add a note\n- Delete a note\n"

SPEC = """test('[AC-1] adds a note', async ({ request }) => {
  expect((await request.post('/notes', { data: { title: 'a' } })).status()).toBe(201);
});

test.skip('[AC-2] deletes a note', async ({ request }) => {});
"""


def _suite(root: Path, spec: str = SPEC) -> None:
    (root / ".project-directory").write_text("notes\n")
    suite.save_criteria(root, number(BRIEF))
    path = root / "notes" / "acceptance" / "notes.spec.js"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(spec)


def _ran(*tests: junit.TestResult) -> suite.AcceptanceResult:
    return suite.AcceptanceResult(ran=True, exit_code=0, command="npx playwright test",
                                  report=junit.Report(found=True, tests=list(tests)))


def test_a_test_written_skipped_is_a_reason_the_suite_proves_nothing(tmp_path) -> None:
    _suite(tmp_path)
    result = _ran(junit.TestResult(name="[AC-1] adds a note", outcome="failed"),
                  junit.TestResult(name="[AC-2] deletes a note", outcome="skipped"))

    reasons = suite.vacuous_green(tmp_path, result)

    assert len(reasons) == 1 and "[AC-2] deletes a note" in reasons[0] and "skipped" in reasons[0]
    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
        assert f" {word} " not in f" {reasons[0].lower()} ", word


def test_a_skipped_test_with_nothing_failed_is_named_whatever_skipped_it(tmp_path) -> None:
    _suite(tmp_path, SPEC.replace("test.skip(", "test("))
    result = _ran(junit.TestResult(name="[AC-1] adds a note"),
                  junit.TestResult(name="[AC-2] deletes a note", outcome="skipped"))

    assert any("[AC-2] deletes a note" in reason for reason in suite.vacuous_green(tmp_path, result))


def test_a_test_skipped_after_another_failed_is_not_named_when_it_is_written_to_run(tmp_path) -> None:
    """A runner skips the rest of a serial group after a failure; that test is written to run."""
    _suite(tmp_path, SPEC.replace("test.skip(", "test("))
    result = _ran(junit.TestResult(name="[AC-1] adds a note", outcome="failed"),
                  junit.TestResult(name="[AC-2] deletes a note", outcome="skipped"))

    assert suite.vacuous_green(tmp_path, result) == []


def test_a_defect_whose_own_tests_were_all_skipped_is_not_measured_passing(tmp_path) -> None:
    report = tmp_path / "acceptance.xml"
    report.write_text(
        '<testsuites><testsuite name="notes.spec.js">'
        '<testcase name="[AC-1] adds a note"/>'
        '<testcase name="[AC-2] deletes a note"><skipped/></testcase>'
        '</testsuite></testsuites>')

    assert per_file._its_own_tests(report, {"AC-2"}) != "finished"
    assert per_file._its_own_tests(report, {"AC-1"}) == "finished"
