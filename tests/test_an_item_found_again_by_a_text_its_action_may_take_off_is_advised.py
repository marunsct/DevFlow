"""A test that looks inside an item again by the text it found it by, after acting inside it, is advised about - never
reopened for it alone - and a product fixer shown such a failure is told what lets the test find the item.

Measured on one run: a locked page test found an item by its title through a helper of the file, pressed "Edit" inside
it, then looked inside it for the "Edit title" field. The product, as its specification said, swapped the title for that
field (a field's value is not text), the locator matched nothing, and fixers spent about forty minutes on the product
without being told. Only text is read here and the reports are made up: no suite runs.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance import junit, suite
from app.agents import suite_dispute
from app.graph import acceptance_nodes
from app.stacks import contract, pack_named
from app.stacks.packs import _javascript as js

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CORPUS = Path(__file__).parent / "fixtures" / "locked_suites"
TITLE = "[AC-1] edit a title"
HELPER = """import { test, expect } from '@playwright/test';

function itemTitled(page, titleText) {
  return page.getByRole('listitem').filter({ hasText: titleText });
}
"""


def _a_test(found: str, after: str, act: str = "await item.getByRole('link', { name: 'Edit', exact: true }).dblclick();") -> str:
    return HELPER + f"""
test('{TITLE}', async ({{ page }}) => {{
  await page.goto('/');
  await page.getByLabel('Title', {{ exact: true }}).fill('Old title');
  await page.getByRole('menuitem', {{ name: 'Add', exact: true }}).press('Enter');

  const item = {found};
  {act}
{after}
}});
"""


MEASURED = _a_test("itemTitled(page, 'Old title')",
                   "  await expect(item.getByLabel('Edit title', { exact: true })).toBeVisible();")
#: What the runner says when the item's locator matched nothing.
NOT_FOUND = (
    "Error: expect(locator).toBeVisible() failed\n\n"
    "Locator: getByRole('listitem').filter({ hasText: 'Old title' }).getByLabel('Edit title', { exact: true })\n"
    "Expected: visible\nTimeout: 5000ms\nError: element(s) not found"
)


def _workspace(tmp_path: Path, spec: str) -> Path:
    contract.write(tmp_path, pack_named("fullstack-node"), "records", "Records")
    (tmp_path / "records" / "acceptance").mkdir(parents=True)
    (tmp_path / "records" / "acceptance" / "workflow.spec.js").write_text(spec, encoding="utf-8")
    return tmp_path


def test_the_measured_test_through_a_helper_of_the_file_is_advised_by_file_line_and_text(tmp_path):
    root = _workspace(tmp_path, MEASURED)

    [advice] = suite.items_found_again_after_an_action(root)

    assert advice.startswith("`records/acceptance/workflow.spec.js` line 14 ")
    assert '"Old title"' in advice and "test id" in advice and "position" in advice
    assert advice.endswith(suite.ADVICE_ONLY)
    assert not BANNED.search(advice)


@pytest.mark.parametrize("spec", [
    _a_test("page.getByRole('listitem').filter({ hasText: 'Old title' })",
            "  await item.getByLabel('Edit title').fill('New title');"),
    HELPER.replace("function itemTitled(page, titleText) {\n  return",
                   "const itemTitled = (page, titleText) =>").replace(";\n}\n", ";\n")
    + MEASURED[len(HELPER):],
    _a_test("itemTitled(page, 'Old title')", "  await expect(item.getByRole('textbox')).toHaveValue('Old title');",
            act="const opener = item.getByRole('link', { name: 'Edit' });\n  await opener.tap();"),
], ids=["written-out", "arrow-helper", "through-a-bound-control"])
def test_each_way_of_finding_the_item_and_acting_inside_it_is_read(spec):
    assert [said for _, said in js.items_found_again_by_a_text_after_an_action(spec)] == ["Old title"]


@pytest.mark.parametrize("spec", [
    # Found again by a stable role and name after the action.
    _a_test("itemTitled(page, 'Old title')",
            "  const editing = page.getByRole('listitem').filter({ has: page.getByLabel('Edit title') });\n"
            "  await expect(editing.getByLabel('Edit title')).toBeVisible();"),
    # Acts, and never looks inside the item again.
    _a_test("itemTitled(page, 'Old title')", "  await expect(item).toHaveCount(0);",
            act="await item.getByRole('link', { name: 'Remove' }).dblclick();"),
    # Looks inside it for the very text it was found by: the test itself expects it kept.
    _a_test("itemTitled(page, 'Old title')", "  await expect(item.getByText('Old title')).toBeVisible();"),
    # Looks inside before acting only.
    _a_test("itemTitled(page, 'Old title')", "", act="await item.getByLabel('Done').check();"),
], ids=["found-again-by-role", "never-looks-inside", "same-text", "before-only"])
def test_a_test_that_does_not_lose_its_item_is_left_alone(spec):
    assert js.items_found_again_by_a_text_after_an_action(spec) == []


def test_the_advice_never_counts_as_a_test_that_cannot_pass(tmp_path):
    root = _workspace(tmp_path, MEASURED)
    suite.lock(root)
    result = suite.AcceptanceResult(ran=True, report=junit.Report(
        tests=[junit.TestResult(name=TITLE, outcome="failed", message=NOT_FOUND)], found=True))

    cannot = suite.findings_that_reopen(root, result, suite.tests_that_cannot_pass(root, result))

    assert not [item for item in cannot if suite.ADVICE_ONLY in item]


def test_a_dispute_is_told_the_advice_and_reopens_nothing_for_it_alone(tmp_path):
    from workflow_nodes import a_dispute

    root = _workspace(tmp_path, MEASURED)
    spec = root / "records" / "acceptance" / "workflow.spec.js"
    judged: list[str] = []

    def the_judge(state, config, *, initial_request, output_key, **kwargs):
        judged.append(" ".join(str(message["content"]) for message in initial_request["messages"]))
        return {output_key: object()}

    _, asked = a_dispute(tmp_path, [(TITLE, "AC-1: x", NOT_FOUND)], [], reopened={}, patches={
        "app.acceptance.suite.suite_files": lambda _: [spec],
        "app.graph.workflow._run_gated_agent": the_judge,
    })

    assert judged and '"Old title" after an action' in judged[0] and "evidence, not proof" in judged[0]
    assert asked["reopen"] == []


def test_what_the_dispute_is_told_avoids_the_banned_words():
    told = suite_dispute.build_dispute_request(
        [(TITLE, "AC-1: x", "m")], "code", "brief", suggested_by_the_code=["`a.spec.js` line 3 looks inside"],
    )["messages"][0]["content"]
    section = told.split("--- What the harness read in these tests' own code that may explain a failure ---")[1]
    assert not BANNED.search(section.split("--- The suite's code ---")[0])


def test_the_qa_lead_reads_the_advice_and_it_sends_nothing_back_by_itself(tmp_path):
    from workflow_nodes import an_acceptance_review

    contract.write(tmp_path, pack_named("browser-react"), "notes", "Notes")
    told: list[str] = []

    def the_qa_lead(state, config, *, output_key, next_stage, initial_request, **kwargs):
        told.append(initial_request["messages"][-1]["content"])
        return {output_key: SimpleNamespace(approved=True, findings=[]), "stage": next_stage}

    spec = MEASURED + "\ntest('[AC-2] remove', async ({ page }) => { await page.goto('/'); });\n" \
                      "test('[AC-3] kept', async ({ page }) => { await page.goto('/'); });\n"
    update = an_acceptance_review(tmp_path, spec, passed=[TITLE, "[AC-2] remove", "[AC-3] kept"],
                                  state={"current_sprint_index": 1},
                                  patches={"app.graph.workflow._run_gated_agent": the_qa_lead})

    assert told, update.get("acceptance_feedback")
    assert acceptance_nodes.ADVICE_HEADING in told[-1]
    assert '"Old title"' in told[-1].split(acceptance_nodes.ADVICE_HEADING, 1)[1]
    assert update.get("stage") != "acceptance_author"
    assert not BANNED.search(acceptance_nodes.ADVICE_HEADING)


def _defects(monkeypatch, tmp_path, message: str, spec: str = MEASURED, reported=()):
    root = _workspace(tmp_path, spec)
    failing = {"id": "AC-1", "text": "a title can be edited",
               "tests": [{"name": TITLE, "outcome": "failed", "message": message}]}
    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda _state: ([failing], "npm run test:acceptance"))
    monkeypatch.setattr(suite, "last_result", lambda _root: {})
    monkeypatch.setattr(acceptance_nodes, "_owner_for", lambda _state, _text: "frontend")
    return acceptance_nodes.failing_due_defects({"repository": SimpleNamespace(root_path=str(root))}, list(reported))


def test_the_fixer_of_a_test_that_lost_its_item_is_told_once_what_lets_the_test_find_it(monkeypatch, tmp_path):
    [defect] = _defects(monkeypatch, tmp_path, NOT_FOUND)

    hint = defect.actual_behavior.split("\n")[-1]
    assert hint.startswith(f"`{TITLE}` finds the item by its text \"Old title\" after acting inside it.")
    assert "keeps \"Old title\" shown" in hint and defect.actual_behavior.count(hint) == 1
    assert not BANNED.search(hint.replace(TITLE, ""))


def test_a_defect_the_round_wrote_itself_carries_the_hint_too(monkeypatch, tmp_path):
    from app.agents.specialists import ReportedDefect

    own = ReportedDefect(description="[AC-1] editing shows no field", severity="major", reproduction_steps="Run it.",
                         expected_behavior="It works.", actual_behavior="not found", affected_files=[], owner="frontend")
    _defects(monkeypatch, tmp_path, NOT_FOUND, reported=[own])
    assert "keeps \"Old title\" shown" in own.actual_behavior


@pytest.mark.parametrize("message, spec", [
    # Another failure: the item was found, its field held another value.
    ("Error: expect(locator).toHaveValue(expected) failed\nExpected: \"New title\"\nReceived: \"Old title\"", MEASURED),
    # Matched nothing, in a test that never acted inside the item before looking inside it.
    (NOT_FOUND, _a_test("itemTitled(page, 'Old title')",
                        "  await expect(item.getByLabel('Edit title', { exact: true })).toBeVisible();", act="")),
], ids=["another-failure", "another-shape"])
def test_no_hint_for_another_failure_or_another_shape(monkeypatch, tmp_path, message, spec):
    [defect] = _defects(monkeypatch, tmp_path, message, spec)
    assert "after acting inside it" not in defect.actual_behavior


def test_the_stored_suites_give_no_advice():
    """The corpus holds the locked suites of runs at a full hidden score; none of them drives a page."""
    found = {str(path.relative_to(CORPUS)): hits
             for path in sorted(CORPUS.rglob("*.spec.*"))
             if (hits := js.items_found_again_by_a_text_after_an_action(path.read_text(encoding="utf-8", errors="replace")))}
    assert found == {}


def test_every_pack_that_reads_locators_reads_this_too():
    for name in ("fullstack-node", "browser-javascript", "browser-react"):
        assert pack_named(name).found_again_after_an_action is js.items_found_again_by_a_text_after_an_action
