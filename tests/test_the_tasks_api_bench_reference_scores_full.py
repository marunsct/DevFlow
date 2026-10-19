"""The tasks-api benchmark's reference passes every hidden test (Initiative U.1).

A bench for the class that failed live on a medium brief: a service with
accounts and per-user data, started from `PORT` and `DATA_DIR` alone, so any
secret it needs it makes and keeps itself. A hidden test is only fit to judge a
run once a reference implementation passes all of it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[1] / "benchmarks" / "tasks-api"

pytest.importorskip("httpx")


def test_the_reference_passes_every_hidden_test(tmp_path):
    expected = json.loads((BENCH / "bench.json").read_text())["tests"]
    done = subprocess.run(
        [sys.executable, "-m", "pytest", str(BENCH / "hidden"), "-q", "-p", "no:cacheprovider",
         "--rootdir", str(BENCH / "hidden"), "-c", os.devnull, "--no-header", "-o", "addopts="],
        env={**os.environ, "PRODUCT_DIR": str(BENCH / "reference")},
        capture_output=True, text=True, timeout=300, cwd=tmp_path,
    )
    assert f"{expected} passed" in done.stdout, done.stdout[-1500:] + done.stderr[-800:]


def test_the_brief_says_nothing_else_is_set_in_the_service_s_environment():
    brief = (BENCH / "brief.md").read_text()
    assert "Nothing else is set in its environment" in brief
    assert "start.sh" in brief and "DATA_DIR" in brief


def test_the_kpis_give_each_tool_its_own_failure_rate():
    import importlib.util

    spec = importlib.util.spec_from_file_location("kpi_u1", Path(__file__).resolve().parents[1] / "scripts" / "loop" / "kpi.py")
    kpi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kpi)
    at = "2026-10-19T00:00:0{}+00:00"
    records = [
        {"at": at.format(0), "stage": "s", "kind": "tool_call", "tool": "edit_artifact", "call_id": "a"},
        {"at": at.format(1), "stage": "s", "kind": "tool_result", "call_id": "a", "result": {"error": "no match"}},
        {"at": at.format(2), "stage": "s", "kind": "tool_call", "tool": "read_file", "call_id": "b"},
        {"at": at.format(3), "stage": "s", "kind": "tool_result", "call_id": "b", "result": "text"},
    ]

    got = kpi.kpis(records)["tool_failure_rate_by_tool"]

    assert got == {"edit_artifact": 1.0, "read_file": 0.0}
