"""A finding that tells a reviewer to break a stated constraint must say so.

`_missing_playwright_for_ui` tells the project it MUST install
`@playwright/test`. On this deployment's brief - "No external dependencies
beyond basic HTML/CSS/JS" - that reads as an instruction to break a constraint
the run has already committed to, and it arrived with no mention that the
constraint exists.

Both of one run's milestone reviewers worked the answer out for
themselves, wrote the reasoning into their findings ("While the brief forbids
external dependencies..."), and filed the result as `suggestion` against a
finding this module grades as blocking. Two consecutive reviewers overruling a
check is the check's problem.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import _missing_playwright_for_ui


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "package.json").write_text(
        '{"name":"p","type":"module","scripts":{"test":"node --test"}}', encoding="utf-8"
    )
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><script src="app.js"></script></body></html>',
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text(
        "document.querySelector('#add').addEventListener('click', () => {});",
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    return tmp_path


def _files(root: Path) -> list[Path]:
    return [root / "package.json", root / "index.html", root / "app.js"]


def test_a_brief_that_bans_dependencies_is_named(project: Path) -> None:
    (project / "docs" / "product_intake.md").write_text(
        "## Technical Constraints\n- No external dependencies beyond basic HTML/CSS/JS\n",
        encoding="utf-8",
    )

    problem = _missing_playwright_for_ui(_files(project), project, None)[0]

    assert "rule out external dependencies" in problem
    assert "devDependencies" in problem
    assert "npm ci --omit=dev" in problem


def test_the_grade_is_unchanged(project: Path) -> None:
    """The message is still the one the severity classification reads: the
    finding is not being downgraded, only made possible to act on."""
    from app.analysis.integration_checks import _severity_of

    (project / "docs" / "product_intake.md").write_text(
        "No external dependencies are permitted.\n", encoding="utf-8"
    )

    problem = _missing_playwright_for_ui(_files(project), project, None)[0]

    assert _severity_of(problem) == "BREAKS"


def test_a_project_with_no_such_constraint_reads_as_before(project: Path) -> None:
    (project / "docs" / "product_intake.md").write_text(
        "## Overview\nA to-do list with a filter bar.\n", encoding="utf-8"
    )

    problem = _missing_playwright_for_ui(_files(project), project, None)[0]

    assert "rule out external dependencies" not in problem


def test_the_word_external_alone_is_not_a_ban(project: Path) -> None:
    """Narrow on purpose: it has to be a statement about dependencies."""
    (project / "docs" / "product_intake.md").write_text(
        "Tasks are stored locally; no external API is called.\n", encoding="utf-8"
    )

    problem = _missing_playwright_for_ui(_files(project), project, None)[0]

    assert "rule out external dependencies" not in problem


def test_an_installed_playwright_reports_nothing_either_way(project: Path) -> None:
    (project / "package.json").write_text(
        '{"name":"p","devDependencies":{"@playwright/test":"^1.40.0"}}', encoding="utf-8"
    )
    (project / "docs" / "product_intake.md").write_text(
        "No external dependencies.\n", encoding="utf-8"
    )
    # Installed and used by a spec: installed alone no longer satisfies it.
    (project / "e2e").mkdir()
    (project / "e2e" / "ui.spec.js").write_text("import { test } from '@playwright/test';\ntest('opens', async ({ page }) => { await page.goto('/'); });\n", encoding="utf-8")

    assert _missing_playwright_for_ui(
        [*_files(project), project / "e2e" / "ui.spec.js"], project, None
    ) == []
