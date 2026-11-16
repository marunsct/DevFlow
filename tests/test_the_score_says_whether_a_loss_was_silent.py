"""The score records the harness's own verdict and whether a lost hidden test was a silent loss (LR.20, LR.21).

Measured over the last 150 scored runs: all 13 losses were runs the harness called completed, and the release
candidate was counted on hidden scores alone, so a loss the harness had warned of and one it had not read the same.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "scripts" / "bench"


def _score():
    spec = importlib.util.spec_from_file_location("bench_score_verdict", ROOT / "score.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_completed_run_s_verdict_is_recorded(tmp_path):
    score = _score()
    cut = "AC-4 ships deferred, unproven by the suite: the export view"
    assert score.harness_verdict(tmp_path / "p", "completed", [cut])["verdict"] == "delivered_with_cuts"
    assert score.harness_verdict(tmp_path / "p", "completed", ["The project has no README: x"])["verdict"] == "not_deliverable"
    assert "verdict" not in score.harness_verdict(tmp_path / "p", "failed", [])


def test_a_silent_loss_is_a_false_acceptance_the_verdict_did_not_warn_of():
    source = (ROOT / "score.py").read_text()
    assert 'result["silent_loss"] = bool(result["false_acceptance"]) and result["harness"].get("verdict") != "not_deliverable"' in source
    assert "SILENT LOSS" in source
