"""Tests that acceptance tests calling nonexistent locator methods are caught and rejected.

Locator methods from other libraries (e.g. getByLabelText from Testing Library)
fail at runtime in Playwright with "is not a function". Because acceptance tests
fail on navigation before the product is built, these errors are hidden during
initial review unless verified mechanically before locking.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance import junit, suite
from app.acceptance.criteria import number
from app.graph import acceptance_nodes
from app.stacks import pack_named
from app.stacks.scaffold import scaffold

BRIEF = """# Items
## Features
- Add an item
"""


def _scaffolded(tmp_path: Path) -> Path:
    pack = pack_named("browser-javascript")

    def smoke(argv, category, wd):
        unit = list(argv) == pack.commands(wd)["unit_test"]
        report = tmp_path / wd / (pack.unit_report if unit else pack.acceptance_report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("<testsuites><testcase name='smoke'/></testsuites>")
        return {"returncode": "0"}

    assert scaffold(tmp_path, pack, "items", "Items", run=smoke).ok
    suite.save_criteria(tmp_path, number(BRIEF))
    return tmp_path / "items" / "acceptance"


def test_browser_packs_define_locators_that_do_not_exist() -> None:
    for name in ("browser-javascript", "browser-react", "fullstack-node"):
        pack = pack_named(name)
        assert hasattr(pack, "locators_that_do_not_exist"), f"{name} must declare locators_that_do_not_exist"
        assert pack.locators_that_do_not_exist, f"{name} must have non-empty locators_that_do_not_exist"


def test_suite_catches_nonexistent_locators(tmp_path: Path) -> None:
    acceptance = _scaffolded(tmp_path)
    acceptance.mkdir(parents=True, exist_ok=True)
    (acceptance / "items.spec.js").write_text(
        "test('[AC-1] displays items', async ({ page }) => {\n"
        "  await page.goto('/');\n"
        "  const input = page.getByLabelText('Name', { exact: true });\n"
        "  const query = page.queryByRole('region');\n"
        "  const finder = page.findByText('Submit');\n"
        "});\n"
    )

    problems = suite.locators_that_do_not_exist(tmp_path)
    assert len(problems) == 1, f"Expected 1 problem report, got: {problems}"
    problem = problems[0]
    assert "items.spec.js" in problem
    assert "getByLabelText" in problem
    assert "line(s) 3, 4, 5" in problem


def test_suite_catches_invalid_role_locators(tmp_path: Path) -> None:
    acceptance = _scaffolded(tmp_path)
    acceptance.mkdir(parents=True, exist_ok=True)
    (acceptance / "items.spec.js").write_text(
        "test('[AC-1] displays items', async ({ page }) => {\n"
        "  await page.goto('/');\n"
        "  const area = page.getByRole('textarea', { name: 'Details', exact: true });\n"
        "  const field = page.getByRole('input', { name: 'Name', exact: true });\n"
        "});\n"
    )

    problems = suite.locators_that_do_not_exist(tmp_path)
    assert len(problems) == 1, f"Expected 1 problem report, got: {problems}"
    problem = problems[0]
    assert "items.spec.js" in problem
    assert "textarea" in problem
    assert "line(s) 3, 4" in problem


def test_suite_allows_valid_playwright_locators(tmp_path: Path) -> None:
    acceptance = _scaffolded(tmp_path)
    acceptance.mkdir(parents=True, exist_ok=True)
    (acceptance / "items.spec.js").write_text(
        "test('[AC-1] displays items', async ({ page }) => {\n"
        "  await page.goto('/');\n"
        "  const input = page.getByLabel('Name', { exact: true });\n"
        "  const role = page.getByRole('heading', { name: 'Welcome' });\n"
        "  const text = page.getByText('Submit');\n"
        "  const alt = page.getByAltText('Logo');\n"
        "  const title = page.getByTitle('Help');\n"
        "});\n"
    )

    problems = suite.locators_that_do_not_exist(tmp_path)
    assert problems == []


def test_acceptance_review_calls_locators_that_do_not_exist() -> None:
    from app.acceptance import suite

    source = inspect.getsource(acceptance_nodes.acceptance_review) + inspect.getsource(suite.tests_that_cannot_pass)
    assert "suite.tests_that_cannot_pass(root, result)" in inspect.getsource(acceptance_nodes.acceptance_review)
    assert "locators_that_do_not_exist" in source, (
        "acceptance_review must check for locators_that_do_not_exist before locking"
    )


def test_acceptance_for_round_includes_locators_that_do_not_exist() -> None:
    from app.acceptance import suite

    source = inspect.getsource(acceptance_nodes.acceptance_for_round) + inspect.getsource(suite.tests_that_cannot_pass)
    assert "suite.tests_that_cannot_pass(root, result)" in inspect.getsource(acceptance_nodes.acceptance_for_round)
    assert "locators_that_do_not_exist" in source, (
        "acceptance_for_round must check locators_that_do_not_exist to reopen broken tests"
    )


def test_acceptance_review_rejects_nonexistent_locators(tmp_path: Path, monkeypatch) -> None:
    acceptance = _scaffolded(tmp_path)
    acceptance.mkdir(parents=True, exist_ok=True)
    (acceptance / "items.spec.js").write_text(
        "test('[AC-1] displays items', async ({ page }) => {\n"
        "  await page.goto('/');\n"
        "  const input = page.getByLabelText('Name', { exact: true });\n"
        "});\n"
    )
    report = junit.Report(found=True, tests=[junit.TestResult(name="[AC-1] displays items", outcome="failed", message="connection refused")])
    monkeypatch.setattr(suite, "run", lambda root: suite.AcceptanceResult(ran=True, command="npm run test:acceptance", report=report))
    monkeypatch.setattr(suite, "gaps", lambda root: [])
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "acceptance_round": 1}

    update = acceptance_nodes.acceptance_review(state, {"configurable": {"thread_id": "t"}}, SimpleNamespace(judgement_model=None, checkpointer=None, repo_root=tmp_path, allow_subdirectories=False))
    assert update.get("stage") == "acceptance_author"
    feedback = update.get("acceptance_feedback") or []
    assert any("getByLabelText" in item for item in feedback)


@pytest.mark.parametrize("word", ["task", "tasks", "to-do", "todo", "button", "click", "checkbox"])
def test_new_locator_rule_contains_no_forbidden_words(word: str) -> None:
    from app.stacks.packs._javascript import PLAYWRIGHT_LOCATORS_RULE

    assert not re.search(rf"\b{re.escape(word)}\b", PLAYWRIGHT_LOCATORS_RULE, re.I), f"Forbidden word found: {word}"

