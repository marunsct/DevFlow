"""A fix round that closes no defect on a product it leaves unchanged ends the attempt instead of running another round
(LR.53, `FIX_STAGES_THAT_CLOSE_NOTHING`, Efficiency group).
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.acceptance import unstable
from app.graph import unchanged_fix_round as rounds

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _cycle(*statuses):
    return SimpleNamespace(defects=[SimpleNamespace(status=s) for s in statuses])


def _product(monkeypatch, name):
    monkeypatch.setattr(unstable, "fingerprint", lambda root: name)


def test_a_round_that_closed_nothing_on_the_same_product_ends_the_attempt(tmp_path, monkeypatch):
    monkeypatch.setenv("FIX_STAGES_THAT_CLOSE_NOTHING", "on")
    _product(monkeypatch, "same")
    assert not rounds.ends_the_attempt(tmp_path, _cycle("open", "fixed"), attempt="0:0", test_round=1)
    assert rounds.ends_the_attempt(tmp_path, _cycle("open", "fixed"), attempt="0:0", test_round=2)
    # The same round entered again after a pause answers as it did.
    assert rounds.ends_the_attempt(tmp_path, _cycle("open", "fixed"), attempt="0:0", test_round=2)


def test_a_round_that_closed_something_or_changed_the_product_runs_another(tmp_path, monkeypatch):
    monkeypatch.setenv("FIX_STAGES_THAT_CLOSE_NOTHING", "on")
    _product(monkeypatch, "before")
    assert not rounds.ends_the_attempt(tmp_path, _cycle("open", "open"), attempt="0:0", test_round=0)
    # One closed, the product unchanged.
    assert not rounds.ends_the_attempt(tmp_path, _cycle("open", "fixed"), attempt="0:0", test_round=1)
    # Nothing closed, the product changed.
    _product(monkeypatch, "after")
    assert not rounds.ends_the_attempt(tmp_path, _cycle("open", "fixed"), attempt="0:0", test_round=2)


def test_only_consecutive_rounds_of_one_attempt_are_compared():
    before = {"attempt": "0:0", "round": 1, "fingerprint": "f", "closed": 0, "written": 0}
    assert rounds.closed_nothing(before, {"attempt": "0:0", "round": 2, "fingerprint": "f", "closed": 0})
    assert not rounds.closed_nothing(before, {"attempt": "0:1", "round": 2, "fingerprint": "f", "closed": 0})
    assert not rounds.closed_nothing(before, {"attempt": "0:0", "round": 3, "fingerprint": "f", "closed": 0})
    assert not rounds.closed_nothing(before, {"attempt": "0:0", "round": 2, "fingerprint": "", "closed": 0})
    assert not rounds.closed_nothing(None, {"attempt": "0:0", "round": 2, "fingerprint": "f", "closed": 0})


def test_off_it_runs_another_round_as_before(tmp_path, monkeypatch):
    monkeypatch.setenv("FIX_STAGES_THAT_CLOSE_NOTHING", "off")
    _product(monkeypatch, "same")
    assert not rounds.ends_the_attempt(tmp_path, _cycle("open"), attempt="0:0", test_round=1)
    assert not rounds.ends_the_attempt(tmp_path, _cycle("open"), attempt="0:0", test_round=2)
    assert rounds.ON_BY_DEFAULT is False


def test_the_test_round_ends_the_attempt_before_it_sends_defects_to_a_fix_round(tmp_path, monkeypatch):
    from workflow_node_stubs import end_an_attempt

    update, asked = end_an_attempt(monkeypatch, tmp_path, "REPLAN")

    assert asked, "the attempt did not end"
    assert update["stage"] == "technical_lead" and rounds.SAID in str(update)


def test_a_round_that_closed_something_goes_to_the_fix_round(tmp_path, monkeypatch):
    from workflow_node_stubs import a_reported_defect, run_a_test_round

    monkeypatch.setattr(rounds, "ends_the_attempt", lambda *a, **k: False)

    seen = run_a_test_round(monkeypatch, tmp_path, found=[a_reported_defect()], failing_due=["AC-2"])

    assert seen.update["stage"] == "defect_remediation"


def test_its_words_use_none_of_the_banned_ones():
    assert not BANNED.search(rounds.SAID)


def _defect_with(*attempts):
    return SimpleNamespace(status="open", attempts=list(attempts))


_FIRST = {"stage": "defect_fix_1_0", "files": ["notes-api/store/store_test.go"], "did": "",
          "outcome": "left open: its tests still fail"}


def test_a_round_whose_fix_was_written_and_put_back_does_not_end_the_attempt(tmp_path, monkeypatch):
    """LF.1445: all 11 firings in 43 runs came in a round where a fixer wrote a fix and the harness put it back, which
    restores the fingerprint. The attempts are a Go run's real rounds 1 and 2 (shown, put back, raised again); the
    sprint was planned again there, and the defect was fixed four rounds later."""
    monkeypatch.setenv("FIX_STAGES_THAT_CLOSE_NOTHING", "on")
    _product(monkeypatch, "same")
    put_back = {"stage": "defect_fix_2_0", "files": ["notes-api/main.go"], "did": "",
                "outcome": "reverted: it broke the product did not start before this fix either (The product did not "
                           "start for the acceptance suite: no test could reach it)"}

    rounds.ends_the_attempt(tmp_path, SimpleNamespace(defects=[_defect_with(_FIRST)]), attempt="0:0", test_round=1)
    ended = rounds.ends_the_attempt(tmp_path, SimpleNamespace(defects=[_defect_with(_FIRST, put_back)]),
                                    attempt="0:0", test_round=2)

    assert ended is False


def test_a_round_whose_fixers_wrote_nothing_still_ends_the_attempt(tmp_path, monkeypatch):
    monkeypatch.setenv("FIX_STAGES_THAT_CLOSE_NOTHING", "on")
    _product(monkeypatch, "same")
    nothing = {"stage": "defect_fix_2_0", "files": [], "did": "", "outcome": "left open: nothing was changed"}

    rounds.ends_the_attempt(tmp_path, SimpleNamespace(defects=[_defect_with(_FIRST)]), attempt="0:0", test_round=1)

    assert rounds.ends_the_attempt(tmp_path, SimpleNamespace(defects=[_defect_with(_FIRST, nothing)]),
                                   attempt="0:0", test_round=2) is True
