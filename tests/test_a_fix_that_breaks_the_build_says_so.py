"""A fix reverted because nothing could run says why: the build or the start failed (measured live).

One rewrite of the served page broke its build; the acceptance suite reached no
test, every test that had passed counted as broken, and the fix was reverted as
"broke 3 test(s)" - twice, the same rewrite each round, because the next fixer
never saw the build error.
"""
from __future__ import annotations

from app import ci
from app.graph import engineering


def _snap(label, acceptance, ran=True, problem=""):
    return ci.Snapshot(label=label, acceptance=acceptance, acceptance_ran=ran, unit_ran=True, problem=problem)


def test_the_cause_comes_first_in_what_the_fix_broke(tmp_path, monkeypatch):
    before = _snap("before", {"[AC-8] health answers": "passed"})
    after = _snap("after", {}, problem="The product did not start for the acceptance suite: error TS2304: Cannot find name 'Tasks'")
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(ci, "load", lambda root, which="latest": before)
    monkeypatch.setattr(ci, "take", lambda root, label, **k: after)
    monkeypatch.setattr(ci, "revert_to", lambda root, base: True)

    broke = engineering.after_a_fix(str(tmp_path), "abc123", "defect_fix_1_0", "rewire the page")

    assert broke[0].startswith("the product no longer builds or starts after it")
    assert "Cannot find name 'Tasks'" in broke[0]
    assert "acceptance: [AC-8] health answers" in broke


def test_a_snapshot_from_before_the_field_still_loads():
    assert ci.Snapshot(label="old").problem == ""
