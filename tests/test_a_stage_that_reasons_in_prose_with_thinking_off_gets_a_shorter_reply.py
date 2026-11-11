"""Once a stage's reply wrote its reasoning in prose to the cap with thinking off, its later thinking-off replies are shorter.

Reasoning-cost review M3 (L3), behind `THINKING_OFF_REPLY_CAP`. Measured over 25 runs: 57 of 57 thinking-off fix
replies that hit the 12,000 cap were prose reasoning, 344 minutes of wall time; thinking off did not stop them.
"""
from __future__ import annotations

import app.models as models
from app import switches
from app.observability import provenance, transcript

OFF = {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}, "reasoning_effort": "none"}}


def _at(monkeypatch, tmp_path, stage="defect_fix_2_0"):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RUN_TRANSCRIPT", "on")
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: stage)
    monkeypatch.setattr(transcript, "_run_id_from_config", lambda: "run-prose")
    models._REASONED_IN_PROSE.clear()


def test_after_prose_reasoning_a_thinking_off_reply_is_capped_lower(monkeypatch, tmp_path):
    _at(monkeypatch, tmp_path)
    monkeypatch.setenv("THINKING_OFF_REPLY_CAP", "on")
    assert models.thinking_off_reply_cap(12_000, 35_000, OFF) == 12_000  # nothing reasoned in prose yet
    models.note_reasoned_in_prose()
    assert models.thinking_off_reply_cap(12_000, 35_000, OFF) == models.THINKING_OFF_REPLY_TOKENS
    assert models.thinking_off_reply_cap(12_000, 35_000, {}) == 12_000  # thinking on: the stage's cap
    assert models.thinking_off_reply_cap(None, 35_000, OFF) == models.THINKING_OFF_REPLY_TOKENS


def test_a_stage_resumed_after_a_restart_reads_it_from_the_transcript(monkeypatch, tmp_path):
    _at(monkeypatch, tmp_path)
    monkeypatch.setenv("THINKING_OFF_REPLY_CAP", "on")
    transcript.record("run-prose", "defect_fix_2_0", "model_response", salvaged="reasoning", reasoning_chars=48000)
    assert models.thinking_off_reply_cap(12_000, 35_000, OFF) == 12_000  # reasoned in its own channel: not prose
    models._REASONED_IN_PROSE.clear()
    transcript.record("run-prose", "defect_fix_2_0", "model_response", salvaged="failed", reasoning_chars=0)
    assert models.thinking_off_reply_cap(12_000, 35_000, OFF) == models.THINKING_OFF_REPLY_TOKENS


def test_off_by_default_and_registered(monkeypatch, tmp_path):
    _at(monkeypatch, tmp_path)
    monkeypatch.setenv("THINKING_OFF_REPLY_CAP", "off")
    models.note_reasoned_in_prose()
    assert models.thinking_off_reply_cap(12_000, 35_000, OFF) == 12_000
    assert models.thinking_off_reply_cap_switch.ON_BY_DEFAULT is False
    assert "THINKING_OFF_REPLY_CAP" in provenance.SWITCHES
    assert "THINKING_OFF_REPLY_CAP" in switches.BUNDLES["PREMIUM_MODEL_TUNING"]


def test_the_paced_call_asks_for_it():
    import inspect

    assert "cap = thinking_off_reply_cap(cap, ceiling, kwargs)" in inspect.getsource(models.CompatibleChatOpenAI._generate_paced)
