"""`loop.sh ship-live` touches no run when the operator login is not loaded.

Measured on 2026-11-05: a deploy was sent with its pause skipped because the login was not loaded, and both live runs
sat orphaned about 18 minutes. The one-step deploy refuses before pausing, deploying or resuming anything.
"""
import os
import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "ship_live.sh"


def test_no_login_means_no_call(tmp_path):
    loop = tmp_path / "scripts" / "loop"
    loop.mkdir(parents=True)
    shutil.copy(SCRIPT, loop / "ship_live.sh")
    calls = tmp_path / "calls.txt"
    (loop / "loop.sh").write_text(f"#!/bin/sh\necho \"$@\" >> {calls}\n")
    os.chmod(loop / "loop.sh", 0o755)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "HANDOVER.md").write_text("\n" * 70)
    env = {k: v for k, v in os.environ.items() if k not in ("LOOP_USER", "LOOP_PASSWORD")}

    done = subprocess.run(["bash", str(loop / "ship_live.sh")], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=60)

    assert done.returncode == 1 and "login is not loaded" in done.stderr
    assert not calls.exists()


def test_it_never_grows_the_pool():
    assert "pool_grow" not in SCRIPT.read_text().replace("`pool_grow`", "")
