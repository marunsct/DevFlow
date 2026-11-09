"""A build of a commit whose images are already there builds nothing, and `ship-live` can ship a named commit.

Measured: a deploy that did not land was retried; its build of the same commit, whose images were already built,
asked the registry, hung on Docker's credential helper waiting on a locked key store, and failed after 181 s.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _docker(bin_dir: Path, log: Path, commit: str) -> None:
    path = bin_dir / "docker"
    path.write_text("#!/bin/sh\n"
                    f"echo \"docker $*\" >> {log}\n"
                    f"case \"$1 $2\" in \"image inspect\") echo HARNESS_COMMIT={commit} ;; esac\n"
                    "exit 0\n")
    path.chmod(0o755)


def _build(tmp_path, commit: str, **env):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    log.write_text("")
    _docker(bin_dir, log, commit)
    done = subprocess.run(["bash", str(ROOT / "scripts" / "loop" / "loop.sh"), "build"], cwd=ROOT, capture_output=True,
                          text=True, timeout=120, env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", **env})
    return done, log.read_text()


def _head() -> str:
    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def test_images_already_built_from_the_commit_build_nothing(tmp_path):
    done, calls = _build(tmp_path, _head())
    assert done.returncode == 0, done.stderr
    assert "images already built from" in done.stdout
    assert " build " not in calls


def test_rebuild_builds_anyway(tmp_path):
    _done, calls = _build(tmp_path, _head(), REBUILD="1")
    assert " build --progress=plain" in calls


def test_ship_live_builds_and_deploys_the_named_commit():
    text = (ROOT / "scripts" / "loop" / "ship_live.sh").read_text(encoding="utf-8")
    assert '"$L" build ${SHIP_COMMIT:-}' in text
    assert '"$L" deploy ${SHIP_COMMIT:-}' in text
