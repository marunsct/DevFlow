"""An acceptance suite finds each control by the name a person sees, never by what nobody sees.

Measured on one run: the brief said a field was "labelled" with a name, QA's
locked suite found it by its placeholder, the product gave it a placeholder and
no label, and the suite passed. Three of the benchmark's hidden tests - which
find the field by its label - failed. The pack's own guide had recommended
`getByPlaceholder`.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from app.acceptance import junit, suite
from app.acceptance.criteria import number
from app.graph import acceptance_nodes as nodes
from app.stacks import pack_named
from app.stacks.packs import ALL_PACKS
from app.stacks.scaffold import scaffold

PAGES = {"browser-javascript", "browser-react", "fullstack-node"}

BRIEF = """# Notes
## Features
- Add a note
"""


def _scaffolded(tmp_path: Path) -> Path:
    pack = pack_named("browser-javascript")

    def smoke(argv, category, wd):
        unit = list(argv) == pack.commands(wd)["unit_test"]
        report = tmp_path / wd / (pack.unit_report if unit else pack.acceptance_report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("<testsuites><testcase name='smoke'/></testsuites>")
        return {"returncode": "0"}

    assert scaffold(tmp_path, pack, "notes", "Notes", run=smoke).ok
    suite.save_criteria(tmp_path, number(BRIEF))
    return tmp_path / "notes" / "acceptance"


def test_no_page_pack_recommends_a_locator_nobody_sees() -> None:
    for pack in ALL_PACKS:
        if pack.name not in PAGES:
            continue
        guide = pack.acceptance_guide
        assert "getByLabel(" in guide and "exact: true" in guide, pack.name
        assert not re.search(r"`page\.getByPlaceholder`|`page\.getByTestId`", guide), pack.name
        assert pack.locators_nobody_sees, pack.name


def test_the_rule_s_examples_are_not_any_one_product_s() -> None:
    from app.stacks.packs._javascript import FIND_CONTROLS

    for word in ("task", "tasks", "todo", "to-do", "title", "note", "notes", "description"):
        assert not re.search(rf"\b{re.escape(word)}\b", FIND_CONTROLS, re.I), word


def test_a_suite_that_finds_a_control_by_its_placeholder_is_named(tmp_path) -> None:
    acceptance = _scaffolded(tmp_path)
    acceptance.mkdir(parents=True, exist_ok=True)
    (acceptance / "notes.spec.js").write_text(
        "test('[AC-1] adds', async ({ page }) => {\n"
        "  await page.getByLabel('Name', { exact: true }).fill('x');\n"
        "  await page.getByPlaceholder('Details').fill('y');\n"
        "  await page.getByTestId('save').click();\n"
        "});\n"
    )

    [problem] = suite.locators_nobody_sees(tmp_path)

    assert "line(s) 3, 4" in problem and "getByPlaceholder('Details')" in problem


def test_every_line_of_a_file_is_named_in_one_round(tmp_path) -> None:
    """Naming only the first let QA fix that line and hear of the next a round
    later: one run's suite was sent back for line 16 of a file, then line 21."""
    acceptance = _scaffolded(tmp_path)
    acceptance.mkdir(parents=True, exist_ok=True)
    (acceptance / "notes.spec.js").write_text(
        "test('[AC-1] adds', async ({ page }) => {\n"
        "  const one = page.locator('.entry').filter({ hasText: 'a' });\n"
        "  await page.getByLabel('Name', { exact: true }).fill('x');\n"
        "  await expect(page.locator('.entry').filter({ hasText: 'b' })).toHaveCount(1);\n"
        "});\n"
    )

    [problem] = suite.locators_nobody_sees(tmp_path)

    assert "line(s) 2, 4" in problem


def test_a_suite_that_finds_them_by_name_is_not(tmp_path) -> None:
    acceptance = _scaffolded(tmp_path)
    acceptance.mkdir(parents=True, exist_ok=True)
    (acceptance / "notes.spec.js").write_text(
        "test('[AC-1] adds', async ({ page }) => {\n"
        "  await page.getByLabel('Details', { exact: true }).fill('y');\n"
        "  await page.getByRole('button', { name: 'Save', exact: true }).click();\n"
        "});\n"
    )
    assert suite.locators_nobody_sees(tmp_path) == []


def test_the_acceptance_review_sends_it_back_to_qa(tmp_path, monkeypatch) -> None:
    acceptance = _scaffolded(tmp_path)
    acceptance.mkdir(parents=True, exist_ok=True)
    (acceptance / "notes.spec.js").write_text(
        "test('[AC-1] adds', async ({ page }) => { await page.getByPlaceholder('Details').fill('y'); });\n"
    )
    report = junit.Report(found=True, tests=[junit.TestResult(name="[AC-1] adds", outcome="failed", message="not found")])
    monkeypatch.setattr(suite, "run", lambda root: suite.AcceptanceResult(ran=True, command="npm run test:acceptance", report=report))
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "acceptance_round": 1}

    update = nodes.acceptance_review(state, {"configurable": {"thread_id": "t"}}, None)

    assert update["stage"] == "acceptance_author"
    assert any("no person sees" in problem for problem in update["acceptance_feedback"])
    assert not suite.is_locked(tmp_path)


