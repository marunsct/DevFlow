"""A run's KPI row carries the family it was scored against, not the brief started last.

Measured: with a run live on each port, `loop.sh kpi` read the family from the brief the loop
started last - the other port's - and four of the last eight ledger rows were filed under the
wrong family, so every comparison with "runs of the same family" compared different products.
"""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "loop"
spec = importlib.util.spec_from_file_location("kpi_ledger_family", SCRIPTS / "kpi_ledger.py")
kpi_ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kpi_ledger)


def test_the_scored_family_wins_over_the_brief_started_last(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "bench").mkdir(parents=True)
    (tmp_path / "data" / "bench" / "run-a.json").write_text(json.dumps({"benchmark": "tasks-api", "score": 1.0}))
    kpis = tmp_path / "run-a.json"
    kpis.write_text(json.dumps({"run": "run-a", "wall_minutes": 60}))
    ledger = tmp_path / "ledger.csv"

    kpi_ledger.main(str(kpis), str(ledger), "notes-api")

    (row,) = list(csv.DictReader(ledger.open()))
    assert row["benchmark"] == "tasks-api"


def test_an_unscored_run_keeps_the_family_it_was_given(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    kpis = tmp_path / "run-b.json"
    kpis.write_text(json.dumps({"run": "run-b", "wall_minutes": 60}))
    ledger = tmp_path / "ledger.csv"

    kpi_ledger.main(str(kpis), str(ledger), "notes-api")

    (row,) = list(csv.DictReader(ledger.open()))
    assert row["benchmark"] == "notes-api"
