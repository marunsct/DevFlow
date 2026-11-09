"""The images are built with an anonymous Docker configuration first, and the owner's own one only as a fall-back.

Measured: with the owner's credential store locked, Docker's credential helper hung every build for an hour, while the
same build with no credential store took 18 seconds. The anonymous configuration keeps the owner's Docker context.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _build(tmp_path, anonymous_fails: bool):
    home = tmp_path / "home"
    (home / ".docker" / "contexts").mkdir(parents=True)
    (home / ".docker" / "config.json").write_text(json.dumps({"currentContext": "desktop-linux", "credsStore": "desktop"}))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log, built = tmp_path / "calls.log", tmp_path / "built"
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (bin_dir / "docker").write_text(
        "#!/bin/sh\n"
        f'echo "DOCKER_CONFIG=${{DOCKER_CONFIG:-}} $*" >> {log}\n'
        'case "$*" in\n'
        f'  *" build "*) if [ -n "${{DOCKER_CONFIG:-}}" ] && [ "{int(anonymous_fails)}" = 1 ]; then exit 1; fi; touch {built} ;;\n'
        f'  "image inspect"*) [ -f {built} ] && echo HARNESS_COMMIT={head} || echo HARNESS_COMMIT=old ;;\n'
        "esac\nexit 0\n")
    (bin_dir / "docker").chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(home)}
    env.pop("DOCKER_CONFIG", None)
    done = subprocess.run(["bash", str(ROOT / "scripts" / "loop" / "loop.sh"), "build"], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=300)
    builds = [line for line in log.read_text().splitlines() if " build --progress=plain" in line]
    return done, builds


def test_the_build_is_anonymous_and_keeps_the_context(tmp_path):
    done, builds = _build(tmp_path, anonymous_fails=False)
    assert done.returncode == 0, done.stderr
    assert len(builds) == 1 and builds[0].startswith("DOCKER_CONFIG=") and "docker-anonymous" in builds[0]
    anon = Path(builds[0].split()[0].split("=", 1)[1])
    config = json.loads((anon / "config.json").read_text())
    assert config == {"currentContext": "desktop-linux"}, "no credential store, the owner's context kept"
    assert (anon / "contexts").is_symlink()


def test_a_failed_anonymous_build_falls_back_to_the_owner_s_configuration(tmp_path):
    done, builds = _build(tmp_path, anonymous_fails=True)
    assert done.returncode == 0, done.stderr
    assert len(builds) == 2 and builds[1].startswith("DOCKER_CONFIG= ")