def test_an_assertion_the_runner_does_not_define_is_named(tmp_path) -> None:
    acceptance = _scaffolded(tmp_path)
    types = tmp_path / "notes" / "node_modules" / "playwright" / "types"
    types.mkdir(parents=True)
    (types / "test.d.ts").write_text("interface Matchers {\n  toBeChecked(options?: {}): Promise<void>;\n  toHaveText<T>(x: T): void;\n}\n")
    acceptance.mkdir(parents=True, exist_ok=True)
    (acceptance / "notes.spec.js").write_text(
        "test('[AC-1] adds', async ({ page }) => {\n"
        "  await expect(page.getByLabel('Done', { exact: true })).toBeChecked();\n"
        "  await expect(page.getByLabel('Done', { exact: true })).toBeUnchecked();\n"
        "  await expect(page.getByRole('listitem')).not.toHaveText('x');\n"
        "});\n"
    )

    problems = suite.assertions_that_do_not_exist(tmp_path)

    assert len(problems) == 1 and "line 3" in problems[0] and "toBeUnchecked" in problems[0]


def test_without_the_runner_s_definitions_nothing_is_guessed(tmp_path) -> None:
    acceptance = _scaffolded(tmp_path)
    acceptance.mkdir(parents=True, exist_ok=True)
    (acceptance / "notes.spec.js").write_text("test('[AC-1] adds', async () => { expect(1).toBeAnything(); });\n")
    assert suite.assertions_that_do_not_exist(tmp_path) == []


def test_a_css_selector_on_role_is_named(tmp_path) -> None:
    """One run's locked suite found every entry by `locator('[role="listitem"]')`,
    which matches only an explicit attribute - never a plain `<li>`."""
    acceptance = _scaffolded(tmp_path)
    acceptance.mkdir(parents=True, exist_ok=True)
    (acceptance / "notes.spec.js").write_text(
        "test('[AC-1] adds', async ({ page }) => {\n"
        "  await page.getByLabel('Name', { exact: true }).fill('x');\n"
        "  await expect(page.locator('[role=\"listitem\"]')).toHaveCount(1);\n"
        "  await expect(page.getByRole('listitem')).toHaveCount(1);\n"
        "});\n"
    )

    problems = suite.locators_nobody_sees(tmp_path)

    assert len(problems) == 1 and "line(s) 3 " in problems[0]


def test_the_guide_warns_against_a_role_selector() -> None:
    for pack in ALL_PACKS:
        if pack.name in PAGES:
            assert "matches only an element" in pack.acceptance_guide, pack.name


def test_a_control_that_leaves_the_page_is_clicked_not_checked() -> None:
    """`check()` confirms the new state afterwards. One run's locked suite
    checked the last record in a view of unfinished ones; the product rightly
    removed it, `check()` timed out, and two criteria were deferred on a product
    the hidden tests passed 10 of 10."""
    from app.stacks.packs._javascript import FIND_CONTROLS

    assert "is a `click()`, not `check()` or `uncheck()`" in FIND_CONTROLS


def test_a_method_of_an_ordinary_value_is_not_an_assertion(tmp_path) -> None:
    """One run's suite built unique titles with `Math.random().toString(36)`; it
    was sent back three times for calling `toString`, which no runner defines."""
    acceptance = _scaffolded(tmp_path)
    types = tmp_path / "notes" / "node_modules" / "playwright" / "types"
    types.mkdir(parents=True)
    (types / "test.d.ts").write_text("interface Matchers {\n  toBeChecked(options?: {}): Promise<void>;\n}\n")
    acceptance.mkdir(parents=True, exist_ok=True)
    (acceptance / "notes.spec.js").write_text(
        "const name = () => `n-${Math.random().toString(36).slice(2)}`;\n"
        "test('[AC-1] adds', async ({ page }) => {\n"
        "  const when = new Date().toISOString();\n"
        "  await expect(page.getByLabel('Done', { exact: true })).toBeChecked();\n"
        "  await expect(\n    page.getByLabel('Done', { exact: true })\n  ).toBeUnchecked();\n"
        "});\n"
    )

    problems = suite.assertions_that_do_not_exist(tmp_path)

    assert len(problems) == 1 and "line 7" in problems[0] and "toBeUnchecked" in problems[0]


def test_assertions_that_do_not_exist_catches_negative_matchers(tmp_path: Path) -> None:
    acceptance = _scaffolded(tmp_path)
    types = tmp_path / "notes" / "node_modules" / "playwright" / "types"
    types.mkdir(parents=True, exist_ok=True)
    (types / "test.d.ts").write_text("interface Matchers {\n  toHaveAttribute(name: string, value: string): Promise<void>;\n}\n")
    acceptance.mkdir(parents=True, exist_ok=True)
    (acceptance / "notes.spec.js").write_text(
        "test('[AC-1] checks', async ({ page }) => {\n"
        "  await expect(page.locator('#item')).notToHaveAttribute('hidden', '');\n"
        "});\n"
    )

    problems = suite.assertions_that_do_not_exist(tmp_path)

    assert len(problems) == 1 and "notToHaveAttribute" in problems[0]


def test_assertions_that_do_not_exist_catches_callable_not(tmp_path: Path) -> None:
    acceptance = _scaffolded(tmp_path)
    types = tmp_path / "notes" / "node_modules" / "playwright" / "types"
    types.mkdir(parents=True, exist_ok=True)
    (types / "test.d.ts").write_text("interface Matchers {\n  toHaveAttribute(name: string, value: string): Promise<void>;\n}\n")
    acceptance.mkdir(parents=True, exist_ok=True)
    (acceptance / "notes.spec.js").write_text(
        "test('[AC-1] checks', async ({ page }) => {\n"
        "  await expect(page.locator('#item')).not().toHaveAttribute('hidden', '');\n"
        "});\n"
    )

    problems = suite.assertions_that_do_not_exist(tmp_path)

    assert len(problems) == 1 and "calls `not`" in problems[0]


