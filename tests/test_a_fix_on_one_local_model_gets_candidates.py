"""After a failed fix, candidates come from the fix's own model when the run has no judgement model of its own (plan AY step 2).

Candidates - several rewrites, each kept only if the defect's own tests pass -
were asked only of a judgement model distinct from the build model, so a run
on one local model went from one rewrite straight to a forty-call agent loop.
"""

from __future__ import annotations

import inspect

import pytest

from app.graph import bounded_fixes as fix_cycle, workflow

BUILD, JUDGE, FIXER = object(), object(), object()


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("FIX_CYCLE", "on")


def test_one_model_writes_its_own_candidates():
    assert fix_cycle.the_candidate_model(BUILD, BUILD, FIXER) is FIXER
    assert fix_cycle.the_candidate_model(None, BUILD) is BUILD


def test_a_judgement_model_of_its_own_still_writes_them():
    assert fix_cycle.the_candidate_model(JUDGE, BUILD, FIXER) is JUDGE


def test_off_until_its_before_and_after_runs_switch_it_on(monkeypatch):
    monkeypatch.delenv("FIX_CYCLE")
    assert fix_cycle.ON_BY_DEFAULT is False
    assert fix_cycle.the_candidate_model(BUILD, BUILD, FIXER) is None
    assert fix_cycle.the_candidate_model(JUDGE, BUILD, FIXER) is JUDGE


def test_the_fix_flow_asks_it():
    assert "candidate_model = the_candidate_model(judgement_model, model, fix_model)" in inspect.getsource(workflow)
