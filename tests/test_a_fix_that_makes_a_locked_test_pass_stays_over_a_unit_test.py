"""A fix that makes a locked test pass and breaks only unit tests stays, and each unit test is raised naming the locked one.

Measured on one run: a locked test asked for a JSON content type on a route, a unit test written earlier asserted the
route's body was empty, and three fixes in a row were reverted for that unit test, so the criterion was never reached.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app import ci
from app.graph import engineering

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
LOCKED = "[AC-3] GET /health answers JSON"
UNIT = "health route has an empty body"


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("UNIT_TESTS_YIELD_TO_THE_LOCKED_SUITE", "on")


def _snapshot(unit, acceptance, **more):
    return ci.Snapshot(label="s", unit=unit, unit_ran=True, acceptance=acceptance, acceptance_ran=True, **more)


BEFORE = _snapshot({UNIT: "passed"}, {LOCKED: "failed", "[AC-1] other": "passed"})
GAINED = _snapshot({UNIT: "failed"}, {LOCKED: "passed", "[AC-1] other": "passed"})


def _after_the_fix(monkeypatch, root, before, after):
    monkeypatch.setattr(engineering, "ci_applies", lambda _: True)
    monkeypatch.setattr(ci, "load", lambda _root, _which: before)
    monkeypatch.setattr(ci, "take", lambda _root, _label: after)
    monkeypatch.setattr(ci, "save", lambda _root, _snap, **_kw: None)
    monkeypatch.setattr(ci, "commit", lambda _root, _message: "c0ffee")
    reverted = []
    monkeypatch.setattr(ci, "revert_to", lambda _root, base: reverted.append(base) or True)
    broke = engineering.after_a_fix(str(root), "abc", "defect_fix_1_0", "[AC-3] health")
    return broke, reverted


def _state(root):
    return {"repository": SimpleNamespace(root_path=str(root))}


def test_the_fix_stays_when_a_locked_test_passes_and_only_a_unit_test_broke(monkeypatch, tmp_path):
    assert _after_the_fix(monkeypatch, tmp_path, BEFORE, GAINED) == ([], [])


def test_the_unit_test_is_raised_naming_the_locked_test(monkeypatch, tmp_path):
    from app.graph import workflow

    _after_the_fix(monkeypatch, tmp_path, BEFORE, GAINED)
    [defect] = workflow._the_unit_tests_a_kept_fix_broke(_state(tmp_path))["review_defects"]

    assert defect.description.startswith(f"Regression: `unit: {UNIT}` passed before")
    assert workflow._A_REGRESSED_TEST.match(defect.description), "closed when that unit test passes again"
    assert "disagrees with the locked test" in defect.actual_behavior and LOCKED in defect.actual_behavior
    assert "AC-3" not in defect.description, "a criterion's id here would judge it by that criterion's tests"
    text = " ".join([defect.description, defect.actual_behavior, defect.expected_behavior, defect.reproduction_steps])
    assert not BANNED.search(text)
    assert workflow._the_unit_tests_a_kept_fix_broke(_state(tmp_path)) == {}, "raised once"


def test_each_broken_unit_test_is_raised_and_what_the_round_holds_stays(monkeypatch, tmp_path):
    from app.graph import workflow

    before = _snapshot({"u1": "passed", "u2": "passed"}, {LOCKED: "failed"})
    after = _snapshot({"u1": "failed", "u2": "failed"}, {LOCKED: "passed"})
    _after_the_fix(monkeypatch, tmp_path, before, after)
    state = {**_state(tmp_path), "review_defects": ["held"]}

    raised = workflow._the_unit_tests_a_kept_fix_broke(state)["review_defects"]

    assert raised[0] == "held" and len(raised) == 3


def test_a_fix_that_also_broke_a_locked_test_is_reverted(monkeypatch, tmp_path):
    after = _snapshot({UNIT: "failed"}, {LOCKED: "passed", "[AC-1] other": "failed"})
    broke, reverted = _after_the_fix(monkeypatch, tmp_path, BEFORE, after)
    assert set(broke) == {f"unit: {UNIT}", "acceptance: [AC-1] other"} and reverted == ["abc"]


def test_a_fix_that_made_no_locked_test_pass_is_reverted(monkeypatch, tmp_path):
    after = _snapshot({UNIT: "failed", "new unit test": "passed"}, {LOCKED: "failed", "[AC-1] other": "passed"})
    broke, reverted = _after_the_fix(monkeypatch, tmp_path, BEFORE, after)
    assert broke == [f"unit: {UNIT}"] and reverted == ["abc"]


def test_a_locked_test_the_last_measurement_did_not_show_failing_is_no_gain(monkeypatch, tmp_path):
    after = _snapshot({UNIT: "failed"}, {"[AC-1] other": "passed", "[AC-8] never measured": "passed"})
    before = _snapshot({UNIT: "passed"}, {"[AC-1] other": "passed"})
    broke, reverted = _after_the_fix(monkeypatch, tmp_path, before, after)
    assert broke == [f"unit: {UNIT}"] and reverted == ["abc"]


def test_a_fix_after_which_the_product_does_not_start_is_reverted(monkeypatch, tmp_path):
    after = _snapshot({UNIT: "failed"}, {LOCKED: "passed", "[AC-1] other": "passed"}, problem="no server")
    _, reverted = _after_the_fix(monkeypatch, tmp_path, BEFORE, after)
    assert reverted == ["abc"]


def test_a_fix_that_stopped_the_unit_runner_is_reverted(monkeypatch, tmp_path):
    after = ci.Snapshot(label="s", unit={}, unit_ran=False, acceptance={LOCKED: "passed", "[AC-1] other": "passed"},
                        acceptance_ran=True)
    _, reverted = _after_the_fix(monkeypatch, tmp_path, BEFORE, after)
    assert reverted == ["abc"]


def test_off_the_fix_is_reverted_as_before_and_nothing_is_raised(monkeypatch, tmp_path):
    from app.graph import workflow

    monkeypatch.setenv("UNIT_TESTS_YIELD_TO_THE_LOCKED_SUITE", "off")
    broke, reverted = _after_the_fix(monkeypatch, tmp_path, BEFORE, GAINED)
    assert broke == [f"unit: {UNIT}"] and reverted == ["abc"]
    assert workflow._the_unit_tests_a_kept_fix_broke(_state(tmp_path)) == {}


def test_a_kept_fix_is_not_also_kept_as_a_candidate_for_a_replay(monkeypatch, tmp_path):
    """`KEPT_FIX_CANDIDATES` looks only at what is reverted."""
    monkeypatch.setattr(engineering, "ci_applies", lambda _: True)
    monkeypatch.setattr(ci, "load", lambda _root, _which: BEFORE)
    monkeypatch.setattr(ci, "take", lambda _root, _label: GAINED)
    monkeypatch.setattr(ci, "save", lambda _root, _snap, **_kw: None)
    monkeypatch.setattr(ci, "commit", lambda _root, _message: "c0ffee")
    seen = []
    assert engineering.after_a_fix(str(tmp_path), "abc", "s", "d", on_revert=seen.append) == [] and seen == []


def test_the_next_round_takes_what_was_raised_as_a_review_defect():
    """The node's update goes where the regressions of a batch go: read by the round, cleared by it."""
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    assert source.count("update.update(_the_unit_tests_a_kept_fix_broke(state))") == 2, "one fix alone, and a batch"
    assert '*(state.get("review_defects") or [])' in source


def test_the_switch_ships_off_and_is_listed():
    # Owner, 2026-11-05: a change that affects quality is always on, with no switch.
    from pathlib import Path

    from app import switches as registry

    assert "UNIT_TESTS_YIELD_TO_THE_LOCKED_SUITE" in registry.BUILT_IN
    assert "UNIT_TESTS_YIELD_TO_THE_LOCKED_SUITE" not in registry.EXPERIMENTS
    compose = (Path(__file__).resolve().parent.parent / "docker-compose.yml").read_text()
    assert "UNIT_TESTS_YIELD_TO_THE_LOCKED_SUITE: " not in compose
