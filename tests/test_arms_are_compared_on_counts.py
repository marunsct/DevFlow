"""Two arms are compared on counts - hidden tests lost, false acceptances, defects left open - before means
(HR2.E.3). With most runs at a hidden score of 1.0, a mean of 0.95 hid "one hidden test lost"."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "kpi_ledger.py"
spec = importlib.util.spec_from_file_location("kpi_ledger_e3", SCRIPT)
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)


def test_the_row_carries_hidden_tests_lost_and_false_acceptance(tmp_path):
    (tmp_path / "run-x.json").write_text(json.dumps({"score": 0.9, "passed": 9, "total": 10, "false_acceptance": True}))
    row = ledger.with_the_scores({"run": "run-x"}, bench=tmp_path)
    assert row["hidden_tests_failed"] == 1 and row["false_acceptance"] == 1


def test_the_arm_report_leads_with_the_counts():
    a = [{"hidden_tests_failed": "0", "false_acceptance": "0", "defects_left_open": "2"},
         {"hidden_tests_failed": "1", "false_acceptance": "1", "defects_left_open": "3"}]
    b = [{"hidden_tests_failed": "0", "false_acceptance": "0", "defects_left_open": "1"},
         {"hidden_tests_failed": "0", "false_acceptance": "0", "defects_left_open": "1"}]
    out = ledger.compare_arms(a, b)
    assert out[0] == "hidden tests lost: arm A 1 in 2 run(s), arm B 0 in 2 run(s)"
    assert out[1] == "false acceptances: arm A 1 in 2 run(s), arm B 0 in 2 run(s)"


def test_the_timing_report_says_how_much_of_the_wall_was_paused():
    text = (Path(__file__).resolve().parent.parent / "scripts" / "loop" / "run_timing.py").read_text(encoding="utf-8")
    assert "def paused_seconds_of(records)" in text and "paused {paused/60:.0f} min for deploys" in text
