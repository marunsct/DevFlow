"""The size report names the budget and the verdict, not two numbers.

One run of 2026-09-20 failed on this. Its milestone review blocked with:

    Application source files total 631 lines across 3 files, exceeding the
    brief's stated constraint of 'Maximum 500 lines of code'. The deterministic
    size check confirms this violates the size budget.

The deterministic check said the opposite. The product measured 413 lines of
code against a declared 500 - which is why `budget_note_for_a_write`, reading
the same figure, stayed silent through every write of the run. 631 is the raw
total, blank lines and comments included.

The reviewer required changes three times, the rerun limit fired, and the run
ended after 199 model calls and roughly five million tokens on a finding the
harness's own measurement contradicts - while asserting that measurement agreed
with it.

The report already carried the line "A brief that caps 'lines of code' means the
second number, not the first". It was read past. So the figure the project is
judged against is now stated with its verdict attached, leaving nothing to pick
between.
"""

from __future__ import annotations

import pytest

from app.analysis.integration_checks import summarise_integration

SPEC = """# Technical Specification

## Constraints
- Total source code stays within 500 lines.
"""


def _page(blank_lines: int) -> str:
    body = "\n".join(
        ["<!doctype html>", "<html><body>", '<script src="app.js"></script>']
        + [""] * blank_lines
        + ["</body></html>"]
    )
    return body + "\n"


@pytest.fixture
def project(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(SPEC)
    return tmp_path


def test_a_product_inside_its_budget_says_so(project):
    """The one run shape: a large raw total over a small code total."""
    (project / "index.html").write_text(_page(200))
    (project / "app.js").write_text(
        "// a comment\n\n" * 100 + "document.title = 'x';\n"
    )

    report = summarise_integration(project)

    assert "WITHIN budget" in report
    assert "500-line limit" in report
    # And it must say why the bigger number is not the one to use.
    assert "not the figure to judge" in report
    assert "OVER by" not in report


def test_a_product_over_its_budget_says_that_instead(project):
    (project / "index.html").write_text(_page(2))
    (project / "app.js").write_text("const x = 1;\n" * 600)

    report = summarise_integration(project)

    assert "OVER by" in report
    assert "a reviewer should block on it" in report
    assert "WITHIN budget" not in report


def test_the_verdict_counts_code_and_not_raw_lines(project):
    """The exact confusion that failed the run, pinned to a number.

    Blank lines and comments are in the raw total and out of the budget
    comparison, so a file can be far longer than the cap and still inside it.
    """
    (project / "index.html").write_text(_page(0))
    (project / "app.js").write_text("\n" * 900 + "const x = 1;\n")

    report = summarise_integration(project)

    assert "WITHIN budget" in report, report[report.find("Size of the product"):]


def test_no_declared_budget_means_no_verdict(tmp_path):
    """Nothing to compare against, so nothing is asserted."""
    (tmp_path / "index.html").write_text(_page(0))
    (tmp_path / "app.js").write_text("const x = 1;\n")

    report = summarise_integration(tmp_path)

    assert "WITHIN budget" not in report
    assert "OVER by" not in report


def test_the_write_time_note_and_the_report_agree(project):
    """The two must never contradict each other again.

    `budget_note_for_a_write` stayed silent all through one run while the
    reviewer blocked; both read the same measurement, so they are checked
    against each other here.
    """
    from app.analysis.integration_checks import budget_note_for_a_write

    (project / "index.html").write_text(_page(200))
    (project / "app.js").write_text("// c\n\n" * 100 + "document.title = 'x';\n")

    report = summarise_integration(project)
    note = budget_note_for_a_write(project, "app.js")

    assert "WITHIN budget" in report
    assert note == "", "the note fired on a project the report calls within budget"


# --- who the budget note is delivered to ----------------------------------


def test_the_budget_note_is_not_sent_to_a_test_file(tmp_path) -> None:
    """The number is application code only - that is the note's whole point -
    but a note is delivered to whoever is writing *this* file. A testing
    specialist told "you are 80 lines over" while holding `app.test.mjs` has
    one obvious way to comply, which is to cut the file in its hand.

    That is the reaction the note's own comment warns about, arriving through
    the addressee rather than through the total. 7 of its 27 firings across
    the stored runs landed on a test file.
    """
    from app.analysis.integration_checks import budget_note_for_a_write

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "intake.md").write_text(
        "## Acceptance Criteria\n- Maximum 100 lines of code\n", encoding="utf-8"
    )
    (tmp_path / "app.js").write_text(
        "\n".join(f"export const v{i} = {i};" for i in range(300)), encoding="utf-8"
    )
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><script type="module" src="app.js"></script></body></html>',
        encoding="utf-8",
    )
    (tmp_path / "app.test.mjs").write_text(
        "import { test } from 'node:test';\ntest('a', () => {});\n", encoding="utf-8"
    )

    assert budget_note_for_a_write(str(tmp_path), "app.test.mjs") == ""


def test_the_application_file_still_gets_it(tmp_path) -> None:
    from app.analysis.integration_checks import budget_note_for_a_write

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "intake.md").write_text(
        "## Acceptance Criteria\n- Maximum 100 lines of code\n", encoding="utf-8"
    )
    (tmp_path / "app.js").write_text(
        "\n".join(f"export const v{i} = {i};" for i in range(300)), encoding="utf-8"
    )
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><script type="module" src="app.js"></script></body></html>',
        encoding="utf-8",
    )

    note = budget_note_for_a_write(str(tmp_path), "app.js")

    assert "over" in note
    assert "application code" in note
