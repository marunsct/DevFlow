"""A repair of a locked suite may not leave it running or passing less than it did; the locked suite comes back.

Measured on two runs: a repair sent for a few tests went from one open problem to three, and another dropped twenty
browser tests from the run; one ended with a criterion deferred and its hidden test failed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.acceptance import junit, suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _locked(root: Path) -> Path:
    folder = root / "app" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(json.dumps({"command": ["run"], "report": "r.xml"}))
    (folder / "ui.spec.js").write_text("test('[AC-1] a', () => {});\ntest('[AC-2] b', () => {});\n")
    (root / ".project-directory").write_text("app\n")
    suite.lock(root)
    (root / suite.RESULT_FILE).parent.mkdir(parents=True, exist_ok=True)
    (root / suite.RESULT_FILE).write_text(json.dumps({"ran": True, "passed": 20, "failed": 2}))
    suite.unlock(root)
    suite.repairing(root, ["[AC-2] b"])
    return folder


def _ran(passed: int, failed: int) -> suite.AcceptanceResult:
    tests = [junit.TestResult(name=f"p{n}", outcome="passed") for n in range(passed)]
    tests += [junit.TestResult(name=f"f{n}", outcome="failed") for n in range(failed)]
    return suite.AcceptanceResult(ran=True, report=junit.Report(tests=tests, found=True))


def test_a_repair_that_drops_tests_is_named_and_the_locked_suite_comes_back(tmp_path):
    folder = _locked(tmp_path)
    (folder / "ui.spec.js").write_text("test('[AC-1] a', () => {});\n")  # the repair dropped a test
    (folder / "extra.spec.js").write_text("test('x', () => {});\n")

    said = suite.a_repair_that_made_it_worse(tmp_path, _ran(12, 1))
    assert "runs 13 test(s)" in said and "ran 22" in said and not BANNED.search(said)

    suite.put_back_the_suite_before_the_repair(tmp_path)
    assert "[AC-2] b" in (folder / "ui.spec.js").read_text()
    assert not (folder / "extra.spec.js").exists()


def test_a_repair_that_loses_nothing_is_left_alone(tmp_path):
    _locked(tmp_path)
    assert suite.a_repair_that_made_it_worse(tmp_path, _ran(21, 1)) == ""
    assert suite.a_repair_that_made_it_worse(tmp_path, _ran(20, 2)) == ""


def test_passing_fewer_is_worse_too(tmp_path):
    _locked(tmp_path)
    assert suite.a_repair_that_made_it_worse(tmp_path, _ran(18, 4))


def test_a_suite_not_under_repair_is_never_measured_so(tmp_path):
    _locked(tmp_path)
    suite.lock(tmp_path)
    assert suite.a_repair_that_made_it_worse(tmp_path, _ran(1, 0)) == ""
