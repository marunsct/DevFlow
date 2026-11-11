"""Defects that name different things in backticks keep different ids across rounds.

Measured on one run: the stable defect id took out everything in backticks, so six mutation findings of one file
shared one id; the per-defect call cap summed their calls, and one finding was left open at "64 calls" that five
others had spent, before it had a single fix stage. Every "Regression: `<test>`" defect shared one id the same way.
"""
from __future__ import annotations

from app.acceptance import mutation_guided
from app.observability.defect_ledger import defect_id
from app.sprint import Defect


def _finding(line, text="    return jsonify(found), True", original="True", replacement="False"):
    return mutation_guided.defect({"file": "api/app.py", "line": line, "column": 39, "original": original,
                                   "replacement": replacement, "text": text})


def _plain(description, source="test_round"):
    return Defect(description=description, severity="major", reproduction_steps="", expected_behavior="",
                  actual_behavior="", affected_files=[], owner="backend", source=source)


def test_findings_on_different_lines_of_one_file_are_apart():
    ids = {defect_id(_finding(n, text=f"    x{n} = flag(True)")) for n in (71, 141, 180)}
    assert len(ids) == 3
    # The same statement repeated on several lines: apart by its place.
    assert defect_id(_finding(71)) != defect_id(_finding(141))
    assert defect_id(_finding(71, original="==", replacement="!=")) != defect_id(_finding(71))


def test_regressions_of_different_tests_are_apart():
    one = _plain("Regression: `unit: pytest › tests.test_auth › test_signin` passed before this round and fails now.")
    two = _plain("Regression: `unit: pytest › tests.test_items › test_toggle` passed before this round and fails now.")
    assert defect_id(one) != defect_id(two)


def test_the_same_defect_with_different_values_is_one():
    one = _plain('[AC-3] lists entries - expected 2 got 3, "Alpha" shown')
    two = _plain('[AC-3] lists entries - expected 5 got 7, "Beta" shown')
    assert defect_id(one) == defect_id(two)
