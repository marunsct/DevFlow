"""A locked test the runner never collects, or refuses outright, is the suite's to fix.

One run's suite left a test unclosed, so the next two - its only tests of two
criteria - were written inside its body. Counted from the text, all three
were there and the suite was locked. Playwright never registered the inner
two, so their criteria read "untested", and failed the outer one with "did not
expect test() to be called here". Round after round these went to the
product's fixers, who cannot change the suite.
"""

from __future__ import annotations

from pathlib import Path

from app.acceptance import junit, suite
from app.acceptance.criteria import number
from app.stacks import contract, pack_named

BRIEF = "# Brief\n## Features\n- Add a note\n- Delete a note\n- Edit a note\n"

SPEC = """test('[AC-1] adds a note', async ({ page }) => {
  await page.goto('/');
});

test('[AC-2] deletes a note', async ({ page }) => {
  await page.goto('/');

test('[AC-3] edits a note', async ({ page }) => {
  await page.goto('/');
});
});
"""


def _suite(root: Path) -> None:
    (root / ".project-directory").write_text("notes\n")
    suite.save_criteria(root, number(BRIEF))
    spec = root / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(SPEC)


def _ran(*tests: junit.TestResult) -> suite.AcceptanceResult:
    return suite.AcceptanceResult(ran=True, exit_code=1, command="npm run test:acceptance",
                                  report=junit.Report(found=True, tests=list(tests)))


def test_a_test_written_inside_another_is_named(tmp_path) -> None:
    _suite(tmp_path)
    result = _ran(
        junit.TestResult(name="[AC-1] adds a note"),
        junit.TestResult(name="Notes › [AC-2] deletes a note", outcome="failed",
                         message="Error: Playwright Test did not expect test() to be called here."),
    )

    missing = suite.tests_the_runner_never_ran(tmp_path, result)

    assert len(missing) == 1 and "[AC-3] edits a note" in missing[0]
    assert "never ran it" in missing[0]


def test_a_suite_whose_every_test_ran_has_nothing_to_say(tmp_path) -> None:
    _suite(tmp_path)
    result = _ran(*(junit.TestResult(name=n) for n in
                    ("[AC-1] adds a note", "[AC-2] deletes a note", "[AC-3] edits a note")))

    assert suite.tests_the_runner_never_ran(tmp_path, result) == []


def test_a_suite_that_did_not_run_says_nothing_here(tmp_path) -> None:
    """That is `run`'s own problem to report, not one test's."""
    _suite(tmp_path)

    assert suite.tests_the_runner_never_ran(tmp_path, suite.AcceptanceResult(ran=False)) == []


def test_playwright_s_refusal_of_the_spec_s_shape_is_the_test_s_bug() -> None:
    import re

    from app.stacks.packs._javascript import TEST_BUGS

    for message in (
        "Error: Playwright Test did not expect test() to be called here.",
        "Error: First argument must use the object destructuring pattern: page",
    ):
        assert any(re.search(pattern, message, re.I | re.M) for pattern in TEST_BUGS), message


def test_a_title_with_an_escaped_quote_is_found_in_the_report(tmp_path) -> None:
    """The text reader stops at `\\'`; one stored suite's `a task\\'s state` read as `a task\\`."""
    (tmp_path / ".project-directory").write_text("notes\n")
    suite.save_criteria(tmp_path, number(BRIEF))
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("test('[AC-1] keeps a note\\'s text', async ({ page }) => {});\n")

    result = _ran(junit.TestResult(name="[AC-1] keeps a note's text"))

    assert suite.tests_the_runner_never_ran(tmp_path, result) == []


def test_a_file_the_runner_does_not_collect_is_named_as_the_reason(tmp_path, monkeypatch) -> None:
    """Measured: a TypeScript service's QA wrote `api.spec.ts` where the runner collects `*.spec.js`; four rounds said
    only "make it a test of its own", the model kept the file, and the run failed with a suite that proved nothing."""
    (tmp_path / ".project-directory").write_text("notes\n")
    suite.save_criteria(tmp_path, number(BRIEF))
    spec = tmp_path / "notes" / "acceptance" / "api.spec.ts"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("test('[AC-1] adds a note', async ({ request }) => {});\n")
    contract.write(tmp_path, pack_named("node-hono-api"), "notes", "Notes")

    missing = suite.tests_the_runner_never_ran(tmp_path, _ran(junit.TestResult(name="[AC-2] other")))

    assert len(missing) == 1
    assert "`api.spec.ts` does not match" in missing[0] and "`*.spec.js`" in missing[0]
    assert "inside another test's body" not in missing[0]


def test_a_file_the_runner_does_collect_keeps_the_general_advice(tmp_path, monkeypatch) -> None:
    _suite(tmp_path)
    contract.write(tmp_path, pack_named("node-hono-api"), "notes", "Notes")
    result = _ran(junit.TestResult(name="[AC-1] adds a note"),
                  junit.TestResult(name="Notes › [AC-2] deletes a note", outcome="failed",
                                   message="did not expect test() to be called here."))

    missing = suite.tests_the_runner_never_ran(tmp_path, result)

    assert len(missing) == 1 and "inside another test's body" in missing[0] and "does not match" not in missing[0]
