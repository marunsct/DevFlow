"""`ship-live` builds the images before it pauses any run, so a build that fails touches no run (harness review HR2.R.3).

The build ran inside the pause: pause-to-resume gaps were 2-12.7 min a deploy (150 min in a day), and a Docker
Desktop that hung on a container create left both runs paused.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _stub(bin_dir: Path, name: str, log: Path, code: int) -> None:
    path = bin_dir / name
    path.write_text(f"#!/bin/sh\necho \"{name} $*\" >> {log}\nexit {code}\n")
    path.chmod(0o755)


def test_a_failing_build_pauses_no_run(tmp_path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    log.write_text("")
    _stub(bin_dir, "docker", log, 1)   # Docker does not answer
    _stub(bin_dir, "curl", log, 0)     # any API call - a pause - would be logged
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "LOOP_USER": "x", "LOOP_PASSWORD": "y"}

    done = subprocess.run(["bash", str(ROOT / "scripts" / "loop" / "ship_live.sh")], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=120)

    assert done.returncode != 0
    assert "no run was paused" in done.stderr
    calls = log.read_text()
    assert "curl" not in calls, calls
    assert "docker info" in calls


def test_the_deploy_builds_only_when_the_images_are_not_already_that_commit() -> None:
    text = (ROOT / "scripts" / "loop" / "loop.sh").read_text()
    deploy = text[text.index("\ndeploy)"):text.index("\nfreshness)")]
    assert '[ "$(built_from)" = "$built" ]' in deploy
    assert '"$0" build "$built"' in deploy
    build = text[text.index("\nbuild)"):text.index("\nfreshness)")]
    assert "timeout 20 docker info" in build and 'echo "built ${built:0:7} in' in build
