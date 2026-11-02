"""A rewind asked for a stage the run never entered, or with a flag it does not know, touches no run.

Measured: `loop.sh rewind --help` took `--help` for a stage name and paused the current run. Everything runs in a copy
of the script under a temporary root, against stand-ins for `curl` and `docker`, so no server or run is reached.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "loop"
POINTS = '{"points": [{"stage": "technical_lead", "at": "2026-10-20T01:00:00", "sprint": 1, "checkpoint_id": "cp-1"}]}'

FAKE_CURL = f"""#!/bin/sh
echo "$*" >> "$CALLS"
case "$*" in
  *auth/token*) echo '{{"access_token": "t"}}' ;;
  *rewind-points*) echo '{POINTS}' ;;
  */rewind*) printf 'ok\\n202\\n' ;;
esac
"""
FAKE_DOCKER = """#!/bin/sh
if grep -q /pause "$CALLS"; then echo paused; else echo running; fi
"""


def _script(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def rewind(tmp_path):
    for name in ("loop.sh", "rewind_point.py"):
        (tmp_path / "scripts" / "loop").mkdir(parents=True, exist_ok=True)
        shutil.copy(SOURCE / name, tmp_path / "scripts" / "loop" / name)
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "python").symlink_to(sys.executable)
    (tmp_path / "data" / "loop").mkdir(parents=True)
    (tmp_path / "data" / "loop" / "current_run.txt").write_text("run-here\n")
    stand_ins = tmp_path / "stand-ins"
    stand_ins.mkdir()
    _script(stand_ins / "curl", FAKE_CURL)
    _script(stand_ins / "docker", FAKE_DOCKER)
    calls = tmp_path / "calls"
    calls.write_text("")

    def run(*words, credentials=True):
        environment = {
            "PATH": f"{stand_ins}{os.pathsep}{os.environ['PATH']}", "CALLS": str(calls), "LOOP_API": "http://stand-in.invalid",
            **({"LOOP_USER": "someone", "LOOP_PASSWORD": "x"} if credentials else {}),
        }
        done = subprocess.run(["bash", str(tmp_path / "scripts" / "loop" / "loop.sh"), "rewind", *words],
                              capture_output=True, text=True, env=environment, timeout=60)
        return done, calls.read_text()

    return run


def _changed_a_run(calls: str) -> bool:
    return "/pause" in calls or "-X POST http://stand-in.invalid/api/runs/run-here/rewind" in calls


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_lists_the_points_and_pauses_nothing(rewind, flag):
    done, calls = rewind(flag)
    assert done.returncode == 0 and "usage:" in done.stdout and "technical_lead" in done.stdout
    assert not _changed_a_run(calls)


def test_list_lists_the_points_and_pauses_nothing(rewind):
    done, calls = rewind("--list")
    assert done.returncode == 0 and "technical_lead" in done.stdout
    assert not _changed_a_run(calls)


def test_help_needs_no_account(rewind):
    done, calls = rewind("--help", credentials=False)
    assert done.returncode == 0 and "usage:" in done.stdout and calls == ""


def test_an_unknown_flag_is_refused_before_anything_is_asked(rewind):
    done, calls = rewind("--bogus")
    assert done.returncode == 2 and "no run was touched" in done.stderr
    assert calls == ""


def test_a_stage_the_run_never_entered_pauses_nothing_and_lists_the_points(rewind):
    done, calls = rewind("no_such_stage")
    assert done.returncode == 1 and "technical_lead" in done.stderr and "not paused" in done.stderr
    assert not _changed_a_run(calls)


def test_no_point_at_or_before_the_time_pauses_nothing(rewind):
    done, calls = rewind("technical_lead", "run-here", "2026-10-19T00:00")
    assert done.returncode == 1 and not _changed_a_run(calls)


def test_a_known_stage_still_pauses_and_then_rewinds(rewind):
    done, calls = rewind("technical_lead")
    assert done.returncode == 0, done.stderr
    assert calls.index("/pause") < calls.index("/run-here/rewind ")
    assert '"checkpoint_id": "cp-1"' in calls


def test_pause_only_still_pauses_and_asks_for_no_point(rewind):
    done, calls = rewind("--pause-only")
    assert done.returncode == 0 and "/pause" in calls and "rewind-points" not in calls
