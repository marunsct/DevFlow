"""A process the worker marks private cannot have its environment read by a same-user command (LR.30, first step).

Found in the launch review: an agent-run command, running as the worker's user, could read the worker's secrets from
`/proc/<pid>/environ` although its own environment was filtered.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="/proc and prctl are Linux's")
def test_a_private_process_s_environment_cannot_be_read_by_its_own_user():
    code = ("import sys, time; sys.path.insert(0, %r); from app.server.process_privacy import keep_private; "
            "print(keep_private(), flush=True); time.sleep(5)") % str(ROOT / "src")
    child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True,
                             env={"SECRET_FOR_THE_TEST": "s3cret", "PATH": "/usr/bin:/bin"})
    try:
        assert child.stdout.readline().strip() == "True"
        with pytest.raises(PermissionError):
            Path(f"/proc/{child.pid}/environ").read_bytes()
    finally:
        child.kill()


def test_both_worker_processes_are_marked():
    source = (ROOT / "src" / "app" / "server" / "tasks.py").read_text()
    assert source.count("keep_private()") >= 2


def test_the_harness_s_own_code_is_not_the_command_user_s_to_change():
    dockerfile = (ROOT / "Dockerfile").read_text()
    final = dockerfile[dockerfile.rindex("COPY --from=python-builder /opt/venv /opt/venv"):]
    assert "COPY src/ ./src/" in final and "--chown=appuser:appuser src/" not in final
    assert "go-w /app/src" in final
