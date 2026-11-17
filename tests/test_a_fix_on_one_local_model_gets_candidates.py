"""After a failed fix, candidates come from the fix's own model when the run has no judgement model of its own (plan AY step 2).

Candidates - several rewrites, each kept only if the defect's own tests pass -
were asked only of a judgement model distinct from the build model, so a run
on one local model went from one rewrite straight to a forty-call agent loop.
"""

from __future__ import annotations


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
    monkeypatch.setenv("FIX_CYCLE", "off")
    assert fix_cycle.ON_BY_DEFAULT is False
    assert fix_cycle.the_candidate_model(BUILD, BUILD, FIXER) is None
    assert fix_cycle.the_candidate_model(JUDGE, BUILD, FIXER) is JUDGE


def test_the_fix_flow_asks_it(tmp_path):
    """After a failed fix, the candidates are written by the model `the_candidate_model` names, and the one the
    defect's tests pass is kept without starting a fixer."""
    from app.agents.specialists import SpecialistOutput
    from workflow_nodes import a_defect, a_fix_stage

    asked, candidates = [], []
    chosen = object()
    kept = SpecialistOutput(changed_files=["app/server.js"], tests=["tests/notes.test.js"])

    def by_candidates(defect, root, model, passes, **kwargs):
        candidates.append(model)
        return kept

    once_failed = a_defect("Saving a note returns 500", fix_attempts=1)
    _, fixed = a_fix_stage(tmp_path, [once_failed], patches={
        **{
        "app.graph.workflow._the_run_approves_its_own_writes": lambda run_id: True,
        "app.graph.workflow._fast_delivery": lambda: True,
        "app.graph.localisation.localised": lambda *args, **kwargs: None,
        "app.graph.rewritten_fixes.what_failed": lambda *args, **kwargs: "",
        "app.graph.rewritten_fixes.files_to_fix": lambda *args, **kwargs: [],
    },
        "app.graph.bounded_fixes.the_candidate_model":
            lambda judgement, model, fix_model: asked.append((judgement, model, fix_model)) or chosen,
        "app.graph.rewritten_fixes.fix_by_candidates": by_candidates,
    })

    assert asked and candidates == [chosen]
    assert fixed["gated"] == [], "a fixer was started although a candidate was kept"
