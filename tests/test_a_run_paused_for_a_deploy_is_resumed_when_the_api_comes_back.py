"""`ship-live` resumes each paused run, trying again while the app is still starting.

Measured on one deploy: the containers were replaced, the app answered nothing for the login that resume needs, the
script ended on the first failed pipe and two runs sat paused until the next audit.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "loop" / "resume_with_retry.sh"


def _stub(tmp_path: Path, fail_first: int) -> Path:
    counter = tmp_path / "count"
    counter.write_text("0")
    stub = tmp_path / "loop.sh"
    stub.write_text("#!/bin/sh\n"
                    f"n=$(cat {counter}); n=$((n+1)); echo $n > {counter}\n"
                    f"if [ $n -le {fail_first} ]; then echo 'Traceback: no answer' >&2; exit 1; fi\n"
                    "echo '{\"message\":\"Run run-x resumed.\"}'\n")
    stub.chmod(0o755)
    return stub


def _run(stub: Path, tries: int):
    return subprocess.run(["bash", str(SCRIPT), "run-x"], cwd=ROOT, capture_output=True, text=True, timeout=60,
                          env={**os.environ, "RESUME_LOOP_SH": str(stub), "RESUME_TRIES": str(tries), "RESUME_WAIT": "0"})


def test_a_run_is_resumed_once_the_api_answers(tmp_path):
    done = _run(_stub(tmp_path, fail_first=2), tries=5)

    assert done.returncode == 0 and "resumed" in done.stdout


def test_a_run_that_could_not_be_resumed_says_so_and_how_to_resume_it(tmp_path):
    done = _run(_stub(tmp_path, fail_first=99), tries=3)

    assert done.returncode == 1 and "WAS NOT RESUMED" in done.stderr and "loop.sh resume run-x" in done.stderr


def test_ship_live_resumes_through_it_and_ends_non_zero_when_one_was_not_resumed():
    text = (ROOT / "scripts" / "loop" / "ship_live.sh").read_text(encoding="utf-8")

    assert 'scripts/loop/resume_with_retry.sh "$run" || not_resumed=1' in text and "exit 3" in text
