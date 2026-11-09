"""Each command's ledger entry records the most memory its process tree held while it ran.

Found in review: the sandbox measures a running command's whole process tree
twice a second (to stop it before the kernel kills the worker) and kept none
of it. When the worker was killed for memory, the run's ledger said which
commands had run and what each exited with, and nothing said which of them
had grown - the one record that could name the command was thrown away.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

from app.tools import sandbox

pytestmark = pytest.mark.skipif(not os.path.isdir("/proc/self"), reason="needs /proc")


def test_the_watch_keeps_the_tree_s_peak(monkeypatch):
    monkeypatch.setattr(sandbox, "_tree_budget_bytes", lambda: 4 * 1024**3)
    code = (
        "import time\n"
        "held = bytearray(80 * 1024 * 1024)\n"
        "for i in range(0, len(held), 4096): held[i] = 1\n"
        "time.sleep(1.5)\n"
    )

    sandbox._run_and_watch_the_tree([sys.executable, "-c", code], cwd=os.getcwd(), env=dict(os.environ), timeout=30)

    peak = sandbox._MEMORY_PEAK_OF_THE_COMMAND.get()
    assert peak is not None and peak > 70 * 1024**2


def _the_ledger(repo_root) -> list[dict]:
    return sandbox.read_execution_ledger(str(repo_root))


def test_the_peak_is_written_onto_the_command_s_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    workspace = tmp_path / "notes-workspace"
    workspace.mkdir()

    def run(cls, command, repo_root, *args, **kwargs):
        sandbox._MEMORY_PEAK_OF_THE_COMMAND.set(612 * 1024**2)
        return {"stdout": "ok", "stderr": "", "returncode": "0"}

    monkeypatch.setattr(sandbox.SandboxExecutor, "_run", classmethod(run))

    sandbox.SandboxExecutor.execute(["node", "--test"], str(workspace), "testing_specialist", "test", for_the_harness=True)

    entries = _the_ledger(workspace)
    assert entries and entries[-1]["memory_peak_mb"] == 612.0


def test_a_command_too_brief_to_measure_records_no_peak(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    workspace = tmp_path / "notes-workspace"
    workspace.mkdir()
    sandbox._MEMORY_PEAK_OF_THE_COMMAND.set(999 * 1024**2)

    monkeypatch.setattr(
        sandbox.SandboxExecutor, "_run",
        classmethod(lambda cls, *a, **k: {"stdout": "", "stderr": "", "returncode": "0"}),
    )

    sandbox.SandboxExecutor.execute(["node", "--version"], str(workspace), "testing_specialist", "test", for_the_harness=True)

    entry = _the_ledger(workspace)[-1]
    assert "memory_peak_mb" not in entry, "an earlier command's peak is not this one's"
    json.dumps(entry)
