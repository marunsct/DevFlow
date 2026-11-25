"""A failed page test's evidence keeps what it looked for, and the page at load stays labelled as such (LF.1458-1461).

Measured on the saved results of 19 runs (263 failed tests) and the briefs of one fullstack run:

- LF.1459: 45 failure lines in 6 runs said only `Error: expect(locator).toBeVisible() failed` or `TimeoutError:
  locator.fill: Timeout 3000ms exceeded.`; the locator and what was found followed and were dropped.
- LF.1460: the page a test failed on was cut at its first 900 characters; two pages held the field their test waited
  for (`getByLabel('Email')`) at characters 990 and 996, after the site's navigation, and read as without it.
- LF.1458: a refreshed criterion's defect lost the label of its page snapshot, so the page at load ("No bookmarks
  yet") read as the page the test met, which listed the bookmark.
- LF.1461: readers took the runner's heading for the error, so a thrown `Error: Login rate limited` was never read.

Every message, page and stored text below is the run's own.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from xml.sax.saxutils import escape

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "evidence_records"
MESSAGES = json.loads((FIXTURES / "page_test_messages.json").read_text(encoding="utf-8"))
PAGES = json.loads((FIXTURES / "failure_pages_cut.json").read_text(encoding="utf-8"))
LABEL = json.loads((FIXTURES / "page_at_load_label.json").read_text(encoding="utf-8"))
THROWN = json.loads((FIXTURES / "thrown_behind_the_heading.json").read_text(encoding="utf-8"))


# --- LF.1459: the locator travels with the matcher ------------------------------------------------------------------


@pytest.mark.parametrize("record", MESSAGES, ids=[m["said"][:40] for m in MESSAGES])
def test_a_page_test_s_line_says_what_it_looked_for(record) -> None:
    from app.graph.acceptance_nodes import the_failed_tests_line

    line = the_failed_tests_line([{"name": record["name"], "message": record["message"]}])

    assert "getBy" in line or "locator(" in line


def test_a_missing_element_s_line_says_it_was_not_found() -> None:
    from app.graph.acceptance_nodes import the_failed_tests_line

    line = the_failed_tests_line([LABEL["test"]])

    assert "getByRole('listitem').filter({ hasText: 'AC3 Delete Me' })" in line
    assert "element(s) not found" in line
    assert "ui.spec.js:224:1" not in line


# --- LF.1460: the page is cut around what the test looked for --------------------------------------------------------


BRIEF = """# Product Brief: Shop

## Requirements
1. **Features**:
   - Sign in

## Acceptance Criteria
- Sign in
"""


def test_the_page_a_test_failed_on_keeps_the_field_it_waited_for(tmp_path) -> None:
    from app.acceptance import suite
    from app.acceptance.criteria import number
    from app.stacks import pack_named
    from app.stacks.scaffold import scaffold

    pack = pack_named("browser-javascript")
    report_holder: dict[str, str] = {"xml": "<testsuites><testcase name='smoke'/></testsuites>"}

    def run(argv, category, working_directory):
        commands = pack.commands(working_directory)
        if category == "test":
            is_unit = list(argv) == commands["unit_test"]
            target = tmp_path / working_directory / (pack.unit_report if is_unit else pack.acceptance_report)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(report_holder["xml"] if not is_unit else "<testsuites><testcase name='smoke'/></testsuites>")
        return {"returncode": "0", "stdout": "", "stderr": ""}

    assert scaffold(tmp_path, pack, "shop", "Shop", run=run).ok
    suite.save_criteria(tmp_path, number(BRIEF))
    spec = tmp_path / "shop/acceptance/auth.spec.js"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("import { test } from '@playwright/test';\n" + "".join(
        f"test('{name}', async () => {{}});\n" for name in PAGES))
    for record in PAGES.values():
        context = tmp_path / "shop/test-results/evidence" / record["folder"] / "error-context.md"
        context.parent.mkdir(parents=True, exist_ok=True)
        context.write_text(record["error_context"], encoding="utf-8")
    report_holder["xml"] = "<testsuites><testsuite>" + "".join(
        f"<testcase name='{escape(name)}'><failure message='{escape(name)}'>{escape(record['message'])}</failure></testcase>"
        for name, record in PAGES.items()) + "</testsuite></testsuites>"

    result = suite.run(tmp_path, runner=run)

    pages = {test.name: suite.page_it_failed_on(test.message) for test in result.report.tests if test.name in PAGES}
    assert set(pages) == set(PAGES)
    for page in pages.values():
        # The tree itself, not the hint after it that names the nearest miss.
        tree = page.split("\nNearly there:", 1)[0]
        assert 'textbox "Email *"' in tree


def test_a_page_with_nothing_sought_on_it_keeps_its_head() -> None:
    from app.acceptance.failure_page import kept

    page = "\n".join(f"  - link \"Item {n}\"" for n in range(200))

    shown = kept(page, ["Nowhere"], 500)

    assert shown.startswith('  - link "Item 0"') and "more line(s)" in shown and len(shown) < 600


def test_each_criterion_s_first_failure_has_a_page_before_a_ninth_of_one() -> None:
    from app.acceptance.failure_page import in_order

    tests = [*(["AC-1"],) * 9, ["AC-2"]]

    order = in_order(tests, lambda criteria: criteria)

    assert order[:2] == [0, 9]


# --- LF.1458: the page at load keeps its label when the defect is refreshed ---------------------------------------


@pytest.mark.parametrize("stored_label", [
    " What the product shows when it loads, before any test touches it:\n",  # as raised before this fix
    None,  # as raised now
])
def test_a_refreshed_criterion_s_defect_keeps_the_label_of_the_page_at_load(stored_label) -> None:
    from app.graph.acceptance_nodes import WHAT_THE_PRODUCT_SHOWS
    from app.graph.fresh_evidence import with_the_tests_now

    label = stored_label if stored_label is not None else WHAT_THE_PRODUCT_SHOWS
    stored = f"{LABEL['first_line']}{label}{LABEL['page_at_load']}"
    defect = SimpleNamespace(description=LABEL["description"])
    saved = {"criteria": {LABEL["criterion"]: {"tests": [LABEL["test"]]}}}

    shown = with_the_tests_now(stored, defect, saved)

    assert "before any test touches it" in shown
    assert shown.index("before any test touches it") < shown.index("No bookmarks yet")
    assert "element(s) not found" in shown.splitlines()[0]


# --- LF.1461: the error a test threw is read past the runner's heading --------------------------------------------


def test_an_error_a_test_threw_is_read_past_the_runner_s_heading() -> None:
    from app.acceptance.first_failing_step import read, what_it_threw

    assert what_it_threw(THROWN["rate"]["message"]) == "Error: Login rate limited"
    assert what_it_threw(THROWN["s401"]["message"]) == "Error: Login failed with status 401"
    assert what_it_threw(THROWN["r429"]["message"]) == ""
    read_now = read([(THROWN[k].get("criterion", "AC-2"), THROWN[k]) for k in ("rate", "s401", "r429")])
    assert [failure.answer for failure in read_now] == ["429", "401", "429"]


def test_two_tests_that_threw_the_same_error_stop_at_the_same_step() -> None:
    from app.acceptance.failure_said import first_line_said

    assert first_line_said(THROWN["rate"]["message"]) == first_line_said(THROWN["rate2"]["message"])
    assert first_line_said(THROWN["rate"]["message"]) == "Error: Login rate limited"
