"""Backups with a tested restore, one deploy at a time, rewinds that cannot hang (plans OP.3, OP.4).

No backup of the run database existed; two sessions deploying at once left
containers stuck at `Created`; a rewind's calls had no timeout.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOOP = (ROOT / "scripts" / "loop" / "loop.sh").read_text()


def _branch(name: str) -> str:
    match = re.search(rf"^{name}\)\n(.*?)^  ;;", LOOP, re.S | re.M)
    assert match, name
    return match.group(1)


def test_a_backup_dumps_the_database_compressed_and_its_check_restores_it():
    backup = _branch("backup")
    assert "pg_dump -U postgres -d langchain --no-owner -Fc" in backup
    assert "pg_restore" in backup and 'select count(*) from runs' in backup and "drop database $scratch" in backup


def test_a_restore_never_goes_over_the_live_database():
    restore = _branch("restore")
    assert '[ "$target" != "langchain" ]' in restore and "create database $target" in restore


def test_the_nightly_job_backs_up_even_beside_a_live_run():
    nightly = _branch("nightly")
    assert nightly.index('"$0" backup') < nightly.index("nightly skipped: a run is live")


def test_one_deploy_at_a_time_and_a_rewind_with_timeouts():
    assert "flock -n 9" in _branch("deploy")
    rewind = _branch("rewind")
    assert rewind.count('-m "${REWIND_TIMEOUT:-600}"') == 2


def test_a_change_to_the_app_alone_is_deployed_without_touching_the_worker():
    """A UI change restarted the worker - and the live run's stage - for nothing the run sees."""
    script = (Path(__file__).resolve().parents[1] / "scripts" / "loop" / "loop.sh").read_text()
    body = script[script.index("\ndeploy-app)"):script.index("\ndeploy)")]

    assert "flock -n 9" in body and "worktree add" in body
    commands = [line for line in body.splitlines() if "build --progress" in line or "up -d" in line]
    assert any(line.rstrip().endswith("app >/dev/null 2>&1") for line in commands)
    assert "docker compose up -d --no-deps app" in body
    assert not any("worker" in line for line in commands)
