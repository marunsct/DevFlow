"""A model request that ended in an error closes there; the next reply is timed from its own request.

A request the server dropped (or a pause cancelled) has no reply. Left open, the next reply in that
stage was paired with it, so the hours a run sat paused or a crashed server was restarted counted as
waiting on the model: the model pressure card's overall speed read 7.8 tokens a second on a run whose
replies came at several times that.
"""
import importlib.util
from pathlib import Path

from app.observability import run_kpis
from app.observability.stage_usage import recent_calls, stage_usage

ROOT = Path(__file__).resolve().parent.parent

ENTRIES = [
    {"kind": "model_request", "stage": "review", "at": "2026-01-01T00:00:00+00:00"},
    {"kind": "model_error", "stage": "review", "at": "2026-01-01T00:00:40+00:00", "error": "502 lost connection"},
    # Paused for three hours, then asked again.
    {"kind": "model_request", "stage": "review", "at": "2026-01-01T03:00:00+00:00"},
    {"kind": "model_response", "stage": "review", "at": "2026-01-01T03:00:10+00:00",
     "usage": {"input_tokens": 100, "output_tokens": 500}},
]


def test_the_stage_waited_ten_seconds():
    assert stage_usage(ENTRIES)[0]["model_seconds"] == 10.0


def test_the_reply_took_ten_seconds():
    assert recent_calls(ENTRIES)[0]["seconds"] == 10.0


def test_the_kpis_count_ten_seconds_of_model_time():
    # The run spans 3 h 0 min 10 s; the model was asked and answered for 10 s of it.
    share = run_kpis.kpis(ENTRIES)["model_busy_share"]
    assert share < 0.01


def test_run_timing_closes_an_errored_request():
    source = (ROOT / "scripts" / "loop" / "run_timing.py").read_text()
    branch = source.split('"model_error"', 1)
    assert len(branch) == 2 and "pop(0)" in branch[1].split("elif", 1)[0]
