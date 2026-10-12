"""The acceptance suite: criteria, the lock, coverage, and the harness's own run of it."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.acceptance import requests, suite
from app.acceptance.criteria import from_brief, number
from app.stacks import pack_named
from app.stacks.scaffold import scaffold
from app.tools.repository import RepositoryToolError, delete_approved_artifact, write_approved_artifact

BRIEF = """# Product Brief: Notes

## Overview
Keep short notes.

## Requirements
1. **User Interface**: a web page
2. **Features**:
   - Add a note with a title
   - Delete a note
3. **Data Storage**: local storage
4. **No authentication required**

## Technical Constraints
- No external dependencies
- Maximum 300 lines of code

## Acceptance Criteria
- Notes persist between page refreshes
- Add a note with a title
"""


def test_criteria_are_the_brief_s_features_and_acceptance_criteria() -> None:
    assert from_brief(BRIEF) == [
        "Add a note with a title",
        "Delete a note",
        "Notes persist between page refreshes",
        "Add a note with a title",
    ]
    numbered = number(BRIEF)
    # The repeat is dropped; constraints and labelled storage choices are not criteria.
    assert [(c.id, c.text) for c in numbered] == [
        ("AC-1", "Add a note with a title"),
        ("AC-2", "Delete a note"),
        ("AC-3", "Notes persist between page refreshes"),
    ]
    assert {c.source for c in numbered} == {"brief"}


def test_a_brief_that_lists_nothing_falls_back_to_the_intake() -> None:
    class Intake:
        success_measures = [
            "A user can export a report as CSV (a success measure; no workflow above covered export)",
            "Reports load in under a second",
        ]

    numbered = number("Build me a reporting tool that people like.", Intake())
    assert [c.text for c in numbered] == ["A user can export a report as CSV", "Reports load in under a second"]
    assert {c.source for c in numbered} == {"intake"}


def _fake_runner(root: Path, pack, report_xml: str | None = None):
    def run(argv, category, working_directory):
        commands = pack.commands(working_directory)
        if category == "test":
            is_unit = list(argv) == commands["unit_test"]
            target = root / working_directory / (pack.unit_report if is_unit else pack.acceptance_report)
            target.parent.mkdir(parents=True, exist_ok=True)
            xml = report_xml if (report_xml is not None and not is_unit) else (
                "<testsuites><testcase name='smoke'/></testsuites>"
            )
            target.write_text(xml)
        return {"returncode": "0", "stdout": "", "stderr": ""}

    return run


@pytest.fixture
def project(tmp_path):
    pack = pack_named("browser-javascript")
    assert scaffold(tmp_path, pack, "notes", "Notes", run=_fake_runner(tmp_path, pack)).ok
    suite.save_criteria(tmp_path, number(BRIEF))
    return tmp_path


def _write(root: Path, relative: str, text: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


SPEC = """import { test, expect } from '@playwright/test';
test('[AC-1] a note with a title is added', async ({ page }) => {});
test('[AC-2][AC-3] a deleted note stays deleted after a reload', async ({ page }) => {});
"""


def test_coverage_reads_the_ids_in_test_names(project) -> None:
    _write(project, "notes/acceptance/notes.spec.js", SPEC)
    assert set(suite.coverage(project)) == {"AC-1", "AC-2", "AC-3"}
    assert suite.gaps(project) == []
    _write(project, "notes/acceptance/notes.spec.js", SPEC.replace("[AC-2][AC-3]", "[AC-9]"))
    gaps = suite.gaps(project)
    assert any(g.startswith("AC-2") for g in gaps) and any("AC-9" in g for g in gaps)


def test_a_deferred_criterion_needs_no_test(project) -> None:
    _write(project, "notes/acceptance/notes.spec.js", SPEC.replace("[AC-2][AC-3]", "[AC-2]"))
    suite.defer(project, {"AC-3": "a person must judge it"})
    assert suite.gaps(project) == []
    assert "deferred: a person must judge it" in (project / "docs" / "acceptance_criteria.md").read_text()


def test_the_lock_puts_the_suite_back(project) -> None:
    _write(project, "notes/acceptance/notes.spec.js", SPEC)
    suite.lock(project)
    _write(project, "notes/acceptance/notes.spec.js", "// weakened\n")
    _write(project, "notes/acceptance/extra.spec.js", "// added\n")

    repairs = suite.restore(project)

    assert len(repairs) == 2
    assert (project / "notes/acceptance/notes.spec.js").read_text() == SPEC
    assert not (project / "notes/acceptance/extra.spec.js").exists()
    assert suite.restore(project) == []


def test_write_tools_refuse_the_locked_suite_and_the_harness_records(project, monkeypatch) -> None:
    _write(project, "notes/acceptance/notes.spec.js", SPEC)
    suite.lock(project)
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: "defect_fix_1_0")

    with pytest.raises(RepositoryToolError, match="acceptance suite"):
        write_approved_artifact(project, "notes/acceptance/notes.spec.js", "// pass\n")
    with pytest.raises(RepositoryToolError, match="acceptance suite"):
        delete_approved_artifact(project, "notes/acceptance/notes.spec.js")
    with pytest.raises(RepositoryToolError, match="harness's own record"):
        write_approved_artifact(project, ".harness/acceptance.json", "{}")
    # The product itself is still writable.
    write_approved_artifact(project, "notes/src/notes.js", "export const notes = [];\n")


def test_only_the_acceptance_author_writes_the_suite_and_nothing_else(project, monkeypatch) -> None:
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: "acceptance_author_0")
    write_approved_artifact(project, "notes/acceptance/notes.spec.js", SPEC)
    with pytest.raises(RepositoryToolError, match="QA writes only"):
        write_approved_artifact(project, "notes/src/notes.js", "export const notes = [];\n")


def test_a_run_is_judged_per_criterion(project) -> None:
    _write(project, "notes/acceptance/notes.spec.js", SPEC)
    report = (
        "<testsuites><testsuite>"
        "<testcase name='[AC-1] a note with a title is added'/>"
        "<testcase name='[AC-2][AC-3] a deleted note stays deleted after a reload'>"
        "<failure message='expected 0 notes, found 1'/></testcase>"
        "</testsuite></testsuites>"
    )
    pack = pack_named("browser-javascript")

    result = suite.run(project, runner=_fake_runner(project, pack, report))

    assert result.ran
    assert result.criteria["AC-1"].status == "passed"
    assert result.criteria["AC-2"].status == "failed"
    assert [c.id for c in result.failing()] == ["AC-2", "AC-3"]
    assert [c.id for c in result.failing(["AC-1", "AC-2"])] == ["AC-2"]
    assert "expected 0 notes" in result.summary()
    assert suite.last_result(project)["criteria"]["AC-1"]["status"] == "passed"


def test_a_criterion_with_no_test_in_the_report_is_untested(project) -> None:
    pack = pack_named("browser-javascript")
    result = suite.run(project, runner=_fake_runner(project, pack, "<testsuites/>"))
    assert {c.status for c in result.criteria.values()} == {"untested"}


def test_a_suite_with_no_report_did_not_run(project) -> None:
    def silent(argv, category, working_directory):
        return {"returncode": "1", "stdout": "SyntaxError: Unexpected token", "stderr": ""}

    result = suite.run(project, runner=silent)
    assert not result.ran and "SyntaxError" in result.output
    assert "did not run" in result.summary()


def test_change_requests_are_proven_like_criteria(project) -> None:
    change_id = suite.add_change_request(project, "Notes are sorted newest first")
    assert change_id == "CR-1"
    _write(project, "notes/acceptance/notes.spec.js", SPEC + "test('[CR-1] newest first', async () => {});\n")
    assert suite.gaps(project) == []
    pack = pack_named("browser-javascript")
    report = "<testsuites><testcase name='[CR-1] newest first'><failure message='no'/></testcase></testsuites>"
    result = suite.run(project, runner=_fake_runner(project, pack, report))
    assert result.change_requests["CR-1"].status == "failed"


def test_the_author_is_told_the_criteria_the_pack_and_the_rules(project) -> None:
    text = requests.build_author_request(project, suite.criteria(project))["messages"][0]["content"]
    assert "AC-1: Add a note with a title" in text
    assert "notes/acceptance/" in text and "page.goto('/')" in text
    assert "RUN and FAIL now" in text
    assert "Each test runs alone, against a product that holds no data" in text


def test_untestable_criteria_are_read_from_blockers() -> None:
    found = requests.not_automatable([
        "AC-4: uptime is measured in production, not by a test",
        "Could not install a browser",
        "AC-5 and AC-6: these need a person's judgement",
    ])
    assert found == {
        "AC-4": "uptime is measured in production, not by a test",
        "AC-5": "these need a person's judgement",
        "AC-6": "these need a person's judgement",
    }


def test_qa_and_the_qa_lead_read_the_customer_s_brief(project) -> None:
    from app.agents.acceptance_reviewer import build_acceptance_review_request

    brief = "## Interface\n- A text field labelled \"Note title\" and a button named \"Keep\"."
    author = requests.build_author_request(project, suite.criteria(project), brief=brief)["messages"][0]["content"]
    assert 'labelled "Note title"' in author and "use exactly those words" in author
    review = build_acceptance_review_request("- AC-1: x", "suite", "ran", [], "", brief=brief)["messages"][0]["content"]
    assert 'labelled "Note title"' in review
    # The rule for tests that act on data they never made is the reviewer's
    # standing instruction, in its system prompt, not in each request.
    from app.agents.acceptance_reviewer import _SYSTEM_PROMPT

    assert "A test that acts on something it never created" in " ".join(_SYSTEM_PROMPT.split())


def test_the_harness_kept_configuration_cannot_be_written(project, monkeypatch) -> None:
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: "defect_fix_1_0")
    with pytest.raises(RepositoryToolError, match="test configuration the harness set up and keeps"):
        write_approved_artifact(project, "notes/playwright.config.js", "export default {};\n")
    # The manifest is not refused: stages add dependencies to it.
    write_approved_artifact(project, "notes/package.json", (project / "notes" / "package.json").read_text())


def test_a_test_round_is_shown_only_the_criteria_that_are_due(project) -> None:
    from app.acceptance.junit import Report, TestResult

    report = Report(found=True, tests=[
        TestResult(name="[AC-1] adds", outcome="passed"),
        TestResult(name="[AC-3] persists", outcome="failed", message="later work"),
    ])
    result = suite._judged(project, suite.AcceptanceResult(ran=True, command="npm run test:acceptance", report=report), False)
    block = requests.acceptance_block(result, ["AC-1"])
    assert "AC-1 PASSED" in block and "AC-3" not in block.split("are not defects now.")[1]


def test_the_ledger_checks_leave_the_acceptance_suite_to_its_gate(project) -> None:
    """One run's first sprint was sent back three times, then escalated: the last
    test run in the ledger was the acceptance suite, red on later sprints' criteria."""
    _write(project, "notes/acceptance/notes.spec.js", SPEC)
    assert not suite.is_an_acceptance_run(project, {"command": ["npm", "run", "test:acceptance"]})
    suite.lock(project)
    assert suite.is_an_acceptance_run(project, {"command": ["npm", "run", "test:acceptance"]})
    assert suite.is_an_acceptance_run(project, {"command": ["npx", "playwright", "test", "acceptance/notes.spec.js"]})
    assert not suite.is_an_acceptance_run(project, {"command": ["npm", "test"]})
    assert not suite.is_an_acceptance_run(project, {"command": ["node", "--test", "tests/"]})


