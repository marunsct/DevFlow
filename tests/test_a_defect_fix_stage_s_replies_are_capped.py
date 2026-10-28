"""A defect-fix stage's replies are capped at `FIX_STAGE_REPLY_TOKENS`; every other stage keeps its length.

Measured on one run: a fix stage's fourteen calls took thirteen minutes, eight of them in two replies of 28,448 and
23,446 tokens (mostly reasoning); an architect's correct specification reply measured 22,810.
"""
from __future__ import annotations

import inspect

import app.models as models
from app.observability import provenance, transcript


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


def test_the_first_call_asks_for_it_and_the_switch_is_registered():
    assert "cap = fix_stage_reply_cap(ceiling)" in inspect.getsource(models.CompatibleChatOpenAI._generate_paced)
    assert "FIX_STAGE_REPLY_CAP" in provenance.SWITCHES
