"""A criterion deferred during the run whose own locked tests pass at release is a note, not unproven (2026-11-09).

29 runs shipped "AC-n ships deferred, unproven by the suite" on a green locked suite, and 28 of them passed every
hidden test: the deferral was recorded mid-run, when the tests' shared setup failed, and never looked at again.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from app import completion_verdict
from app.acceptance import interface_contract, junit, suite
from app.acceptance.criteria import number
from app.graph import delivery


def test_a_deferred_criterion_whose_tests_pass_is_a_note(tmp_path) -> None:
    (tmp_path / suite.RESULT_FILE).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / suite.RESULT_FILE).write_text(json.dumps({"criteria": {
        "AC-7": {"tests": [{"name": "[AC-7] updates a note", "outcome": "passed"}]},
        "AC-9": {"tests": []}}}))
    assert interface_contract._its_criterion_passed(tmp_path, "AC-7")
    assert not interface_contract._its_criterion_passed(tmp_path, "AC-9"), "no test of its own: still unproven"

    note = "AC-7 was deferred during the run; its own locked tests pass at release: 26 tests failed in their setup"
    assert not completion_verdict.is_blocking(note)
    # Still unproven, and said so - as a scope cut (LR.21), not as a sign the product fails.
    assert completion_verdict.is_a_cut("AC-9 ships deferred, unproven by the suite: no test")


def test_the_release_names_a_deferred_criterion_whose_tests_pass_as_a_note(tmp_path, monkeypatch) -> None:
    (tmp_path / ".project-directory").write_text("notes\n")
    suite.save_criteria(tmp_path, number("# Brief\n## Features\n- Add a note\n- Delete a note\n"))
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True)
    spec.write_text("test('[AC-1] adds', ()=>{});\ntest('[AC-2] deletes', ()=>{});\n")
    suite.lock(tmp_path)
    suite.defer(tmp_path, {"AC-2": "the shared setup failed"})
    report = junit.Report(found=True, tests=[junit.TestResult(name="[AC-1] adds"), junit.TestResult(name="[AC-2] deletes")])
    monkeypatch.setattr(suite, "run", lambda root: suite._judged(
        root, suite.AcceptanceResult(ran=True, command="npm run test:acceptance", report=report), True))
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)

    update = delivery.release({"repository": SimpleNamespace(root_path=str(tmp_path)),
                               "product_intake": SimpleNamespace(product_name="Notes")},
                              {"configurable": {"thread_id": "t"}}, None)

    gaps = [str(gap) for gap in update.get("completion_gaps") or []]
    assert any(gap.startswith("AC-2 was deferred during the run; its own locked tests pass") for gap in gaps)
    assert not any(gap.startswith("AC-2 ships deferred, unproven") for gap in gaps)
