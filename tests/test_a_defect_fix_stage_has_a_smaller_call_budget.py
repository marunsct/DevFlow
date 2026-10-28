"""A defect-fix stage stops at `FIX_STAGE_MODEL_CALLS` model calls instead of the budget every stage shares.

Measured over ten runs: the median productive agent-loop fix took 12 calls; the five most expensive stages were
36-40-call loops that ended in a surrender ("we can't fix all", empty `changed_files`), 1.1-1.9M input tokens each.
"""
from __future__ import annotations

import inspect

from app.agents import settled_answer
from app.observability import provenance, transcript


def test_a_fix_stage_gets_the_smaller_cap_and_others_keep_theirs(monkeypatch):
    monkeypatch.setenv("FIX_STAGE_CALL_CAP", "on")
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: "defect_fix_2_4")
    assert settled_answer._the_step_limit(40) == settled_answer.FIX_STAGE_MODEL_CALLS == 16
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: "specialist_backend_1")
    assert settled_answer._the_step_limit(40) == 40
    assert settled_answer._the_step_limit(0) == 0


def test_off_it_changes_nothing(monkeypatch):
    monkeypatch.setenv("FIX_STAGE_CALL_CAP", "off")
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: "defect_fix_2_4")
    assert settled_answer._the_step_limit(40) == 40


def test_every_use_of_the_budget_reads_it_and_the_switch_is_registered():
    source = inspect.getsource(settled_answer.build_settled_answer_middleware)
    assert source.count("_the_step_limit(step_limit)") >= 5
    assert ">= step_limit" not in source and "(messages, step_limit," not in source and "step_limit - _model" not in source
    assert "FIX_STAGE_CALL_CAP" in provenance.SWITCHES
