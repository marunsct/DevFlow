"""Once a passing locked test has been the only casualty of two reverted fixes in an attempt and the suite may not be repaired
for it, breaking it alone no longer reverts a fix that makes other tests pass.

Measured on one run: `DELETE /notes/{id}` answers 204 in the brief, and AC-7's test asserted a JSON content type on
every response, a successful delete included. Each fix that made the delete criterion pass broke that one test and
was reverted - eight times over four attempts - with the suite's repairs spent, so no dispute could set it right.
"""
from __future__ import annotations

from app import ci
from app.graph import engineering, workflow

CONTESTED = "acceptance: ct.spec.js › [AC-7] DELETE /notes/1 returns Content-Type application/json"


def _measured(monkeypatch, before, after):
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(ci, "load", lambda root, which: before)
    monkeypatch.setattr(ci, "take", lambda root, label: after)
    reverted = []
    monkeypatch.setattr(ci, "revert_to", lambda root, base: reverted.append(base) or True)
    return reverted


def test_a_fix_whose_only_casualty_is_the_contested_test_is_kept(monkeypatch, tmp_path):
    before = ci.Snapshot(label="latest", acceptance={CONTESTED[len("acceptance: "):]: "passed", "[AC-5] deletes": "failed"}, acceptance_ran=True)
    after = ci.Snapshot(label="after", acceptance={CONTESTED[len("acceptance: "):]: "failed", "[AC-5] deletes": "passed"}, acceptance_ran=True)
    reverted = _measured(monkeypatch, before, after)

    (tmp_path / ".harness").mkdir()
    broke = engineering.after_a_fix(str(tmp_path), "abc", "defect_fix_1_1", "[AC-5] delete", contested=CONTESTED)

    assert broke == [] and reverted == []


def test_without_the_contested_test_named_it_is_reverted_as_before(monkeypatch):
    before = ci.Snapshot(label="latest", acceptance={CONTESTED[len("acceptance: "):]: "passed", "[AC-5] deletes": "failed"}, acceptance_ran=True)
    after = ci.Snapshot(label="after", acceptance={CONTESTED[len("acceptance: "):]: "failed", "[AC-5] deletes": "passed"}, acceptance_ran=True)
    reverted = _measured(monkeypatch, before, after)

    assert engineering.after_a_fix("/w", "abc", "defect_fix_1_1", "[AC-5] delete") == [CONTESTED] and reverted


def test_the_contested_test_is_named_only_after_three_reverts_with_the_repairs_spent(monkeypatch):
    from types import SimpleNamespace

    note = f"A fix was tried and reverted, because it broke what passed before it: {CONTESTED}."
    cycle = SimpleNamespace(defects=[SimpleNamespace(actual_behavior=note) for _ in range(2)])
    spent = {"suite_repairs": 4, "suite_repaired_tests": []}
    monkeypatch.setattr("app.graph.acceptance_nodes.MAX_SUITE_REPAIRS_IN_ALL", 4)

    assert workflow._a_contested_test_past_repair(spent, cycle) == CONTESTED
    assert workflow._a_contested_test_past_repair({"suite_repairs": 0}, cycle) == "", "still repairable: disputed instead"
    one = SimpleNamespace(defects=cycle.defects[:1])
    assert workflow._a_contested_test_past_repair(spent, one) == "", "one revert is a bad fix"
