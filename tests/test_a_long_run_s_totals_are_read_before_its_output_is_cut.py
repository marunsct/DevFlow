"""A long test run's totals are read from its whole output, before that output is cut for the model.

Deep review of the parsers (2026-11-25), finding 4d. Playwright prints "N failed", then the list of the failed tests,
then "N passed". The ledger read the totals from the output as the model is shown it - its head and its tail - and on
a long run the "N failed" line is in the middle that is cut. Measured on a medium brief's acceptance authors: 97 tests,
93 failing, recorded as 4 of 4 passing, 27 results in a row; when one fewer test passed the author was told the suite
had shrunk and not to remove tests. The output here is that run's, as the journal kept it.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from app.tools import sandbox

WHOLE = (Path(__file__).parent / "captured" / "playwright-1.64-97-tests-93-failed.log").read_text(encoding="utf-8")


def test_the_ledger_counts_the_failures_the_cut_left_out(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "in-container")
    monkeypatch.setattr(sandbox, "MAX_OUTPUT_SIZE", 12_000)
    monkeypatch.setattr(sandbox.SandboxExecutor, "_resolve_executable", staticmethod(lambda name, *a, **k: "/usr/bin/" + name))
    monkeypatch.setattr(sandbox, "_run_and_watch_the_tree",
                        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1, WHOLE, ""))
    workspace = tmp_path / "dashboard-workspace"
    workspace.mkdir()

    outcome = sandbox.SandboxExecutor.execute(["npx", "playwright", "test"], str(workspace), "testing_specialist", "test")

    assert "93 failed" not in outcome["stdout"], "the model is shown the cut output"
    entry = sandbox.read_execution_ledger(str(workspace))[-1]
    assert (entry["passed"], entry["failed"], entry["tests"]) == (4, 93, 97)
