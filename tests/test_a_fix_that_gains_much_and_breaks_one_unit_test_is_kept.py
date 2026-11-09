"""A fix that makes many tests pass and breaks one of the workers' unit tests is kept, not reverted whole.

Measured on a small-model run: a fix made 12 tests pass and broke 1 unit test (a sign-up test the same model had
written) and was reverted; four more fixes that each repaired a criterion and broke that test were reverted too, and
the sprint went round again with nothing gained.
"""
from __future__ import annotations

import pytest

from app import ci
from app.graph import engineering, net_gain


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("KEEP_NET_GAINS", "on")


def _measure(monkeypatch, before, after, reverted):
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(ci, "load", lambda root, which: before)
    monkeypatch.setattr(ci, "take", lambda root, label: after)
    monkeypatch.setattr(ci, "revert_to", lambda root, base: reverted.append(base) or True)
    monkeypatch.setattr(ci, "save", lambda root, snapshot, **kw: None)
    monkeypatch.setattr(ci, "commit", lambda root, message: "c0ffee")


def _snapshots(gains, unit_lost=1, acceptance_lost=0, problem=""):
    before_unit = {f"u{n}": "passed" for n in range(unit_lost)}
    before_acc = {f"a{n}": "passed" for n in range(acceptance_lost)}
    before_acc.update({f"g{n}": "failed" for n in range(gains)})
    after_unit = {f"u{n}": "failed" for n in range(unit_lost)}
    after_acc = {f"a{n}": "failed" for n in range(acceptance_lost)}
    after_acc.update({f"g{n}": "passed" for n in range(gains)})
    return (ci.Snapshot(label="b", unit=before_unit, unit_ran=True, acceptance=before_acc, acceptance_ran=True),
            ci.Snapshot(label="a", unit=after_unit, unit_ran=True, acceptance=after_acc, acceptance_ran=True,
                        problem=problem))


def test_twelve_gained_and_one_unit_test_broken_stays(monkeypatch):
    reverted = []
    _measure(monkeypatch, *_snapshots(12), reverted)

    broke = engineering.after_a_fix("/workspace", "abc1234", "defect_fix_2_1", "sign-up")

    assert broke == [] and reverted == []


def test_one_gained_for_one_broken_is_reverted_as_before(monkeypatch):
    reverted = []
    _measure(monkeypatch, *_snapshots(1), reverted)

    assert engineering.after_a_fix("/workspace", "abc1234", "defect_fix_1_0", "sign-up") == ["unit: u0"]
    assert reverted == ["abc1234"]


def test_a_fix_that_breaks_an_acceptance_test_needs_a_bigger_gain_to_stay(monkeypatch):
    """Measured: a fix that made 5 tests pass and broke 1 criterion was reverted, a net gain of four thrown away."""
    reverted = []
    _measure(monkeypatch, *_snapshots(12, unit_lost=0, acceptance_lost=1), reverted)
    assert engineering.after_a_fix("/workspace", "abc1234", "defect_fix_1_0", "x") == [] and reverted == []

    _measure(monkeypatch, *_snapshots(3, unit_lost=0, acceptance_lost=1), reverted)
    assert engineering.after_a_fix("/workspace", "abc1234", "defect_fix_1_0", "x") == ["acceptance: a0"]
    assert reverted == ["abc1234"]


def test_five_gained_for_one_criterion_stays_and_five_for_two_does_not(monkeypatch):
    reverted = []
    _measure(monkeypatch, *_snapshots(5, unit_lost=0, acceptance_lost=1), reverted)
    assert engineering.after_a_fix("/workspace", "abc1234", "defect_fix_2_4", "x") == [] and reverted == []

    _measure(monkeypatch, *_snapshots(5, unit_lost=0, acceptance_lost=2), reverted)
    assert engineering.after_a_fix("/workspace", "abc1234", "defect_fix_2_4", "x")
    assert reverted == ["abc1234"]


def test_a_fix_that_stops_the_product_starting_is_reverted_whatever_it_gained(monkeypatch):
    reverted = []
    _measure(monkeypatch, *_snapshots(12, problem="build failed"), reverted)

    assert engineering.after_a_fix("/workspace", "abc1234", "defect_fix_1_0", "x")
    assert reverted == ["abc1234"]


def test_it_is_a_switch_and_off_the_fix_is_reverted_as_before(monkeypatch):
    monkeypatch.setenv("KEEP_NET_GAINS", "off")
    reverted = []
    _measure(monkeypatch, *_snapshots(12), reverted)

    assert engineering.after_a_fix("/workspace", "abc1234", "defect_fix_2_1", "sign-up") == ["unit: u0"]
    assert reverted == ["abc1234"]


def test_the_ratio_scales_with_what_was_broken():
    assert net_gain.keeps(["unit: a"], ["x"] * 3, product_runs=True)
    assert not net_gain.keeps(["acceptance: a"], ["x"] * 3, product_runs=True)
    assert net_gain.keeps(["acceptance: a"], ["x"] * 4, product_runs=True)
    assert not net_gain.keeps(["unit: a", "unit: b"], ["unit: x"] * 5, product_runs=True)
    assert net_gain.keeps(["unit: a", "unit: b"], ["unit: x"] * 6, product_runs=True)
    assert not net_gain.keeps(["unit: a"], ["x"] * 2, product_runs=True)


def test_a_fix_that_gains_locked_tests_and_breaks_only_unit_tests_stays_whatever_the_ratio(monkeypatch):
    monkeypatch.setenv("KEEP_NET_GAINS", "on")
    lost = [f"unit: test/notes.test.ts › case {n}" for n in range(8)]
    gained = [f"acceptance › [AC-{n}] works" for n in range(5)] + [f"unit: test/other.test.ts › {n}" for n in range(10)]
    assert net_gain.keeps(lost, gained, product_runs=True) is True
    # Unit tests alone still answer to the ratio, and a lost criterion still needs the larger gain.
    assert net_gain.keeps(lost, [f"unit: x › {n}" for n in range(15)], product_runs=True) is False
    assert net_gain.keeps(["acceptance › [AC-1] a"], ["acceptance › [AC-2] b", "acceptance › [AC-3] c", "acceptance › [AC-4] d"], product_runs=True) is False
