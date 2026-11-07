"""The audit's redundant-read line says when the count is too small to mean waste.

Measured over one evening: 3 redundant reads of 69 printed as 39% against a "healthy 8-19%" band and were chased
twice; the one real case was 14 by one stuck stage.
"""
from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "audit_live.py"


def test_the_line_distinguishes_noise_from_a_count_worth_a_look():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "noise, not waste" in text and "_FEW = 10" in text
    assert "healthy: 8-19%; before the digest" not in text