def test_a_planned_file_is_a_hint_once_behaviour_is_measured(project) -> None:
    from app.agents.specialists import what_the_files_already_prove

    planned = ["Create notes/src/storage.js to keep notes"]
    before = what_the_files_already_prove(str(project), planned=planned)
    _write(project, "notes/acceptance/notes.spec.js", SPEC)
    suite.lock(project)
    after = what_the_files_already_prove(str(project), planned=planned)
    assert any("storage.js" in p for p in before)
    assert not any("storage.js" in p for p in after)


def test_a_test_that_breaks_on_its_own_code_is_sent_back(project) -> None:
    """One run locked a suite whose helper was declared `addTask({ page }, ...)`
    and called `addTask(page, ...)`: nine of eleven tests threw a TypeError before
    touching the page, and no product could ever pass them."""
    from app.acceptance.junit import Report, TestResult

    report = Report(found=True, tests=[
        TestResult(name="[AC-1] adds", outcome="failed",
                   message="Cannot read properties of undefined (reading 'getByLabel')\nTypeError: Cannot read properties of undefined"),
        TestResult(name="[AC-2] deletes", outcome="failed",
                   message="locator.fill: Timeout 3000ms exceeded.\nCall log:\n  - waiting for getByLabel('Title', { exact: true })"),
        TestResult(name="[AC-3] persists", outcome="failed",
                   message="expect(locator).toHaveCount(expected) failed\nExpected: 1\nReceived: 0"),
        TestResult(name="[AC-4] reads state", outcome="failed",
                   message="page.evaluate: ReferenceError: store is not defined"),
        TestResult(name="[AC-5] helper", outcome="failed", message="TypeError: addTask is not a function"),
    ])
    result = suite.AcceptanceResult(ran=True, report=report)

    broken = suite.tests_that_broke_themselves(project, result)

    assert [b.split("`")[1] for b in broken] == ["[AC-1] adds", "[AC-5] helper"]


