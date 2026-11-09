"""Each scored run reports its locked suite's pass rate beside the hidden score, and the gap (plan item 21).

A run whose own suite passes far more than the hidden tests do measured itself on a weaker standard than the one it is
judged by; the score alone cannot show that.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCORE = Path(__file__).resolve().parent.parent / "scripts" / "bench" / "score.py"


def _score_module():
    spec = importlib.util.spec_from_file_location("bench_score", SCORE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_gap_is_visible_less_hidden():
    module = _score_module()
    found = module.visible_and_hidden({"score": 0.556, "harness": {"locked_passed": 12, "locked_failed": 0}})
    assert found == {"visible_score": 1.0, "visible_hidden_gap": 0.444}


def test_an_unscored_run_or_an_empty_suite_reports_none():
    module = _score_module()
    assert module.visible_and_hidden({"score": 1.0, "unscored": True, "harness": {"locked_passed": 3}}) == {}
    assert module.visible_and_hidden({"score": 1.0, "harness": {}}) == {}
