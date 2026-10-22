"""A product over its line budget is not a dead CSS rule.

The summary had two buckets, and a finding that breaks nothing and is not
untidiness either had no home. So "The product is 580 lines of code against
the 500-line maximum this project's own documents state - 80 over ... This is
a stated acceptance criterion, not a preference" arrived under the heading
"untidy rather than broken - dead rules, unused files. Worth a minor finding,
not a blocking one" - in the same report whose size section says, of the same
number, "This is a stated acceptance criterion and a reviewer should block on
it". A reviewer reads both and is left to guess which the harness means.

Seen on one run (538 against 500) and one run (580 against 500).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import _severity_of, summarise_integration

OVER_BUDGET = (
    "The product is 580 lines of code against the 500-line maximum this "
    "project's own documents state - 80 over. Counted without blank lines, "
    "comments, tests or files nothing loads. This is a stated acceptance "
    "criterion, not a preference: either bring it under 500 or say in the "
    "review why the criterion no longer holds."
)

BREAKS = (
    "task-manager/package.json has no script that runs ui.pw.test.mjs - they "
    "are @playwright/test specs, and nothing in this manifest invokes it."
)

UNTIDY = (
    "task-manager/app.js exports 10 name(s) and no test mentions generateId, "
    "init. A passing suite says nothing about those."
)


def test_an_unmet_criterion_is_graded_as_one() -> None:
    assert _severity_of(OVER_BUDGET) == "CRITERION"


def test_it_is_not_promoted_to_breaking() -> None:
    """That bucket's heading says "a feature DOES NOT WORK ... the code path
    is simply never reached", and a product eighty lines over its budget works
    perfectly well. Grading it there would make the heading false - the
    mistake `test_a_ui_with_no_browser_test_blocks` exists to prevent."""
    assert _severity_of(OVER_BUDGET) != "BREAKS"


def test_a_broken_relationship_is_still_breaking() -> None:
    assert _severity_of(BREAKS) == "BREAKS"


def test_a_dead_export_is_still_untidy() -> None:
    assert _severity_of(UNTIDY) == "untidy"


@pytest.fixture
def over_budget(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "product_intake.md").write_text(
        "## Acceptance Criteria\n- Maximum 100 lines of code\n", encoding="utf-8"
    )
    (tmp_path / "app.js").write_text(
        "\n".join(f"export const v{i} = {i};" for i in range(200)), encoding="utf-8"
    )
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><script type="module" src="app.js"></script></body></html>',
        encoding="utf-8",
    )
    return tmp_path


def test_the_summary_gives_it_its_own_heading(over_budget: Path) -> None:
    summary = summarise_integration(str(over_budget))

    assert "a stated acceptance criterion this product does not meet" in summary


def test_the_heading_says_who_may_decide_otherwise(over_budget: Path) -> None:
    """The same rule the deferral finding states: a criterion the project was
    given is not one the run may set aside for itself."""
    summary = summarise_integration(str(over_budget))

    assert "only a person may decide that no longer holds" in summary


def test_it_is_not_under_the_untidy_heading(over_budget: Path) -> None:
    summary = summarise_integration(str(over_budget))
    line = next(l for l in summary.splitlines() if "lines of code against" in l)
    untidy_at = summary.find("untidy rather than broken")

    assert untidy_at == -1 or summary.index(line) < untidy_at


def test_a_project_inside_its_budget_says_nothing(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "product_intake.md").write_text(
        "## Acceptance Criteria\n- Maximum 500 lines of code\n", encoding="utf-8"
    )
    (tmp_path / "app.js").write_text("export const a = 1;\n", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><script type="module" src="app.js"></script></body></html>',
        encoding="utf-8",
    )

    assert "does not meet" not in summarise_integration(str(tmp_path))
