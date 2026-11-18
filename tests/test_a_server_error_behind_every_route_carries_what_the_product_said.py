"""A server error behind every route reaches the fixer with what the product said, not the status alone.

Measured on a Rust run: every route answered 500 "Missing request extension: Extension of type `AppState` was not
found" - the cause, in the product's own words - and three sprint attempts were shown only "Expected: 201, Received:
500". The contract's probe keeps the start of each failed answer's body, and the one-cause defect quotes one.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

from app.acceptance import interface_contract as ic
from app.acceptance import junit
from app.graph import acceptance_nodes

SAID = "Missing request extension: Extension of type `AppState` was not found."


class _Broken(BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D401 - quiet
        pass

    def do_POST(self):  # noqa: N802
        raw = SAID.encode()
        self.send_response(500)
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def test_the_probe_s_failure_carries_the_start_of_the_answer(tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Broken)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        (check,), _ = ic.parse(["AC-1 POST /notes -> 201"])
        (tmp_path / "test_probe.py").write_text(ic.pytest_checks([check]))
        (tmp_path / "conftest.py").write_text(
            f"import pytest\n\n@pytest.fixture\ndef base_url():\n    return 'http://127.0.0.1:{server.server_port}'\n")
        env = {**os.environ, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
        subprocess.run([sys.executable, "-m", "pytest", "test_probe.py", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                        "--junitxml=report.xml"], cwd=tmp_path, capture_output=True, text=True, env=env, timeout=120)
        (test,) = junit.read(tmp_path / "report.xml").tests
    finally:
        server.shutdown()

    assert test.outcome == "failed" and ic.IT_SAID + "Missing request extension" in test.message


def test_the_one_cause_defect_quotes_what_one_request_was_answered(tmp_path, monkeypatch):
    def the_probe(root, **kwargs):  # the probe starts the product: the edge
        ic._SAID[str(root)] = f"`POST /notes` answered 500: {SAID}"
        return []

    monkeypatch.setattr(ic, "server_errors", the_probe)
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}

    assert SAID in acceptance_nodes._what_one_of_them_said(state, "500")
    assert acceptance_nodes._what_one_of_them_said(state, "401") == ""
