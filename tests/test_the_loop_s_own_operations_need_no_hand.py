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
    assert nightly.index('"$0" backup') < nightly.index("nightly skipped: $live runs are live")


def test_the_nightly_runs_beside_one_live_run_and_skips_only_beside_two():
    """It uses a scratch workspace and no model; skipping whenever a run was live skipped 15 of 18 nights (HR2.O.3)."""
    nightly = _branch("nightly")
    assert '[ "${live:-2}" -ge "${NIGHTLY_SKIP_AT:-2}" ]' in nightly


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


def test_a_deploy_can_build_a_named_commit_for_a_measure_pair():
    """A Measure pair runs on exactly its Fix batch while later work is committed above it."""
    script = (Path(__file__).resolve().parents[1] / "scripts" / "loop" / "loop.sh").read_text()
    body = script[script.index("\ndeploy)\n"):script.index("\ndeploy-app)") if script.index("\ndeploy-app)") > script.index("\ndeploy)\n") else None]

    assert 'built=$(git -C "$ROOT" rev-parse "${2:-HEAD}^{commit}")' in body
    # The named commit is built by `loop.sh build` (HR2.R.3), from its own clean checkout.
    assert '"$0" build "$built"' in body
    build = script[script.index("\nbuild)\n"):script.index("\nfreshness)")]
    assert 'worktree add -q --detach "$head_tree" "$built"' in build


def test_a_held_out_family_refuses_a_learning_run(tmp_path):
    """A static held-out set is tuned to; a held-out family runs for a Measure run only (HR2.E.4)."""
    import shutil
    import subprocess

    root = Path(__file__).resolve().parents[1]
    family = root / "benchmarks" / "zz-held-out-probe"
    family.mkdir()
    try:
        (family / "brief.md").write_text("# probe\n")
        (family / "bench.json").write_text('{"kind": "http_api", "held_out_since": "2026-11-08"}')
        done = subprocess.run(["bash", str(root / "scripts" / "loop" / "loop.sh"), "bench", "zz-held-out-probe"],
                              cwd=root, capture_output=True, text=True, timeout=60)
        assert done.returncode == 2 and "held out since 2026-11-08" in done.stderr
    finally:
        shutil.rmtree(family)
