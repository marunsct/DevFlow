"""A unit test of the product's own that fails in two product states beside a green locked suite is set aside, not raised.

Deep review 2026-11-18, item B6: the model writes the unit tests after the code, so they mirror it; fixers chased the
ones that disagreed with the locked suite, were reverted for breaking them, and "own unit tests still fail and ship
failing" was a gap in 28 of the last 150 runs. A set-aside test is recorded and named at release; its file moves
aside only when every test in it failed, so no passing test leaves the run, and nothing is deleted.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from app import ci, completion_verdict
from app.acceptance import junit, suite
from app.acceptance.criteria import number
from app.graph import delivery
from app.graph import unit_test_quarantine as quarantine

W = ci.WHERE


def _project(tmp_path):
    (tmp_path / "app" / "tests").mkdir(parents=True)
    (tmp_path / "app" / "tests" / "test_a.py").write_text("def test_one(): assert 1 == 2\ndef test_two(): assert 0\n")
    (tmp_path / "app" / "tests" / "test_b.py").write_text("def test_ok(): pass\ndef test_bad(): assert 0\n")
    return {f"tests/test_a.py{W}test_one": "failed", f"tests/test_a.py{W}test_two": "failed",
            f"tests/test_b.py{W}test_ok": "passed", f"tests/test_b.py{W}test_bad": "failed"}


def test_a_test_failing_in_one_product_state_is_still_raised_however_often_it_is_measured(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIT_TEST_QUARANTINE", "on")
    outcomes = _project(tmp_path)

    first = quarantine.after_a_green_measurement(tmp_path, outcomes, "state-1", "app")
    again = quarantine.after_a_green_measurement(tmp_path, outcomes, "state-1", "app")

    assert first == again == sorted(k for k, o in outcomes.items() if o == "failed")
    assert quarantine.set_aside(tmp_path) == {}


def test_a_second_product_state_sets_it_aside_and_moves_only_a_file_with_no_passing_test(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIT_TEST_QUARANTINE", "on")
    outcomes = _project(tmp_path)
    quarantine.after_a_green_measurement(tmp_path, outcomes, "state-1", "app")

    still = quarantine.after_a_green_measurement(tmp_path, outcomes, "state-2", "app")

    assert still == []
    aside = quarantine.set_aside(tmp_path)
    assert set(aside) == {f"tests/test_a.py{W}test_one", f"tests/test_a.py{W}test_two", f"tests/test_b.py{W}test_bad"}
    assert not (tmp_path / "app" / "tests" / "test_a.py").exists()
    assert (tmp_path / quarantine.FOLDER / "app" / "tests" / "test_a.py").read_text().startswith("def test_one")
    assert (tmp_path / "app" / "tests" / "test_b.py").exists(), "a file holding a passing test stays in the run"
    assert f"tests/test_b.py{W}test_ok" not in aside


def test_off_nothing_is_counted_or_moved(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIT_TEST_QUARANTINE", "off")
    outcomes = _project(tmp_path)

    assert quarantine.after_a_green_measurement(tmp_path, outcomes, "state-1", "app") is None
    assert quarantine.after_a_green_measurement(tmp_path, outcomes, "state-2", "app") is None
    assert (tmp_path / "app" / "tests" / "test_a.py").exists()


def _released(tmp_path, monkeypatch, failing_units):
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)
    (tmp_path / ".project-directory").write_text("notes\n")
    suite.save_criteria(tmp_path, number("# Brief\n## Features\n- Add a note\n"))
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True)
    spec.write_text("test('[AC-1] adds', ()=>{});\n")
    suite.lock(tmp_path)
    report = junit.Report(found=True, tests=[junit.TestResult(name="[AC-1] adds")])
    monkeypatch.setattr(suite, "run", lambda root: suite._judged(
        root, suite.AcceptanceResult(ran=True, command="npm test", report=report), True))
    # The unit run in the sandbox: what it found failing is given here.
    monkeypatch.setattr(ci, "unit_failures", lambda root, runner=None: list(failing_units))
    return delivery.release({"repository": SimpleNamespace(root_path=str(tmp_path)),
                             "product_intake": SimpleNamespace(product_name="Notes")},
                            {"configurable": {"thread_id": "t"}}, None)


def test_the_release_is_not_held_by_a_test_set_aside_and_names_it_as_a_note(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIT_TEST_QUARANTINE", "on")
    bad = f"tests/test_b.py{W}test_bad"
    (tmp_path / ".harness").mkdir()
    (tmp_path / quarantine.STORE).write_text(json.dumps({"seen": {}, "set_aside": {
        bad: {"why": quarantine.WHY, "file": "app/tests/test_b.py", "moved_to": ""}}}))

    update = _released(tmp_path, monkeypatch, [bad])

    assert update.get("stage") != "technical_lead", "held back for a test set aside"
    gaps = [str(g) for g in update.get("completion_gaps") or []]
    named = [g for g in gaps if quarantine.SET_ASIDE in g]
    assert named and bad in named[0] and "locked acceptance suite passed in full" in named[0]
    assert not any(completion_verdict.is_blocking(g) for g in named)


def test_a_green_round_raises_the_unit_run_until_every_failing_test_is_set_aside(tmp_path, monkeypatch):
    from app.acceptance import unstable

    monkeypatch.setenv("UNIT_TEST_QUARANTINE", "on")
    outcomes = _project(tmp_path)
    # The runner's report as the sandbox wrote it, and the product state the repository holds.
    monkeypatch.setattr(ci, "unit_outcomes_in_the_pack_s_report", lambda root: (outcomes, True))
    states = iter(["state-1", "state-2"])
    monkeypatch.setattr(unstable, "fingerprint", lambda root: next(states))

    assert quarantine.raised_beside_a_green_suite(tmp_path) is True
    assert quarantine.raised_beside_a_green_suite(tmp_path) is False
