"""`ready` for a pinned run asks the server the run will use: measured, a busy server held back a run pinned to another.

The script itself runs, in its own process, against real local HTTP servers; only the store's reading is stood in for.
"""
from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "loop" / "model_ready.py"
LOOP = ROOT / "scripts" / "loop" / "loop.sh"


def _server(model: str, *, hang: float = 0.0, key: str = ""):
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _allowed(self):
            seen.append(self.headers.get("Authorization") or "")
            return not key or self.headers.get("Authorization") == f"Bearer {key}"

        def do_GET(self):
            if self.path.endswith("/models"):
                return self._send(200 if self._allowed() else 401, {"data": [{"id": model}]})
            return self._send(404, {})

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if hang:
                time.sleep(hang)
            return self._send(200, {"choices": [{"message": {"content": "ready"}}]})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/v1", seen


def _run(global_url: str, *args: str):
    env = {
        **os.environ, "PYTHONPATH": str(ROOT / "src"), "OPENAI_BASE_URL": global_url, "OPENAI_MODEL": "global-model",
        "LLM_PROVIDER": "local", "ENV": "development", "ALLOW_COMMAND_EXECUTION": "true",
        "SANDBOX_EXECUTION_MODE": "in-container", "JUDGEMENT_MODEL": "", "OPENAI_API_KEY": "the-global-key",
        "DATABASE_URL": "postgresql://nobody@127.0.0.1:1/none",
    }
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=120, check=False)


def test_a_pinned_run_is_not_held_back_by_the_global_server_being_gone():
    server, url, _ = _server("pinned-model")
    try:
        done = _run("http://127.0.0.1:1/v1", f"pin_url={url}", "pin_model=pinned-model")
    finally:
        server.shutdown()
    assert done.returncode == 0, done.stdout + done.stderr
    assert "ALL READY" in done.stdout
    assert "127.0.0.1:1/v1" not in done.stdout


def test_an_unreachable_target_still_blocks_with_the_global_server_answering():
    server, url, _ = _server("global-model")
    try:
        done = _run(url, "pin_url=http://127.0.0.1:1/v1", "pin_model=global-model")
    finally:
        server.shutdown()
    assert done.returncode == 1
    assert "NOTREADY pinned" in done.stdout and "NOT ALL READY" in done.stdout


def test_a_target_that_does_not_serve_the_model_blocks():
    server, url, _ = _server("another-model")
    try:
        done = _run("http://127.0.0.1:1/v1", f"pin_url={url}", "pin_model=pinned-model")
    finally:
        server.shutdown()
    assert done.returncode == 1 and "NOTREADY pinned" in done.stdout


def test_with_no_target_the_global_server_is_the_one_asked():
    server, url, seen = _server("global-model")
    try:
        done = _run(url)
    finally:
        server.shutdown()
    assert done.returncode == 0, done.stdout
    assert "READY default" in done.stdout and seen
    gone = _run("http://127.0.0.1:1/v1")
    assert gone.returncode == 1 and "NOTREADY default" in gone.stdout


def test_the_global_server_s_key_is_not_sent_to_the_target():
    server, url, seen = _server("pinned-model")
    try:
        done = _run("http://127.0.0.1:1/v1", f"pin_url={url}", "pin_model=pinned-model")
    finally:
        server.shutdown()
    assert done.returncode == 0, done.stdout + done.stderr
    assert seen and "Bearer the-global-key" not in seen
    assert "the-global-key" not in done.stdout + done.stderr


def _in_process(monkeypatch, capsys, argv, *, live: list[str], keys: dict[str, str] | None = None):
    """The script run here, with what a real worker has in its store and its stored endpoint keys."""
    from app.server import run_store, runtime_settings

    class Store:
        def list_all(self, **_):
            return [type("R", (), {"run_id": run, "status": "running"}) for run in live]

        def model_states(self, runs):
            return {run: (True, {"OPENAI_BASE_URL": base}) for run, base in zip(runs, monkeypatch.busy_at)}

    monkeypatch.setattr(run_store.RunStore, "shared", classmethod(lambda _c: Store()))
    monkeypatch.setattr(runtime_settings, "endpoint_keys", lambda: keys or {})
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("OPENAI_MODEL", "global-model")
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "in-container")
    monkeypatch.setenv("JUDGEMENT_MODEL", "")
    monkeypatch.setattr(sys, "argv", ["model_ready.py", *argv])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    return stopped.value.code, capsys.readouterr().out


