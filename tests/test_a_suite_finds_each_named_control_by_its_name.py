"""Every control the brief names is found by that name, and by a locator that refuses two.

Measured on one run. The brief gave every item a box labelled "Done" and three
filters named "All", "Active" and "Completed". The locked suite found the box
by a class and pressed the filters with a selector handed to the page, which
acts on the first match. The product gave the box no label and drew every
filter twice; the suite passed 9 of 9, and three of the benchmark's ten hidden
tests - which find each control by its name, strictly - failed.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance import junit, suite
from app.acceptance.criteria import number
from app.acceptance.requests import build_author_request
from app.analysis.interface_checks import controls_the_brief_names
from app.graph import acceptance_nodes as nodes
from app.stacks import pack_named
from app.stacks.scaffold import scaffold

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")

BRIEF = """# Notes
## Interface
- A text field labelled "Name", a text area labelled "Body", and a button named "Keep".
- Each note is an item of a list. Each has a box labelled "Pinned".
- Two buttons named "Everything" and "Pinned only" choose which are shown.
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
    acceptance = tmp_path / "notes" / "acceptance"
    acceptance.mkdir(parents=True, exist_ok=True)
    return acceptance


class TestTheNamesABriefGives:
    def test_each_quoted_name_of_a_control_in_order(self) -> None:
        assert controls_the_brief_names(BRIEF) == [
            "Name", "Body", "Keep", "Pinned", "Everything", "Pinned only",
        ]

    @pytest.mark.parametrize("benchmark, expected", [
        ("web-todo", ["Title", "Description", "Add task", "Done", "Edit", "Edit title",
                      "Save", "Delete", "All", "Active", "Completed"]),
        ("fullstack-bookmarks", ["Title", "URL", "Tag", "Save bookmark", "Delete", "Filter by tag"]),
        ("textkit-lib", []),
        ("notes-api", []),
    ])
    def test_the_benchmarks_briefs(self, benchmark, expected) -> None:
        brief = (Path(__file__).resolve().parents[1] / "benchmarks" / benchmark / "brief.md").read_text()

        assert controls_the_brief_names(brief) == expected

    def test_a_name_given_to_something_no_one_operates_is_not_a_control(self) -> None:
        assert controls_the_brief_names('A weekly report named "Summary" is emailed.') == []


class TestASuiteThatNeverAsksForTheName:
    def test_a_control_found_another_way_is_named(self, tmp_path) -> None:
        acceptance = _scaffolded(tmp_path)
        (acceptance / "notes.spec.js").write_text(
            "test('[AC-1] keeps', async ({ page }) => {\n"
            "  await page.getByLabel('Name', { exact: true }).fill('x');\n"
            "  await page.getByLabel('Body', { exact: true }).fill('y');\n"
            "  await page.getByRole('button', { name: 'Keep', exact: true }).click();\n"
            "  await page.getByRole('listitem').getByRole('checkbox').check();\n"
            "  await page.getByRole('button', { name: /^Everything$/ }).click();\n"
            "});\n"
        )

        [problem] = suite.controls_never_found_by_name(tmp_path, BRIEF)

        assert '"Pinned", "Pinned only"' in problem
        assert '"Name"' not in problem and '"Everything"' not in problem

    def test_a_suite_that_finds_every_one_by_name_passes(self, tmp_path) -> None:
        acceptance = _scaffolded(tmp_path)
        (acceptance / "notes.spec.js").write_text(
            "test('[AC-1] keeps', async ({ page }) => {\n"
            + "".join(f"  await page.getByLabel('{name}', {{ exact: true }}).fill('x');\n" for name in ("Name", "Body", "Pinned"))
            + "".join(f"  await page.getByRole('button', {{ name: \"{name}\", exact: true }}).click();\n"
                      for name in ("Keep", "Everything", "Pinned only"))
            + "});\n"
        )

        assert suite.controls_never_found_by_name(tmp_path, BRIEF) == []

    def test_a_brief_that_names_nothing_asks_nothing(self, tmp_path) -> None:
        acceptance = _scaffolded(tmp_path)
        (acceptance / "notes.spec.js").write_text("test('[AC-1] x', async ({ page }) => {});\n")

        assert suite.controls_never_found_by_name(tmp_path, "# Notes\n- Add a note\n") == []


class TestALocatorThatPicksOne:
    @pytest.mark.parametrize("line", [
        "await page.click('text=Everything');",
        "await page.fill('[aria-label=\"Name\"]', 'x');",
        "await page.getByRole('button', { name: 'Keep', exact: true }).first().click();",
        "await page.getByLabel('Pinned').nth(1).check();",
        "await page.locator('li', { hasText: 'x' }).last().click();",
        "await page.getByRole('listitem').filter({ hasText: 'x' }).first().click();",
    ])
    def test_is_named(self, tmp_path, line) -> None:
        acceptance = _scaffolded(tmp_path)
        (acceptance / "notes.spec.js").write_text(
            f"test('[AC-1] keeps', async ({{ page }}) => {{\n  {line}\n}});\n"
        )

        [problem] = suite.locators_that_pick_one(tmp_path)

        assert "line(s) 2" in problem

    @pytest.mark.parametrize("line", [
        "await page.getByRole('listitem').first().click();",
        "await page.keyboard.press('Enter');",
        "await page.getByLabel('Name', { exact: true }).fill('x');",
        "await expect(page.getByRole('listitem').nth(0)).toContainText('x');",
    ])
    def test_a_strict_one_is_not(self, tmp_path, line) -> None:
        acceptance = _scaffolded(tmp_path)
        (acceptance / "notes.spec.js").write_text(
            f"test('[AC-1] keeps', async ({{ page }}) => {{\n  {line}\n}});\n"
        )

        assert suite.locators_that_pick_one(tmp_path) == []

    def test_one_problem_per_file_with_every_line(self, tmp_path) -> None:
        acceptance = _scaffolded(tmp_path)
        (acceptance / "notes.spec.js").write_text(
            "test('[AC-1] keeps', async ({ page }) => {\n"
            "  await page.fill('#name', 'x');\n"
            "  await page.getByLabel('Body', { exact: true }).fill('y');\n"
            "  await page.click('text=Keep');\n"
            "});\n"
        )

        [problem] = suite.locators_that_pick_one(tmp_path)

        assert "line(s) 2, 4" in problem


