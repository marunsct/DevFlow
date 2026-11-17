"""A fix round that closes no defect on a product it leaves unchanged ends the attempt instead of running another round
(LR.53, `FIX_STAGES_THAT_CLOSE_NOTHING`, Efficiency group).
"""
from __future__ import annotations

import inspect
import re
from types import SimpleNamespace

from app.acceptance import unstable
from app.graph import unchanged_fix_round as rounds
from app.graph import workflow

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
    before = {"attempt": "0:0", "round": 1, "fingerprint": "f", "closed": 0}
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


def test_the_test_round_ends_the_attempt_before_it_sends_defects_to_a_fix_round():
    source = inspect.getsource(workflow)
    node = source[source.index("def test_and_triage_node"):source.index("def _replan_or_escalate")]
    at = node.index("unchanged_fix_round.ends_the_attempt(")
    assert "_replan_or_escalate(state, base_update, cycle, unchanged_fix_round.SAID)" in node[at:at + 600]
    assert at < node.index('stage="defect_remediation"')


def test_its_words_use_none_of_the_banned_ones():
    assert not BANNED.search(rounds.SAID)