def _time_out_at_once(monkeypatch):
    """urlopen as a busy server makes it for the one small request: the listing answers, the completion times out."""
    import urllib.request

    real = urllib.request.urlopen

    def urlopen(request, timeout=None):
        if str(getattr(request, "full_url", request)).endswith("/chat/completions"):
            raise TimeoutError("timed out")
        return real(request, timeout=timeout)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


def test_a_timeout_on_a_server_busy_on_a_live_run_of_ours_is_reported_busy_and_still_blocks(monkeypatch, capsys):
    server, url, _ = _server("pinned-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:1/v1")
    monkeypatch.busy_at = [url]
    _time_out_at_once(monkeypatch)
    try:
        code, out = _in_process(monkeypatch, capsys, [f"pin_url={url}", "pin_model=pinned-model"], live=["run-a"])
    finally:
        server.shutdown()
    assert code == 1
    assert "BUSY" in out and "run-a" in out and "NOT ALL READY" in out


def test_a_timeout_with_no_live_run_of_ours_there_does_not_say_busy(monkeypatch, capsys):
    server, url, _ = _server("pinned-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:1/v1")
    monkeypatch.busy_at = ["http://127.0.0.1:2/v1"]
    _time_out_at_once(monkeypatch)
    try:
        code, out = _in_process(monkeypatch, capsys, [f"pin_url={url}", "pin_model=pinned-model"], live=["run-a"])
    finally:
        server.shutdown()
    assert code == 1
    assert "BUSY" not in out and "does not answer a request" in out


def test_the_target_gets_its_own_endpoint_key_and_the_key_is_never_printed(monkeypatch, capsys):
    from app.server import runtime_settings

    server, url, seen = _server("pinned-model", key="the-target-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:1/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "the-global-key")
    monkeypatch.busy_at = []
    wanted = runtime_settings.endpoint_id("local", url)
    try:
        code, out = _in_process(monkeypatch, capsys, [f"pin_url={url}", "pin_model=pinned-model"], live=[], keys={wanted: "the-target-key"})
    finally:
        server.shutdown()
    assert code == 0, out
    assert "Bearer the-target-key" in seen
    assert "the-target-key" not in out


def _start_block() -> str:
    text = LOOP.read_text()
    return text[text.index("\nstart)"):text.index("\nbench)")]


def _run_the_start_block(tmp_path, **env):
    """The script's own readiness lines, run by bash with `docker` a stub that records what the worker is asked."""
    calls = tmp_path / "calls"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(f'#!/bin/sh\necho "$@" >> {calls}\ncat >/dev/null\necho "NOT ALL READY"\n')
    (bin_dir / "docker").chmod(0o755)
    brief = tmp_path / "brief.md"
    brief.write_text("x")
    done = subprocess.run(["bash", str(LOOP), "start", str(brief)], capture_output=True, text=True, check=False,
                          env={**{k: v for k, v in os.environ.items() if not k.startswith("PIN_")},
                               "PATH": f"{bin_dir}:{os.environ['PATH']}", **env})
    return done, calls.read_text() if calls.exists() else ""


def test_start_passes_the_pin_to_the_check_and_a_refusal_stops_it(tmp_path):
    done, calls = _run_the_start_block(tmp_path, PIN_URL="http://x:8888/v1", PIN_MODEL_NAME="m")
    assert done.returncode == 1
    assert "pin_url=http://x:8888/v1" in calls and "pin_model=m" in calls
    assert "not starting" in done.stderr


def test_start_with_no_pin_asks_as_before(tmp_path):
    done, calls = _run_the_start_block(tmp_path)
    assert done.returncode == 1
    assert "exec -T worker python -" in calls
    assert "pin_url" not in calls and "pin_model" not in calls


def test_a_server_given_without_pin_model_pins_the_run():
    block = _start_block()
    assert 'PIN_MODEL="${PIN_MODEL:-1}"' in block
