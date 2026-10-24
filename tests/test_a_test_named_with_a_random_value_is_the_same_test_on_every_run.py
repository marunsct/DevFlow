"""A test whose name carries a per-run value is the same test on every run.

Measured on a small-model run: an acceptance test was parametrized on a random user name
(`test_ac1_signup[user_02dc5292-password123]`), so every measurement named it differently. Each fix "broke" the test that
passed before it, and seven fixes - one of which had made three tests pass - were reverted for it.
"""
from __future__ import annotations

from types import SimpleNamespace

from app import ci


def _test(name, outcome="passed", file="acceptance/test_signup.py"):
    return SimpleNamespace(name=name, outcome=outcome, file=file, within="", suite="")


def test_the_random_part_of_a_name_does_not_make_a_new_test():
    before = ci.outcomes_of([_test("test_ac1_signup[user_02dc5292-password123]")])
    after = ci.outcomes_of([_test("test_ac1_signup[user_9f3a71b0-password123]")])

    assert before == after
    assert ci.regressions(
        ci.Snapshot(label="b", acceptance=before, acceptance_ran=True),
        ci.Snapshot(label="a", acceptance=after, acceptance_ran=True),
    ) == []


def test_a_test_that_really_stopped_passing_is_still_a_regression():
    before = ci.outcomes_of([_test("test_ac1_signup[user_02dc5292-password123]")])
    after = ci.outcomes_of([_test("test_ac1_signup[user_9f3a71b0-password123]", outcome="failed")])

    assert ci.regressions(
        ci.Snapshot(label="b", acceptance=before, acceptance_ran=True),
        ci.Snapshot(label="a", acceptance=after, acceptance_ran=True),
    ) == ["acceptance: acceptance/test_signup.py › test_ac1_signup[user_~-password123]"]


def test_a_snapshot_kept_before_keys_were_stable_still_matches():
    old = {"acceptance/test_signup.py › test_ac1_signup[user_02dc5292-password123]": "passed"}
    now = ci.outcomes_of([_test("test_ac1_signup[user_9f3a71b0-password123]")])

    assert ci.regressions(
        ci.Snapshot(label="b", acceptance=old, acceptance_ran=True),
        ci.Snapshot(label="a", acceptance=now, acceptance_ran=True),
    ) == []


def test_ordinary_names_are_left_alone():
    for name in ("test_ac1_signup", "test_list_notes[3-201]", "test_adds a note", "Notes › [AC-2] deletes a note"):
        assert ci.stable(name) == name
    assert ci.stable("a-1b2c3d4e-5f6a-4b7c-8d9e-0f1a2b3c4d5e-z") == "a-~-z"
