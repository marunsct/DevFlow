"""A fix's gain is weighed against the tests it broke, not against the unit tests it renamed on purpose.

Found in a code review: `after_a_fix` forgives unit tests a fix replaced on purpose (`_broken_tests`: every unit test
passes after it and no fewer pass than before), then weighed what the fix gained against every test that no longer
passed, renamed ones included. A fix that broke one criterion and renamed four unit tests was weighed as five broken
and had to make 15 tests pass to stay, instead of 4. The renamed tests' new names are not counted as gained either.
"""
from __future__ import annotations

import pytest

from app import ci
from app.graph import engineering


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("KEEP_NET_GAINS", "on")


def _measure(monkeypatch, before, after, reverted):
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(engineering, "what_the_fix_did_to_the_install", lambda root, base: "")
    monkeypatch.setattr(engineering, "_its_tests_without_its_product_change", lambda *args: None)
    monkeypatch.setattr(ci, "load", lambda root, which: before)
    monkeypatch.setattr(ci, "take", lambda root, label: after)
    monkeypatch.setattr(ci, "revert_to", lambda root, base: reverted.append(base) or True)
    monkeypatch.setattr(ci, "save", lambda root, snapshot, **kw: None)
    monkeypatch.setattr(ci, "commit", lambda root, message: "c0ffee")


def _a_fix_that_renamed_four_unit_tests(gains: int):
    """Before: four unit tests and one criterion pass. After: the four renamed (all passing), the criterion broken."""
    before = ci.Snapshot(
        label="b", unit_ran=True, acceptance_ran=True,
        unit={f"old name {n}": "passed" for n in range(4)},
        acceptance={"[AC-1] lists": "passed", **{f"[AC-{n + 2}] gained": "failed" for n in range(gains)}},
    )
    after = ci.Snapshot(
        label="a", unit_ran=True, acceptance_ran=True,
        unit={f"new name {n}": "passed" for n in range(4)},
        acceptance={"[AC-1] lists": "failed", **{f"[AC-{n + 2}] gained": "passed" for n in range(gains)}},
    )
    return before, after


def test_four_gained_for_one_criterion_broken_stays_though_four_unit_tests_were_renamed(monkeypatch):
    reverted: list[str] = []
    _measure(monkeypatch, *_a_fix_that_renamed_four_unit_tests(4), reverted)

    broke = engineering.after_a_fix("/workspace", "abc1234", "defect_fix_2_1", "the list")

    assert broke == [] and reverted == []


def test_three_gained_for_one_criterion_broken_is_still_reverted(monkeypatch):
    reverted: list[str] = []
    _measure(monkeypatch, *_a_fix_that_renamed_four_unit_tests(3), reverted)

    broke = engineering.after_a_fix("/workspace", "abc1234", "defect_fix_2_1", "the list")

    assert broke == ["acceptance: [AC-1] lists"] and reverted == ["abc1234"]


def test_the_renamed_tests_new_names_do_not_buy_back_a_broken_criterion(monkeypatch):
    reverted: list[str] = []
    _measure(monkeypatch, *_a_fix_that_renamed_four_unit_tests(0), reverted)

    broke = engineering.after_a_fix("/workspace", "abc1234", "defect_fix_2_1", "the list")

    assert broke == ["acceptance: [AC-1] lists"] and reverted == ["abc1234"]


def test_a_fix_that_broke_only_what_is_not_a_test_is_not_kept_for_its_gain(monkeypatch):
    """The language service's certainty is not a test name: weighed as nothing broken, it must not keep the fix."""
    reverted: list[str] = []
    before = ci.Snapshot(label="b", unit_ran=True, unit={"a": "passed"})
    after = ci.Snapshot(label="a", unit_ran=True, unit={"a": "passed"})
    _measure(monkeypatch, before, after, reverted)
    monkeypatch.setattr(engineering, "what_the_fix_made_certain_to_fail", lambda root, base: ["`x.py` line 3: oops"])

    broke = engineering.after_a_fix("/workspace", "abc1234", "defect_fix_2_1", "x")

    assert broke and broke[0].startswith("it wrote code") and reverted == ["abc1234"]
