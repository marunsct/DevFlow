"""A criterion deferred during the run whose own locked tests pass at release is a note, not unproven (2026-11-09).

29 runs shipped "AC-n ships deferred, unproven by the suite" on a green locked suite, and 28 of them passed every
hidden test: the deferral was recorded mid-run, when the tests' shared setup failed, and never looked at again.
"""
from __future__ import annotations

import inspect
import json

from app import completion_verdict
from app.acceptance import interface_contract, suite
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
    assert completion_verdict.is_blocking("AC-9 ships deferred, unproven by the suite: no test")


def test_the_release_asks_each_deferred_criterion_s_own_tests() -> None:
    source = inspect.getsource(delivery.release)
    assert "if _its_criterion_passed(root, cid):" in source