FRESH_PAGE = """- main:
  - heading "Notes" [level=1]
  - textbox "Title"
  - button "Add note"
"""

PAGE_WITH_NOTE = FRESH_PAGE + """  - list:
    - listitem:
      - checkbox "Done"
      - button "Edit"
      - button "Delete"
"""


def _acceptance_result_waiting_for(locator: str, failed_page: str, other_page: str) -> suite.AcceptanceResult:
    from app.acceptance.junit import Report, TestResult

    return suite.AcceptanceResult(
        ran=True,
        report=Report(found=True, tests=[
            TestResult(
                name="[AC-2] acts on a note",
                outcome="failed",
                message=f"Timeout\nCall log:\n - waiting for {locator}\n"
                        f"{suite._PAGE_MARK}{failed_page}",
            ),
            TestResult(
                name="[AC-1] adds a note",
                outcome="failed",
                message=f"Timeout\n{suite._PAGE_MARK}{other_page}",
            ),
        ]),
        shows=FRESH_PAGE,
    )


def test_a_locked_test_waiting_for_data_qa_never_created_goes_back_to_qa(project) -> None:
    result = _acceptance_result_waiting_for(
        "getByRole('checkbox', { name: 'Done', exact: true })",
        FRESH_PAGE,
        PAGE_WITH_NOTE,
    )

    findings = suite.tests_that_need_what_they_never_made(project, result)

    assert len(findings) == 1
    assert "`[AC-2] acts on a note`" in findings[0]
    assert "starts from an empty product" in findings[0]


