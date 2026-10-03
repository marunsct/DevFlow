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
