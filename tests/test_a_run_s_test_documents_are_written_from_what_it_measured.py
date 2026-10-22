"""A finished run's unit-test and acceptance-test documents are written from what the harness measured (plans DT.1, DT.6).

Every row is a test or a criterion the run recorded; a criterion no test
carries says so, a failure carries its message, and a workspace that recorded
nothing yields empty facts rather than invented ones. Read-only and on demand,
so a run's behaviour is untouched.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.acceptance import suite
from app.handover.facts import document_facts
from app.handover.test_documents import acceptance_test_document, unit_test_document
from app.stacks import contract

UNIT = """<?xml version="1.0"?><testsuites><testsuite name="pytest">
<testcase classname="tests.test_store" file="tests/test_store.py" name="test_saves" time="0.012"/>
<testcase classname="tests.test_store" file="tests/test_store.py" name="test_loads" time="0.020"><failure message="assert 1 == 2">x</failure></testcase>
</testsuite></testsuites>"""


def _workspace(tmp_path: Path, monkeypatch) -> Path:
    (tmp_path / contract.CONTRACT_FILE).parent.mkdir(parents=True)
    (tmp_path / contract.CONTRACT_FILE).write_text(json.dumps({
        "pack": "python-http-api", "project": "items-api", "title": "Items API", "unit_report": "test-results/unit.xml",
        "unit_test": ["pytest", "tests"], "acceptance_test": ["pytest", "acceptance"]}))
    (tmp_path / "items-api" / "test-results").mkdir(parents=True)
    (tmp_path / "items-api" / "test-results" / "unit.xml").write_text(UNIT)
    monkeypatch.setattr(suite, "last_result", lambda root: {
        "ran": True, "passed": 1, "failed": 1, "skipped": 0, "command": "pytest acceptance",
        "criteria": {
            "AC-1": {"id": "AC-1", "text": "Sign up", "status": "passed", "tests": [{"name": "test_ac1_signs_up", "outcome": "passed", "message": ""}]},
            "AC-2": {"id": "AC-2", "text": "Sign in", "status": "failed", "tests": [{"name": "test_ac2_signs_in", "outcome": "failed", "message": "assert 401 == 200"}]},
        }})
    monkeypatch.setattr(suite, "criteria", lambda root: [
        suite.Criterion("AC-1", "Sign up", "brief"), suite.Criterion("AC-2", "Sign in", "brief"), suite.Criterion("AC-3", "Sign out", "brief")])
    monkeypatch.setattr(suite, "deferred", lambda root: {})
    return tmp_path


def test_the_facts_and_both_documents_hold_only_what_was_measured(tmp_path, monkeypatch):
    facts = document_facts(_workspace(tmp_path, monkeypatch), run_id="run-x", completion_gaps=["AC-3 ships untested"])

    assert [c["id"] for c in facts["criteria"]] == ["AC-1", "AC-2", "AC-3"]
    assert [t["outcome"] for t in facts["unit_tests"]] == ["passed", "failed"]
    acceptance = acceptance_test_document(facts)
    assert "3 criteria: 1 passed, 1 failed" in acceptance
    assert "| AC-3: Sign out | untested | - | no test carries it |" in acceptance
    assert "AC-2 `test_ac2_signs_in`: assert 401 == 200" in acceptance and "AC-3 ships untested" in acceptance
    unit = unit_test_document(facts)
    assert "2 tests: 1 passed, 1 failed, 0 skipped." in unit and "assert 1 == 2" in unit
    assert unit.index("test_loads") < unit.index("test_saves"), "failures first"


def test_an_empty_workspace_yields_empty_facts_not_invented_ones(tmp_path):
    facts = document_facts(tmp_path)
    assert facts["criteria"] == [] and facts["unit_tests"] == [] and facts["pack"] == ""
    assert "recorded no unit test report" in unit_test_document(facts)
