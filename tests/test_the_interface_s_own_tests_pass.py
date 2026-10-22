"""The interface's own tests (Vitest: the status map, the appearance, the session, the runs table) run with the suite."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parents[1] / "langchain-ui"


@pytest.mark.skipif(shutil.which("npm") is None or not (UI / "node_modules" / ".bin" / "vitest").exists(),
                    reason="needs npm and the interface's dependencies installed")
def test_vitest_passes():
    done = subprocess.run(["npm", "test", "--silent"], cwd=UI, capture_output=True, text=True, timeout=240)

    assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-500:]
    assert "failed" not in done.stdout.lower().split("tests")[-1]


def test_ci_runs_them_for_the_interface_too():
    workflow = (UI.parent / ".github" / "workflows" / "ci.yml").read_text()

    assert "npm test" in workflow
