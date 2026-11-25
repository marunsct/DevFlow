"""The next fixer of a defect reads each earlier attempt as measured, not a revert sentence (plan PH.2).

A fixer saw an earlier attempt only as a sentence appended to the defect's
actual behaviour, so it could redo the very change that had been reverted.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents import ledger
from app.sprint import Defect, RemediationCycle


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("DECISION_LEDGER", "on")


def _defect(description: str, status: str = "open", attempts=None) -> Defect:
    return Defect(description=description, severity="major", reproduction_steps="run the suite",
                  expected_behavior="it signs in", actual_behavior="it does not", owner="backend",
                  status=status, attempts=attempts or [])


def test_an_attempt_is_recorded_with_its_files_what_it_did_and_how_it_ended():
    result = SimpleNamespace(changed_files=["app/auth.py"], decisions=["Hashed passwords with bcrypt", "x"])

    record = ledger.attempt_record("defect_fix_1_2", result, "reverted: it broke unit:test_login")

    assert record == {"stage": "defect_fix_1_2", "files": ["app/auth.py"], "did": "Hashed passwords with bcrypt",
                      "outcome": "reverted: it broke unit:test_login"}


def test_the_cycle_keeps_each_attempt_on_its_defect():
    from app.graph.workflow import _with_the_attempt

    cycle = RemediationCycle(sprint_goal="g", defects=[_defect("sign in fails for a new user")])
    result = SimpleNamespace(changed_files=["app/auth.py"], decisions=["Rewrote login"])

    once = _with_the_attempt(cycle, 0, "defect_fix_1_0", result, "left open: its tests still fail")
    twice = _with_the_attempt(once, 0, "defect_fix_2_0", result, "fixed")

    assert [a["outcome"] for a in twice.defects[0].attempts] == ["left open: its tests still fail", "fixed"]
    assert cycle.defects[0].attempts == []


def test_the_next_fixer_reads_its_own_attempts_and_those_of_the_defect_it_recurs_from():
    before = _defect("sign in fails for a new user account", status="fixed", attempts=[
        {"stage": "defect_fix_1_0", "files": ["app/auth.py"], "did": "Rewrote login", "outcome": "fixed"}])
    now = _defect("sign in fails again for a new user account", attempts=[
        {"stage": "defect_fix_2_0", "files": ["app/main.py"], "did": "", "outcome": "reverted: it broke AC-2"}])

    block = ledger.earlier_attempts(now, [before])

    assert "--- Earlier attempts at this defect" in block
    assert '- defect_fix_1_0: changed `app/auth.py`; it said, not measured: "Rewrote login" -> fixed' in block
    assert "- defect_fix_2_0: changed `app/main.py` -> reverted: it broke AC-2" in block


def test_none_and_off_are_no_block(monkeypatch):
    assert ledger.earlier_attempts(_defect("x y z"), []) == ""
    monkeypatch.delenv("DECISION_LEDGER")
    assert ledger.earlier_attempts(_defect("a b c", attempts=[{"stage": "s", "outcome": "fixed"}]), []) == ""


def test_the_fix_loop_records_and_shows_them(tmp_path, monkeypatch):
    """Each fix is recorded on its defect, fixed or reverted, and the next fixer is shown the attempts on its
    defect and on the ones before it."""
    from workflow_nodes import a_defect, a_fix_stage

    shown = []
    monkeypatch.setattr(ledger, "earlier_attempts",
                        lambda defect, earlier: shown.append((defect.description, [d.description for d in earlier])) or "")
    round_ = [a_defect("Saving a note returns 500"), a_defect("Deleting a note returns 500")]

    update, _ = a_fix_stage(tmp_path, round_, defect_index=1)
    assert shown == [("Deleting a note returns 500", ["Saving a note returns 500"])]
    (attempt,) = update["remediation"].defects[1].attempts
    # Nothing measured it: the attempt is recorded as unverified, not fixed.
    assert attempt["stage"] == "defect_fix_2_1" and attempt["outcome"].startswith("unverified")

    update, _ = a_fix_stage(tmp_path, round_, patches={
        "app.graph.engineering.after_a_fix": lambda *args, **kwargs: ["[AC-2] lists notes"]})
    (attempt,) = update["remediation"].defects[0].attempts
    assert attempt["stage"] == "defect_fix_2_0" and attempt["outcome"].startswith("reverted")
