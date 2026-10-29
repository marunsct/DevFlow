"""The static suite checks, replayed over 30 real locked suites, find what they found when last accepted.

Measured on one run: a new check tried on 40 locked suites, none of which sent a value through a helper, reopened a
right suite in a live run with its first false positive. A change here is reviewed, then accepted with
`.venv/bin/python scripts/loop/locked_suites.py accept`.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "loop" / "locked_suites.py"


def test_no_check_s_findings_on_a_real_suite_changed_unreviewed():
    spec = importlib.util.spec_from_file_location("locked_suites", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len([p for p in module.CORPUS.iterdir() if p.is_dir()]) >= 30
    assert module.changes() == [], "a check's findings on a real locked suite changed: review, then accept"
