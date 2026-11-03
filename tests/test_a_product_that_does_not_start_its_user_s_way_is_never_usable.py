"""The verdict that a product does not start its user's way reaches every reader, though its suite passed.

Deep review, top code finding: the start check set the verdict on a green suite, and the snapshot dropped it because
tests had run; settlement then closed a start defect on any snapshot, the release read only criterion statuses, and the
best attempt could record a product its user could not start.
"""
from __future__ import annotations

from app import ci
from app.acceptance import junit, suite
from app.graph import best_attempt

NOT_STARTING = f"{suite.PRODUCT_DID_NOT_START}: `start.sh` exited with code 2"


def _green(problem: str = "") -> suite.AcceptanceResult:
    report = junit.Report(tests=[junit.TestResult(name="[AC-1] lists", outcome="passed")], found=True)
    return suite.AcceptanceResult(ran=True, exit_code=0, report=report, problem=problem)


def test_the_snapshot_keeps_it_though_tests_ran(tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "_run_unit", lambda root, runner: ({}, False))
    monkeypatch.setattr(ci, "head", lambda root: "abc")
    assert ci.take(tmp_path, "after a fix", acceptance=_green(NOT_STARTING)).problem.startswith(suite.PRODUCT_DID_NOT_START)
    assert ci.take(tmp_path, "after a fix", acceptance=_green()).problem == ""


def test_a_product_that_does_not_start_is_never_the_best(tmp_path, monkeypatch):
    monkeypatch.setattr(suite, "last_result", lambda root: {"ran": True, "passed": 12, "problem": NOT_STARTING})
    assert best_attempt._passed_now(tmp_path) is None
    monkeypatch.setattr(suite, "last_result", lambda root: {"ran": True, "passed": 12, "problem": ""})
    assert best_attempt._passed_now(tmp_path) == 12


def test_a_fix_that_keeps_the_suite_green_and_breaks_the_user_s_start_is_reverted(tmp_path, monkeypatch):
    import subprocess

    from app.graph import engineering

    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=h@example.com", "-c", "user.name=h", *args],
                       check=True, capture_output=True)

    (tmp_path / ".project-directory").write_text("app")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("X = 1\n")
    git("init", "-q"), git("add", "-A"), git("commit", "-qm", "base")
    base = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (tmp_path / "app" / "main.py").write_text("X = 2\n")
    green = ci.Snapshot(label="latest", acceptance={"[AC-1] lists": "passed"}, acceptance_ran=True)
    after = ci.Snapshot(label="after", acceptance={"[AC-1] lists": "passed"}, acceptance_ran=True, problem=NOT_STARTING)
    reverted: list[str] = []
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(ci, "load", lambda root, which: green)
    monkeypatch.setattr(ci, "take", lambda root, label: after)
    monkeypatch.setattr(ci, "save", lambda root, snapshot: None)
    monkeypatch.setattr(ci, "commit", lambda root, message: None)
    monkeypatch.setattr(ci, "revert_to", lambda root, b: reverted.append(b) or True)
    monkeypatch.setattr("app.analysis.language_service.underlined_in", lambda *a, **k: {})

    broke = engineering.after_a_fix(str(tmp_path), base, "defect_fix_1_0", "a change")

    assert reverted == [base]
    assert any("no longer starts the way its user starts it" in item for item in broke)


def test_the_release_holds_a_green_suite_whose_product_does_not_start(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import pytest

    from app.graph import delivery

    monkeypatch.setattr(delivery.suite, "is_locked", lambda root: True)
    monkeypatch.setattr(delivery.suite, "run", lambda root: SimpleNamespace(
        failing=lambda: [], summary=lambda: "17 passed", ran=True, problem=NOT_STARTING))
    monkeypatch.setattr(delivery.suite, "vacuous_green", lambda root, result: [])
    monkeypatch.setattr(delivery.suite, "deferred", lambda root: {})
    monkeypatch.setattr(delivery, "_unit_tests_failing", lambda root: [])
    monkeypatch.setattr(delivery, "_root", lambda state: str(tmp_path))
    monkeypatch.setattr("app.graph.acceptance_nodes.naming_back_to_qa", lambda state: None)
    monkeypatch.setattr("app.graph.last_try_on_deferred.try_them", lambda root, state: None)

    class _Stop(Exception):
        pass

    recorded = {}

    def _record(state, update, **kwargs):
        recorded.update(kwargs)
        raise _Stop

    monkeypatch.setattr("app.decisions.record_decision", _record)
    with pytest.raises(_Stop):
        delivery.release({"release_attempts": 0}, {"configurable": {}}, SimpleNamespace(judgement_model=None))
    assert recorded["decision"] != "release"
    assert suite.PRODUCT_DID_NOT_START in recorded["rationale"]