def test_a_missing_product_feature_is_not_mistaken_for_bad_test_data(project) -> None:
    result = _acceptance_result_waiting_for(
        "getByRole('button', { name: 'Export', exact: true })",
        FRESH_PAGE,
        PAGE_WITH_NOTE,
    )

    assert suite.tests_that_need_what_they_never_made(project, result) == []


def test_a_locator_present_on_the_fresh_page_is_not_a_missing_data_finding(project) -> None:
    fresh_with_control = FRESH_PAGE + '  - checkbox "Done"\n'
    result = _acceptance_result_waiting_for(
        "getByRole('checkbox', { name: 'Done', exact: true })",
        fresh_with_control,
        PAGE_WITH_NOTE,
    )
    result.shows = fresh_with_control

    assert suite.tests_that_need_what_they_never_made(project, result) == []


def test_a_test_that_creates_its_own_data_is_not_reopened(project) -> None:
    result = _acceptance_result_waiting_for(
        "getByRole('checkbox', { name: 'Done', exact: true })",
        PAGE_WITH_NOTE,
        PAGE_WITH_NOTE,
    )

    assert suite.tests_that_need_what_they_never_made(project, result) == []


def test_only_browser_packs_use_the_page_data_detector() -> None:
    for name in ("browser-javascript", "browser-react", "fullstack-node"):
        assert pack_named(name).needs_what_it_never_made is not None
    assert pack_named("python-cli").needs_what_it_never_made is None


def test_python_packs_know_their_runner_s_test_bugs(tmp_path) -> None:
    import re

    from app.stacks import pack_named

    patterns = [re.compile(p, re.I | re.M) for p in pack_named("python-cli").test_bugs]
    def hit(message): return any(p.search(message) for p in patterns)
    assert hit("NameError: name 'run_cli' is not defined")
    assert hit("fixture 'cli' not found")
    assert not hit("ModuleNotFoundError: No module named 'wordstats'")
    assert not hit("AssertionError: assert 1 == 2")


def test_a_criterion_id_is_read_whatever_dash_a_model_types() -> None:
    """One run's review wrote every id with a non-breaking hyphen; the harness
    saw no criterion in it and sent a sprint back three times over later work."""
    from app.acceptance.junit import tags_in

    text = "AC‑2, AC‐3, AC—4, AC−5, AC－6, AC-7, AC_8, ac9, test_ac10_x, [CR‑1]"
    assert tags_in(text) == ("AC-2", "AC-3", "AC-4", "AC-5", "AC-6", "AC-7", "AC-8", "AC-9", "AC-10", "CR-1")
    assert tags_in("access pac3 AC") == ()


def test_the_suite_is_held_to_the_shape_the_interface_names(project) -> None:
    """One run's locked suite found tasks by their text alone. The brief said each
    is "an item of a list"; the product rendered them as plain blocks, its own
    suite passed 8 of 9, and the hidden tests - which find each record as a list
    item - passed 2 of 10."""
    from app.agents.acceptance_reviewer import _SYSTEM_PROMPT

    author = requests.build_author_request(project, suite.criteria(project), brief="## Interface\n- x")["messages"][0]["content"]
    for text in (" ".join(author.split()), " ".join(_SYSTEM_PROMPT.split())):
        assert "an item of a list, a row of a table, an element of a returned array" in text