class TestACssSelectorOnAControl:
    @pytest.mark.parametrize("selector", [
        "input[type=\"checkbox\"].done",
        "#list li",
        "li.pinned",
        "[aria-label=\"Name\"]",
        "[data-filter=\"all\"]",
    ])
    def test_is_something_nobody_sees(self, tmp_path, selector) -> None:
        acceptance = _scaffolded(tmp_path)
        (acceptance / "notes.spec.js").write_text(
            f"test('[AC-1] keeps', async ({{ page }}) => {{\n  await page.locator('{selector}').waitFor();\n}});\n"
        )

        assert len(suite.locators_nobody_sees(tmp_path)) == 1

    @pytest.mark.parametrize("selector", [
        "meta[name=\"viewport\"]",
        "role=listitem",
        "text=Mr. Smith",
        "ul",
    ])
    def test_the_head_an_engine_or_a_bare_element_is_not(self, tmp_path, selector) -> None:
        acceptance = _scaffolded(tmp_path)
        (acceptance / "notes.spec.js").write_text(
            f"test('[AC-1] keeps', async ({{ page }}) => {{\n  await page.locator('{selector}').waitFor();\n}});\n"
        )

        assert suite.locators_nobody_sees(tmp_path) == []


def test_the_review_sends_a_suite_that_misses_them_back_to_qa(tmp_path, monkeypatch) -> None:
    acceptance = _scaffolded(tmp_path)
    (acceptance / "notes.spec.js").write_text(
        "test('[AC-1] keeps', async ({ page }) => { await page.click('text=Keep'); });\n"
    )
    report = junit.Report(found=True, tests=[junit.TestResult(name="[AC-1] keeps", outcome="failed", message="x")])
    monkeypatch.setattr(suite, "run", lambda root: suite.AcceptanceResult(ran=True, command="npm run test:acceptance", report=report))
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "document": SimpleNamespace(text=BRIEF),
        "acceptance_round": 1,
    }

    update = nodes.acceptance_review(state, {"configurable": {"thread_id": "t"}}, None)

    assert update["stage"] == "acceptance_author"
    feedback = " ".join(update["acceptance_feedback"])
    assert "whichever match comes first" in feedback and '"Pinned only"' in feedback


def test_qa_is_given_the_names_before_it_writes(tmp_path) -> None:
    _scaffolded(tmp_path)

    text = build_author_request(tmp_path, suite.criteria(tmp_path), brief=BRIEF)["messages"][0]["content"]

    assert '--- The names the brief gives its controls ---\n- "Name"\n- "Body"' in text


def test_what_the_rules_say_names_no_product_and_no_control(tmp_path) -> None:
    from app.acceptance.requests import _the_names_the_brief_gives

    acceptance = _scaffolded(tmp_path)
    (acceptance / "notes.spec.js").write_text("test('[AC-1] x', async ({ page }) => { await page.fill('#n', 'x'); });\n")
    rules = " ".join([
        _the_names_the_brief_gives('A field labelled "Q".'),
        *(problem.split("(`", 1)[0] + problem.split("`)", 1)[-1] for problem in suite.locators_that_pick_one(tmp_path)),
        *suite.controls_never_found_by_name(tmp_path, 'A field labelled "Q".'),
    ]).lower()

    assert rules
    for word in BANNED:
        assert not re.search(rf"\b{re.escape(word)}\b", rules), word


class TestARoleFoundByANameItNeverHas:
    """Measured in a browser on one run: `getByRole('listitem', { name: 'Original' })`
    found 0 items on a page listing "Original", `filter({ hasText })` found 1, and
    the locked edit tests that used it could never pass."""

    def test_is_named_with_its_lines(self, tmp_path) -> None:
        acceptance = _scaffolded(tmp_path)
        (acceptance / "notes.spec.js").write_text(
            "test('[AC-1] keeps', async ({ page }) => {\n"
            "  const one = page.getByRole('listitem', { name: 'Original' }).first();\n"
            "  const two = page.getByRole('listitem').filter({ hasText: 'Original' });\n"
            "  await page.getByRole('button', { name: 'Keep', exact: true }).click();\n"
            "});\n"
        )

        [problem] = suite.locators_by_a_name_the_role_never_has(tmp_path)

        assert "line(s) 2 " in problem and "filter it by the text it shows" in problem
        for word in BANNED:
            assert not re.search(rf"\b{word}\b", problem.split("(`")[0].lower() + problem.split("`)")[-1].lower()), word

    def test_the_guide_says_how_to_find_an_item(self) -> None:
        from app.stacks.packs._javascript import FIND_CONTROLS

        assert "A list item takes no name from its text" in " ".join(FIND_CONTROLS.split())
