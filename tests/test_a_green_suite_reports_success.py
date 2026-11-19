"""`loop.sh suite` exits 0 when every test passed.

Measured 2026-11-20: a suite of 18,618 passed and none failed exited 1. With `set -euo pipefail`, the step that
collects the failures to run again - a `grep` that finds none - failed the pipeline and ended the script, so a green
suite read as a red one to anything that checks the exit status.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _a_tree(tmp_path: Path, pytest_says: str) -> Path:
    (tmp_path / "scripts" / "loop").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "loop" / "loop.sh", tmp_path / "scripts" / "loop" / "loop.sh")
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n"
                      "case \"$*\" in *xdist*) exit 1 ;; esac\n"
                      f"printf '%s\\n' {pytest_says!r}\n")
    python.chmod(python.stat().st_mode | stat.S_IEXEC)
    return tmp_path / "scripts" / "loop" / "loop.sh"


def _suite(script: Path) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "COMPOSE_FILE"}
    env["PATH"] = "/usr/bin:/bin"  # no docker, no npx: only the suite's own steps run
    return subprocess.run(["bash", str(script), "suite"], capture_output=True, text=True, env=env, timeout=60)


def test_a_suite_with_no_failure_exits_zero(tmp_path):
    done = _suite(_a_tree(tmp_path, "5 passed in 1.00s"))

    assert done.returncode == 0, done.stdout + done.stderr
    assert "5 passed" in done.stdout
