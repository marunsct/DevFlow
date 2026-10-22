"""An arm is found by the short commit the docs and the deploy name it by.

The ledger keeps the full commit; `arms 039ad84 20dcdfbe` matched exactly and
found no run of either arm after Measure pair 2.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "loop"
spec = importlib.util.spec_from_file_location("kpi_ledger_arms", SCRIPTS / "kpi_ledger.py")
kpi_ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kpi_ledger)

ROWS = [
    {"run": "a", "harness_commits": "039ad843e3e82d6139fa93444f181ed722a2ee8d", "mixed_versions": "False", "benchmark": "tasks-api"},
    {"run": "b", "harness_commits": "039ad843e3e82d6139fa93444f181ed722a2ee8d", "mixed_versions": "False", "benchmark": "tasks-api"},
    {"run": "c", "harness_commits": "039ad843e3e8 20dcdfbe9033", "mixed_versions": "True", "benchmark": "tasks-api"},
    {"run": "d", "harness_commits": "20dcdfbe9033f2f18f12ce8adec8d2dbc025ce25", "mixed_versions": "False", "benchmark": "other"},
]


def test_a_short_commit_finds_its_runs_and_a_mixed_run_stays_out():
    assert [r["run"] for r in kpi_ledger.the_arm(ROWS, "039ad84", "tasks-api")] == ["a", "b"]
    assert [r["run"] for r in kpi_ledger.the_arm(ROWS, "039ad843e3e82d6139fa93444f181ed722a2ee8d")] == ["a", "b"]
    assert kpi_ledger.the_arm(ROWS, "20dcdfbe", "tasks-api") == []
    assert kpi_ledger.the_arm(ROWS, "") == []