@pytest.mark.parametrize("word", ["task", "to-do", "todo", "button", "click", "checkbox"])
def test_the_shape_rule_names_no_product_and_no_control(project, word: str) -> None:
    import re

    from app.agents.acceptance_reviewer import _SYSTEM_PROMPT

    start = _SYSTEM_PROMPT.index("Where the brief's interface says what kind of thing")
    rule = _SYSTEM_PROMPT[start:start + 400]
    assert not re.search(rf"\b{re.escape(word)}\b", rule, re.I)


def test_a_record_that_changes_state_inside_a_view_is_tested(project) -> None:
    """One run's locked suite checked each status view only as it was first
    chosen. The product left a record in view after its state changed, its suite
    passed 19 of 19, and the hidden test of exactly that failed (9 of 10)."""
    from app.agents.acceptance_reviewer import _SYSTEM_PROMPT

    author = requests.build_author_request(project, suite.criteria(project), brief="## Interface\n- x")["messages"][0]["content"]
    for text in (" ".join(author.split()), " ".join(_SYSTEM_PROMPT.split())):
        assert "while that view is shown" in text and "at once" in text


@pytest.mark.parametrize("word", ["task", "tasks", "to-do", "todo", "button", "click", "checkbox", "filter", "active", "completed"])
def test_the_state_change_rule_names_no_product_and_no_control(project, word: str) -> None:
    import re

    from app.agents.acceptance_reviewer import _SYSTEM_PROMPT

    author = requests.build_author_request(project, suite.criteria(project), brief="## Interface\n- x")["messages"][0]["content"]
    rules = [
        author[author.index("- Where a view shows only the records"):][:400],
        _SYSTEM_PROMPT[_SYSTEM_PROMPT.index("Where the brief has a view that shows only"):][:400],
    ]
    for rule in rules:
        assert not re.search(rf"\b{re.escape(word)}\b", rule, re.I), word


def test_a_review_finding_about_the_product_is_not_qa_s_to_fix(project) -> None:
    """One run's repair handed QA three product findings under "Fix each of these
    first", and QA spent five calls trying to edit the page."""
    request = requests.build_author_request(
        project, suite.criteria(project), feedback=["The save does nothing on an empty title"]
    )["messages"][0]["content"]
    text = " ".join(request.split())
    assert "Fix each of these that is about the tests first" in text
    assert "One about the product" in text and "is not yours to fix" in text


def test_a_repair_after_the_product_exists_does_not_say_nothing_is_built(project, monkeypatch) -> None:
    monkeypatch.setattr(suite, "last_result", lambda root: {"passed": 17, "failed": 5})
    text = requests.build_author_request(project, suite.criteria(project))["messages"][0]["content"]
    assert "Nothing of the product's features is built yet" not in text
    assert "partly built and the suite is being repaired" in text

    monkeypatch.setattr(suite, "last_result", lambda root: {})
    fresh = requests.build_author_request(project, suite.criteria(project))["messages"][0]["content"]
    assert "Nothing of the product's features is built yet" in fresh


@pytest.mark.parametrize("word", ["task", "tasks", "to-do", "todo", "button", "click", "checkbox", "page"])
def test_the_product_finding_rule_names_no_product_and_no_control(project, word: str) -> None:
    import re

    request = requests.build_author_request(project, suite.criteria(project), feedback=["x"])["messages"][0]["content"]
    rule = request[request.index("Fix each of these that is about"):][:300]
    assert not re.search(rf"\b{re.escape(word)}\b", rule, re.I), word

def test_author_request_requires_testing_persistence_of_all_changes():
    from types import SimpleNamespace
    criteria = [SimpleNamespace(id="AC-1", text="some criteria", automatability_reason="")]
    req = requests.build_author_request(
        "tmp_path", 
        criteria, 
        brief="## Interface\n- x"
    )
    content = req["messages"][0]["content"]
    assert "checks every kind of change it offers - not only creating a record, but each way one can be changed or removed - survives a reload or a restart" in " ".join(content.split())
    # A Playwright rule is the JavaScript packs' to give (their guide says to
    # match names exactly), never the request every stack's QA reads.
    assert "Playwright" not in content.split("--- What to build them against ---", 1)[1].split("--- Rules ---", 1)[0]
    rules = content.split("--- Rules ---", 1)[1].lower()
    import re
    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox", "completion"):
        assert not re.search(rf"\b{word}\b", rules.split("- write only inside", 1)[0]), word
