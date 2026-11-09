"""Every fixer sees the output that defines its defect, not another stage's last command (harness review HR2.fix.6).

Acceptance-suite fixers were shown the run's last failing command 124 times to their own tests 64; test-round fixers
76 to 9; mutation fixers 78 to 2.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

from app.acceptance import mutation_guided, suite
from app.graph import workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_a_criterion_whose_suite_did_not_run_is_shown_the_suite_s_problem(tmp_path) -> None:
    (tmp_path / suite.RESULT_FILE).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / suite.RESULT_FILE).write_text(json.dumps({
        "criteria": {"AC-2": {"tests": []}},
        "problem": "The product did not start: Error: Cannot find module './store'"}))
    shown = suite.what_the_criteria_s_tests_printed(tmp_path, ["AC-2"])
    assert shown["title"] == "What the suite's last run printed"
    assert "Cannot find module './store'" in shown["output"]
    assert not BANNED.search(shown["title"])


def test_a_defect_the_unit_command_caught_is_shown_its_failures(tmp_path, monkeypatch) -> None:
    pack = SimpleNamespace(unit_test=("npm", "test"), unit_report="test-results/unit.xml")
    monkeypatch.setattr(suite.contract, "the_pack", lambda root: (pack, {}))
    monkeypatch.setattr(suite, "location", lambda root: ("notes",))
    report = tmp_path / "notes" / "test-results" / "unit.xml"
    report.parent.mkdir(parents=True)
    report.write_text('<testsuites><testsuite><testcase name="saves a note"><failure message="expected 1, got 0">'
                      "</failure></testcase></testsuite></testsuites>")
    shown = suite.what_the_unit_tests_printed(tmp_path, "Saving a note does not store it", caught_by="npm test")
    assert shown is not None and "saves a note" in shown["output"]
    assert suite.what_the_unit_tests_printed(tmp_path, "Saving a note does not store it", caught_by="") is None


def test_a_mutation_finding_is_never_shown_the_last_command(monkeypatch) -> None:
    monkeypatch.setattr("app.observability.transcript.last_failing_command",
                        lambda run_id: {"command": "npm test", "output": "another defect's failure"})
    finding = SimpleNamespace(source=mutation_guided.SOURCE, description="a changed comparison went unnoticed")
    assert workflow._what_the_last_failure_printed("run-x", finding) is None
    other = SimpleNamespace(source="acceptance", description="x")
    assert workflow._what_the_last_failure_printed("run-x", other)["command"] == "npm test"
