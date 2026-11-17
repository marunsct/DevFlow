"""A defect-fix stage's replies are capped at `FIX_STAGE_REPLY_TOKENS`; every other stage keeps its length.

Measured on one run: a fix stage's fourteen calls took thirteen minutes, eight of them in two replies of 28,448 and
23,446 tokens (mostly reasoning); an architect's correct specification reply measured 22,810.
"""
from __future__ import annotations

import app.models as models
from app.observability import transcript


def test_a_fix_stage_gets_the_cap_and_a_smaller_ceiling_wins(monkeypatch):
    monkeypatch.setenv("FIX_STAGE_REPLY_CAP", "on")
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: "defect_fix_1_1")
    assert models.fix_stage_reply_cap(None) == models.FIX_STAGE_REPLY_TOKENS == 12_000
    assert models.fix_stage_reply_cap(8_000) == 8_000


def test_other_stages_and_the_switch_off_get_none(monkeypatch):
    monkeypatch.setenv("FIX_STAGE_REPLY_CAP", "on")
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: "principal_architect")
    assert models.fix_stage_reply_cap(None) is None
    monkeypatch.setenv("FIX_STAGE_REPLY_CAP", "off")
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: "defect_fix_1_1")
    assert models.fix_stage_reply_cap(None) is None


def test_a_fix_stage_s_request_carries_the_cap(monkeypatch):
    from workflow_nodes import a_served_model

    monkeypatch.setenv("FIX_STAGE_REPLY_CAP", "on")
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: "defect_fix_1_1")
    model, sent = a_served_model()

    model.invoke("Fix the defect.")

    [body] = sent
    assert 12_000 in (body.get("max_tokens"), body.get("max_completion_tokens")), body


def test_a_run_records_whether_the_cap_was_on(monkeypatch):
    from app.observability import provenance

    monkeypatch.setenv("FIX_STAGE_REPLY_CAP", "on")
    assert "FIX_STAGE_REPLY_CAP" in provenance.switches_on()
    monkeypatch.setenv("FIX_STAGE_REPLY_CAP", "off")
    assert "FIX_STAGE_REPLY_CAP" not in provenance.switches_on()
