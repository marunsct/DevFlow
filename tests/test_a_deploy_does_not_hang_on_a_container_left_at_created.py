"""The deploy's compose call starts a container left at Created, and brings up again a service not on its new image.

Measured: compose created the new app container and waited on it for eight minutes with both live runs paused;
`docker start` on it returned at once, but the worker was never replaced and the deploy did not land.
"""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "scripts" / "loop" / "compose_up.sh"
LOOP = ROOT / "scripts" / "loop" / "loop.sh"

# A docker whose `compose up` hangs until the app container is started, and replaces the worker only when it is
# brought up on its own. State lives in files under $STATE.
FAKE = textwrap.dedent("""\
    #!/usr/bin/env bash
    echo "$*" >> "$STATE/calls"
    case "$1 $2" in
      "compose up")
        if [ -n "${HANG:-}" ] && [ "$*" != "compose up -d --no-deps worker" ]; then
          echo created > "$STATE/app.state"
          while [ "$(cat "$STATE/app.state")" != running ]; do sleep 0.2; done
        else
          echo running > "$STATE/app.state"
        fi
        case "$*" in *--no-deps\\ worker*) echo new > "$STATE/worker.image" ;; esac
        exit 0 ;;
      "compose ps") for s in "$@"; do :; done; echo "c-$s" ;;
      "start c-app") echo running > "$STATE/app.state" ;;
      "inspect -f")
        if [ "$3" = "{{.State.Status}}" ]; then cat "$STATE/${4#c-}.state" 2>/dev/null || echo running
        else cat "$STATE/${4#c-}.image" 2>/dev/null || echo new; fi ;;
      "image inspect") echo new ;;
    esac
    exit 0
    """)


def _run(tmp_path, worker_image="old", **env):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(FAKE)
    (bin_dir / "docker").chmod(0o755)
    (tmp_path / "worker.image").write_text(worker_image)
    run_env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "STATE": str(tmp_path),
               "UNSTICK_AFTER": "1", "COMPOSE_UP_STEP": "1", "COMPOSE_UP_MOST": "20", **env}
    return subprocess.run(["bash", str(HELPER), "app", "worker"], env=run_env, capture_output=True, text=True, timeout=60)


def test_a_container_left_at_created_is_started_and_the_worker_is_replaced(tmp_path):
    done = _run(tmp_path, HANG="1")
    assert done.returncode == 0, done.stderr
    calls = (tmp_path / "calls").read_text()
    assert "start c-app" in calls
    assert "compose up -d --no-deps worker" in calls
    assert (tmp_path / "worker.image").read_text().strip() == "new"


def test_a_compose_that_does_not_hang_is_left_alone(tmp_path):
    done = _run(tmp_path, worker_image="new")
    assert done.returncode == 0
    calls = (tmp_path / "calls").read_text()
    assert "start " not in calls and "--no-deps" not in calls


def test_the_deploy_uses_it():
    text = LOOP.read_text(encoding="utf-8")
    body = text[text.index("\ndeploy)"):text.index("\nbuild)")]
    assert "compose_up.sh\" app worker" in body or "compose_up.sh\" app worker 9>&-" in body
    assert "\n  docker compose up -d app worker\n" not in body


def test_no_docker_call_inherits_a_lock():
    # A credential helper Docker left hanging kept the build lock, and every later build refused to start.
    text = LOOP.read_text(encoding="utf-8")
    build = text[text.index("\nbuild)"):]
    build = build[:build.index("\n  ;;")]
    assert '> "$STATE/build.log" 2>&1 8>&-' in build
    deploy = text[text.index("\ndeploy)"):text.index("\nbuild)")]
    assert 'compose_up.sh" app worker 9>&-' in deploy
