"""A fix is judged by where its tests fail, not only by how many pass (LF.1272, deep review 2.4).

Measured on a medium run: fixes that moved their criterion's tests from 500 to 404 - the route now served, a later
step reached - were recorded as "left open: its tests still fail" and counted as failed fixes, exactly like fixes that
changed nothing; only the pass count was read.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from app import ci
from app.acceptance.unstable import fingerprint
from app.graph import judged_fixes

import the_fix_stage
from the_fix_stage import a_defect, a_state

PRODUCT = "app/count.js"
STAGE = "defect_fix_2_0"


def _answered(status: int, line: int = 12) -> str:
    return (f"Error: expect(received).toBe(expected)\nExpected: 201\nReceived: {status}\n"
            f"    at Object.<anonymous> (/w/tests/count.spec.js:{line}:5)")


def _threw(error: str, line: int = 12) -> str:
    return f"{error}\n    at Object.<anonymous> (/w/tests/count.spec.js:{line}:5)"


ASSERTED = "Error: expect(received).toEqual(expected)\n- 2\n+ 1\n    at Object.<anonymous> (/w/tests/count.spec.js:12:5)"


def _test(name: str, outcome: str, message: str = "") -> dict:
    return {"name": name, "outcome": outcome, "message": message}


@pytest.mark.parametrize("was, now", [
    (_answered(500), _answered(404)),
    (_answered(500), _answered(422)),
    (_threw("TypeError: Cannot read properties of undefined (reading 'id')"), ASSERTED),
    (_answered(404, line=12), _answered(500, line=30)),
], ids=["a server error, then a missing route", "a server error, then a refusal", "a thrown error, then an assertion",
        "a later line of the test reached"])
def test_a_failure_further_on_is_progress(was, now):
    said = judged_fixes.progress([_test("[AC-1] counts", "failed", was)], [_test("[AC-1] counts", "failed", now)])

    assert said and "`[AC-1] counts` now fails at" in said


def test_a_test_that_passes_now_is_progress():
    said = judged_fixes.progress([_test("[AC-1] counts", "failed", _answered(500)), _test("[AC-1] lists", "failed", _answered(500))],
                                [_test("[AC-1] counts", "passed"), _test("[AC-1] lists", "failed", _answered(500))])

    assert said == "`[AC-1] counts` passes now"


@pytest.mark.parametrize("before, after", [
    ([_test("a", "failed", _answered(404))], [_test("a", "failed", _answered(500))]),
    ([_test("a", "failed", _answered(500, line=30))], [_test("a", "failed", _answered(500, line=12))]),
    ([_test("a", "failed", _answered(500)), _test("b", "passed")],
     [_test("a", "failed", _answered(404)), _test("b", "failed", _answered(500))]),
    ([_test("a", "failed", _answered(500)), _test("b", "failed", _answered(500))],
     [_test("a", "failed", _answered(404)), _test("b", "failed", _answered(404, line=4))]),
    ([_test("a", "failed", _answered(500))], [_test("a", "failed", _answered(500))]),
], ids=["a missing route, then a server error", "an earlier line", "a passing test now failing",
        "one forward, one back", "the same failure"])
def test_a_failure_no_further_on_or_one_further_back_is_no_progress(before, after):
    assert judged_fixes.progress(before, after) == ""


def test_failures_nothing_can_be_read_from_leave_the_count_to_judge():
    assert judged_fixes.progress([_test("a", "failed", "")], [_test("a", "failed", "")]) is None


# --- the fix stage, settled on the suite's results before and after it -----------------------------------------------


def _git(root, *args):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=root, check=True,
                   capture_output=True)


def _result(root, message: str) -> None:
    """The suite's saved result of the product as it is now: AC-1's test failing with `message`."""
    path = root / ".harness" / "acceptance-result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"criteria": {"AC-1": {"tests": [_test("[AC-1] counts", "failed", message)]}},
                               "fingerprint": fingerprint(root)}))


def _settled(tmp_path, before: str, after: str):
    (tmp_path / PRODUCT).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / PRODUCT).write_text("const count = 1;\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "before the fix")
    _result(tmp_path, before)

    def the_fixer_writes(stage):
        (tmp_path / PRODUCT).write_text("const count = 2;\n")

    def measured(*args, **kwargs):
        # The fix's measurement: its criterion's test still failing, with `after`.
        _result(tmp_path, after)
        ci.save(tmp_path, ci.Snapshot(label=f"after {STAGE}", acceptance={"count.spec.js › [AC-1] counts": "failed"},
                                      acceptance_ran=True))
        return []

    update, _ = the_fix_stage.run(
        tmp_path, a_state(tmp_path, a_defect("[AC-1] The count is wrong", affected_files=[PRODUCT])),
        during=the_fixer_writes, measure=measured)
    return update["remediation"].defects[0]


def test_a_fix_that_moved_its_tests_from_500_to_404_is_recorded_as_progress(tmp_path):
    defect = _settled(tmp_path, _answered(500), _answered(404))

    outcome = defect.attempts[-1]["outcome"]
    assert outcome.startswith("moved forward") and "answered 404" in outcome
    assert defect.status == "open", "its tests still fail: it stays open"
    assert defect.fix_attempts == 0, "not counted as a failed fix"
    assert "answered 404" in defect.actual_behavior, "the next fixer is told where its tests fail now"


def test_a_fix_whose_failures_cannot_be_read_is_settled_as_before(tmp_path):
    defect = _settled(tmp_path, "", "")

    assert defect.attempts[-1]["outcome"] == "left open: its tests still fail"
    assert defect.fix_attempts == 1
