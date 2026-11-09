"""A service the restart helper started is stopped when its test ends, and an orphan the harness finds is stopped after the command.

Measured on a run: the helper started `start.sh` in a process group of its own; a test that failed before `stop()` left
it running, owned by no one. After a morning of runs 130 such services were alive in the worker - about 4 GB - and the
worker's process was killed with SIGKILL in the middle of a run.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time

import pytest

from app.acceptance import stray_services
from app.stacks import pack_named


@pytest.mark.skipif(shutil.which("node") is None, reason="no Node here")
def test_a_service_the_test_never_stopped_ends_with_the_test(tmp_path):
    (tmp_path / "acceptance").mkdir()
    (tmp_path / "acceptance" / "service.cjs").write_text(pack_named("node-hono-native-api").files["acceptance/service.cjs"])
    (tmp_path / "start.sh").write_text('#!/bin/sh\ncd "$(dirname "$0")" && exec node server.cjs\n')
    (tmp_path / "server.cjs").write_text(
        "require('http').createServer((q, s) => s.end('ok')).listen(Number(process.env.PORT), process.env.HOST);\n")
    (tmp_path / "check.cjs").write_text(
        "const { startService } = require('./acceptance/service.cjs');\n"
        "(async () => { const s = await startService(); console.log(s.baseURL); })();\n")  # never stops it

    done = subprocess.run(["node", "check.cjs"], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    port = done.stdout.strip().rsplit(":", 1)[1]
    time.sleep(0.5)

    alive = subprocess.run(["sh", "-c", f"ps -eo args | grep -c '[n]ode server.cjs' || true"], capture_output=True, text=True)
    assert alive.stdout.strip() == "0", f"a service is still listening on {port}"


def _process(proc, pid: int, parent: int, environ: dict[str, str]) -> None:
    folder = proc / str(pid)
    folder.mkdir()
    (folder / "stat").write_text(f"{pid} (node src/main.ts) S {parent} {pid} {pid} 0")
    (folder / "environ").write_bytes(b"\0".join(f"{k}={v}".encode() for k, v in environ.items()) + b"\0")


def test_only_orphans_the_helper_started_in_this_workspace_are_stopped(tmp_path, monkeypatch):
    proc = tmp_path / "proc"
    proc.mkdir()
    workspace = tmp_path / "ws"
    (workspace / "notes").mkdir(parents=True)
    other = tmp_path / "other"
    other.mkdir()
    _process(proc, 101, 1, {"HARNESS_SERVICE_OF": str(workspace / "notes")})   # orphan of this run: stopped
    _process(proc, 102, 55, {"HARNESS_SERVICE_OF": str(workspace / "notes")})  # its test still runs it: kept
    _process(proc, 103, 1, {"HARNESS_SERVICE_OF": str(other)})                 # another workspace: kept
    _process(proc, 104, 1, {"PATH": "/usr/bin"})                               # not the helper's: kept
    killed = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append(pid))

    assert stray_services.stop_strays(workspace, proc) == 1
    assert killed == [101]


def test_every_sandbox_command_looks_for_strays():
    import inspect

    from app.tools import sandbox

    body = inspect.getsource(sandbox.SandboxExecutor.execute)
    assert "stop_strays(repo_root)" in body


def test_the_helper_marks_and_tracks_what_it_starts():
    helper = pack_named("node-http-api").files["acceptance/service.cjs"]
    assert "HARNESS_SERVICE_OF: PROJECT" in helper and "process.once('exit', stopAll)" in helper
