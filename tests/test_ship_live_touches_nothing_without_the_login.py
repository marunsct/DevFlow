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
    shutil.copy(SCRIPT.parent / "operator_login.sh", loop / "operator_login.sh")
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


def test_the_worker_is_found_again_after_the_deploy():
    """Measured on its first use: the deploy recreated the worker and every check after it asked the old container."""
    text = SCRIPT.read_text()
    deploy = text.index('"$L" deploy')
    assert "WORKER_C=$(docker compose ps -q worker" in text[deploy:]


def _fakes(tmp_path, stages):
    """A loop.sh that reports one running run in `stages` (one per audit, the last repeating) and a harmless docker."""
    loop = tmp_path / "scripts" / "loop"
    loop.mkdir(parents=True)
    shutil.copy(SCRIPT, loop / "ship_live.sh")
    shutil.copy(SCRIPT.parent / "operator_login.sh", loop / "operator_login.sh")
    calls = tmp_path / "calls.txt"
    (tmp_path / "stages.txt").write_text("\n".join(stages) + "\n")
    (loop / "loop.sh").write_text(f"""#!/bin/sh
echo "$@" >> {calls}
case "$1" in
  status) echo "run-11111111-2222-3333-4444-555555555555|running||now" ;;
  audit) n=$(grep -c '^audit' {calls}); s=$(sed -n "${{n}}p" {tmp_path}/stages.txt); [ -n "$s" ] || s=$(tail -1 {tmp_path}/stages.txt); echo "now in: $s   records=1" ;;
  rewind) echo paused ;;
  *) echo ok ;;
esac
""")
    os.chmod(loop / "loop.sh", 0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "sleep").write_text("#!/bin/sh\nexit 0\n")
    for tool in (bin_dir / "docker", bin_dir / "sleep"):
        os.chmod(tool, 0o755)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "HANDOVER.md").write_text("\n" * 64 + "LOOP_USER=op LOOP_PASSWORD=pw   # operator-login\n")
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "SHIP_WAIT_SECONDS": "200"}
    return loop, calls, env


def test_it_pauses_at_the_stage_boundary_instead_of_polling_for_the_architect(tmp_path):
    """Measured on one run: a deploy paused the architect mid-revision; ten section rewrites failed, the revision
    started over and wrote one part, and the review found four of its findings again. The runner now waits for any
    stage to end before it stops (HR2.R.2), so the script asks for that and polls nothing."""
    loop, calls, env = _fakes(tmp_path, ["principal_architect", "principal_architect", "acceptance_author_0"])
    (loop / "loop.sh").write_text((loop / "loop.sh").read_text().replace(
        'echo "$@" >>', 'echo "$@ PAUSE_AT=${PAUSE_AT:-}" >>', 1))
    subprocess.run(["bash", str(loop / "ship_live.sh")], cwd=tmp_path, env=env, capture_output=True, text=True,
                   timeout=60)
    said = calls.read_text().splitlines()
    pause = next(i for i, line in enumerate(said) if line.startswith("rewind --pause-only"))
    assert said[pause].endswith("PAUSE_AT=boundary")
    assert not [line for line in said[:pause] if line.startswith("audit")]


def test_ship_now_does_not_wait(tmp_path):
    loop, calls, env = _fakes(tmp_path, ["principal_architect"])
    subprocess.run(["bash", str(loop / "ship_live.sh")], cwd=tmp_path, env={**env, "SHIP_NOW": "1"},
                   capture_output=True, text=True, timeout=60)
    said = calls.read_text().splitlines()
    assert not any(line.startswith("audit") for line in said[:next(i for i, l in enumerate(said) if l.startswith("rewind"))])
    assert "export PAUSE_AT=boundary" in SCRIPT.read_text() and 'if [ "${SHIP_NOW:-0}" != 1 ]; then export PAUSE_AT' in SCRIPT.read_text()
