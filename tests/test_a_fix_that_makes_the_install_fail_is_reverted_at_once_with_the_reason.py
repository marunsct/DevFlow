"""A fix that edits a manifest into one nothing can install is reverted at once, with the installer's words.

Measured on a small-model run: a fix pinned `python-jose==4.3.0`, which does not exist. The five fixers after it each ended
"its own tests still fail" on a project nothing could install, and the defect carrying the registry's answer ("the current
release is 3.5.0") was raised only when the round ended.
"""
from __future__ import annotations

from types import SimpleNamespace

from app import ci
from app.acceptance import suite
from app.graph import engineering
from app.stacks.contract import INSTALL_FAILED

NOTE = (f"`pip install -r requirements.txt` {INSTALL_FAILED}. The registry's current release of `python-jose` is 3.5.0: "
        "pin that, or a version the registry lists, not a version it does not have.; it ended: No matching distribution")


def _measure(monkeypatch, *, repairs, changed):
    snapshot = ci.Snapshot(label="s", unit={"u1": "passed"}, unit_ran=True)
    reverted = []
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(ci, "load", lambda root, which: snapshot)
    monkeypatch.setattr(ci, "take", lambda root, label: snapshot)
    monkeypatch.setattr(ci, "revert_to", lambda root, base: reverted.append(base) or True)
    monkeypatch.setattr(ci, "save", lambda root, snap, **kw: None)
    monkeypatch.setattr(ci, "commit", lambda root, message: "c0ffee")
    monkeypatch.setattr(ci, "_git", lambda root, *args: SimpleNamespace(returncode=0, stdout="\n".join(changed)))
    monkeypatch.setattr(suite, "last_result", lambda root: {"repairs": repairs})
    return reverted


def test_a_manifest_edit_that_stops_the_install_is_reverted_with_the_hint(monkeypatch):
    reverted = _measure(monkeypatch, repairs=[NOTE], changed=["tasks-api/requirements.txt", "tasks-api/tasks_api/auth.py"])

    broke = engineering.after_a_fix("/workspace", "abc1234", "defect_fix_1_0", "sign-up")

    assert reverted == ["abc1234"]
    assert len(broke) == 1 and broke[0].startswith("it broke the install:") and "current release of `python-jose` is 3.5.0" in broke[0]


def test_an_install_that_was_already_failing_is_not_the_fix_s(monkeypatch):
    reverted = _measure(monkeypatch, repairs=[NOTE], changed=["tasks-api/tasks_api/auth.py"])

    assert engineering.after_a_fix("/workspace", "abc1234", "defect_fix_1_0", "sign-up") == []
    assert reverted == []


def test_a_manifest_edit_that_installs_is_kept(monkeypatch):
    reverted = _measure(monkeypatch, repairs=[], changed=["tasks-api/requirements.txt"])

    assert engineering.after_a_fix("/workspace", "abc1234", "defect_fix_1_0", "sign-up") == []
    assert reverted == []


def test_a_fix_that_gains_a_great_deal_is_still_reverted_when_it_breaks_the_install(monkeypatch):
    reverted = _measure(monkeypatch, repairs=[NOTE], changed=["tasks-api/package.json"])
    before = ci.Snapshot(label="b", acceptance={f"g{n}": "failed" for n in range(9)}, acceptance_ran=True)
    after = ci.Snapshot(label="a", acceptance={f"g{n}": "passed" for n in range(9)}, acceptance_ran=True)
    monkeypatch.setattr(ci, "load", lambda root, which: before)
    monkeypatch.setattr(ci, "take", lambda root, label: after)

    assert engineering.after_a_fix("/workspace", "abc1234", "defect_fix_2_1", "x")
    assert reverted == ["abc1234"]
