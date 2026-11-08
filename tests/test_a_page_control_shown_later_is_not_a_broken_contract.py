"""A page control a bare visit cannot find is not a broken contract when its criterion's own tests passed (2026-11-08).

13 runs carried "does not keep its interface contract ... at a bare visit" (50 lines), and 12 of them scored 1.0 on
their hidden tests: an "Edit" control appears once the page holds a task, and the tests that add one passed.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from app import completion_verdict
from app.acceptance import interface_contract as ic
from app.acceptance import suite


def _gaps(tmp_path, monkeypatch, outcome: str):
    from app.stacks import contract

    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(files={"playwright.config.js": ""}, probe_runner="playwright"), {"project": "app"}))
    (tmp_path / "app").mkdir()
    ic.record_at_lock(tmp_path, ['AC-3 page /index.html button "Edit"'])
    (tmp_path / suite.RESULT_FILE).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / suite.RESULT_FILE).write_text(json.dumps({"criteria": {"AC-3": {"tests": [{"name": "[AC-3] edits a title", "outcome": outcome}]}}}))

    def runner(argv, category, where):
        (tmp_path / where / "test-results").mkdir(exist_ok=True)
        (tmp_path / where / ic.REPORT_FILE).write_text(
            '<testsuites><testsuite name="c" tests="1">'
            '<testcase name="[AC-3] contract 1: AC-3 page /index.html button &quot;Edit&quot;"><failure message="x">not visible</failure></testcase>'
            "</testsuite></testsuites>")
        return {"returncode": "1"}

    return ic.what_the_contract_checks_find(tmp_path, runner=runner)


def test_a_control_whose_criterion_passed_is_named_unchecked_not_broken(tmp_path, monkeypatch) -> None:
    gaps = _gaps(tmp_path, monkeypatch, "passed")
    assert not [g for g in gaps if "does not keep its interface contract" in g]
    unchecked = [g for g in gaps if "were not checked at release" in g]
    assert unchecked and "appears once the page has records or a person signed in" in unchecked[0]
    assert not completion_verdict.is_blocking(unchecked[0])


def test_a_control_whose_criterion_failed_is_still_a_broken_contract(tmp_path, monkeypatch) -> None:
    gaps = _gaps(tmp_path, monkeypatch, "failed")
    assert [g for g in gaps if "does not keep its interface contract" in g]
