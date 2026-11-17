"""A write sent valid JSON that is not an object must not make the server fail: probed behind `WRONG_SHAPE_BODY_PROBE`.

Measured: products answered 500 to a JSON string sent as a write's body; the bad-body probe sends bytes no parser can
read, so it never reached the handler that read fields off a string.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from app.acceptance import interface_contract as ic
from app.acceptance import junit
from app.acceptance import wrong_shape_body_probe as ws
from app.agents.specialists import SpecialistOutput
from app.graph import acceptance_nodes, workflow
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
LINES = ["AC-1 POST /notes -> 201", "AC-2 PUT /notes/{id} -> 200", "AC-3 GET /notes -> 200"]


def _asked():
    return ic.bad_body_checks(ic.parse(LINES)[0], [{"title": "milk"}])[0]


def test_the_playwright_spec_sends_each_shape_as_the_bytes_it_names():
    spec = ws.playwright_wrong_shape_checks(_asked())
    assert spec.count('data: Buffer.from("\\"text\\""), ') == 2 and spec.count('data: Buffer.from("[]"), ') == 2
    assert f"Buffer.from({ic._js(ic.A_BODY_NOTHING_CAN_PARSE)})" not in spec  # the bad-body probe's bytes, not these
    titles = re.findall(r'test\("(.*?)", async', spec)
    assert [t.split(":")[0] for t in titles] == ["[AC-1] contract 1", "[AC-1] contract 2", "[AC-2] contract 3", "[AC-2] contract 4"]
    assert "expect(answer.status()).toBeLessThan(500);" in spec


@pytest.mark.skipif(shutil.which("node") is None, reason="no node to read the spec")
def test_the_playwright_spec_is_javascript_node_can_read(tmp_path):
    (tmp_path / "contract.spec.mjs").write_text(ws.playwright_wrong_shape_checks(_asked()))
    done = subprocess.run(["node", "--check", str(tmp_path / "contract.spec.mjs")], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


class _Notes(BaseHTTPRequestHandler):
    """A write route that reads a field off whatever JSON it parsed; `guarded` refuses a body that is not an object."""

    guarded = False

    def log_message(self, *args):
        pass

    def _answer(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _write(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)))
        except ValueError:
            return self._answer(400, {"error": "unparsable"})
        if type(self).guarded and not isinstance(body, dict):
            return self._answer(422, {"error": "not an object"})
        try:
            return self._answer(201, {"id": 1, "title": body.get("title")})
        except Exception:  # noqa: BLE001 - the crash the probe is for
            return self._answer(500, {"error": "crashed"})

    do_POST = do_PUT = _write  # noqa: N815


def _run_the_pytest_module(tmp_path, guarded):
    server = ThreadingHTTPServer(("127.0.0.1", 0), type("Notes", (_Notes,), {"guarded": guarded}))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        (tmp_path / "test_probe.py").write_text(ws.pytest_wrong_shape_checks(_asked(), [{"title": "milk"}]))
        (tmp_path / "conftest.py").write_text(
            f"import pytest\n\n@pytest.fixture\ndef base_url():\n    return 'http://127.0.0.1:{server.server_port}'\n")
        env = {**os.environ, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
        subprocess.run([sys.executable, "-m", "pytest", "test_probe.py", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                        "--junitxml=report.xml"], cwd=tmp_path, capture_output=True, text=True, env=env, timeout=120)
        return junit.read(tmp_path / "report.xml")
    finally:
        server.shutdown()


def test_the_pytest_module_sends_the_bytes_and_finds_the_crash(tmp_path):
    (tmp_path / "crashes").mkdir()
    (tmp_path / "refuses").mkdir()
    crashed = _run_the_pytest_module(tmp_path / "crashes", guarded=False)
    assert crashed.found and [t.outcome for t in crashed.tests] == ["failed"] * 4
    assert all(ic._a_server_error(t) == 500 for t in crashed.tests)
    refused = _run_the_pytest_module(tmp_path / "refuses", guarded=True)
    assert refused.found and [t.outcome for t in refused.tests] == ["passed"] * 4


def _project(tmp_path, monkeypatch):
    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(probe_runner="playwright"), {"project": "app"}))
    (tmp_path / "app").mkdir()
    ic.record_at_lock(tmp_path, LINES)


def _reporting(failing: set[int]):
    asked = []

    def report(project, name, probe, web, run, compiled_by="checks", bodies=None):
        asked.append(probe[compiled_by](web))
        return SimpleNamespace(found=True, tests=[
            SimpleNamespace(name=f"contract {n}: x", outcome="failed" if n in failing else "passed",
                            message="Expected: < 500\nReceived: 500" if n in failing else "")
            for n in range(1, 2 * len(web) + 1)])
    return report, asked


def test_off_it_is_not_asked_and_on_each_5xx_is_named_with_its_body(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    report, asked = _reporting({1})
    monkeypatch.setattr(ic, "_the_probe_s_report", report)
    monkeypatch.setenv("WRONG_SHAPE_BODY_PROBE", "off")
    assert ws.wrong_shape_errors(tmp_path) is None and asked == []

    monkeypatch.setenv("WRONG_SHAPE_BODY_PROBE", "on")
    errors = ws.wrong_shape_errors(tmp_path, runner=lambda *a: {})
    assert [(c.method, c.path, s, b) for c, s, b in errors] == [("POST", "/notes", 500, '"text"')]
    coverage = json.loads((tmp_path / ".harness" / "contract-probe.json").read_text())["wrong_shape_body"]
    assert coverage["asked"] == coverage["probed"] == 2  # each line once, not once a shape


def test_the_defect_says_a_json_body_that_is_not_an_object_and_is_settled_by_the_probe(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    monkeypatch.setenv("WRONG_SHAPE_BODY_PROBE", "on")
    check = _asked()[0]
    text = ic.server_error_description([], [], [(check, 500, '"text"'), (check, 502, "[]")])
    assert text.startswith(ic.SERVER_FAILED)
    assert "`POST /notes` sent a JSON body that is not an object (`\"text\"` answered 500, `[]` answered 502)" in text
    assert ws.SAID in text and "JSON that is not an object (a string, an array)" in text
    assert "AC-" not in text and not BANNED.search(text)
    assert ws.SAID not in ic.server_error_description([(check, 500)])  # the audit reads it as this probe firing

    monkeypatch.setattr(ic, "_the_probe_s_report", _reporting({1})[0])
    assert ic.still_raised(tmp_path, text, runner=lambda *a: {}) is True
    monkeypatch.setattr(ic, "_the_probe_s_report", _reporting(set())[0])
    assert ic.still_raised(tmp_path, text, runner=lambda *a: {}) is False
    monkeypatch.setenv("WRONG_SHAPE_BODY_PROBE", "off")
    assert ic.still_raised(tmp_path, text) is False


def test_a_green_round_raises_it_behind_its_switch(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    monkeypatch.setattr(acceptance_nodes.suite, "is_locked", lambda root: True)
    monkeypatch.setattr(ic, "server_errors", lambda root, runner=None: [])
    monkeypatch.setattr(ic, "bad_body_errors", lambda root, runner=None: [])
    monkeypatch.setattr(ic, "emptied_field_errors", lambda root, runner=None: [])
    monkeypatch.setattr(ic, "_the_probe_s_report", _reporting({2})[0])
    monkeypatch.setenv("CONTRACT_SERVER_ERRORS_AT_A_ROUND", "on")
    monkeypatch.setenv("CONCURRENT_WRITE_PROBE", "off")
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}
    green = SpecialistOutput(changed_files=[], defects=[], decisions=[])
    milestone = SimpleNamespace(delegated_tasks=[], milestone_scope=[])

    monkeypatch.setenv("WRONG_SHAPE_BODY_PROBE", "off")
    assert workflow._with_the_contract_s_server_errors(state, green, milestone).defects == []
    monkeypatch.setenv("WRONG_SHAPE_BODY_PROBE", "on")
    raised = workflow._with_the_contract_s_server_errors(state, green, milestone).defects
    assert len(raised) == 1 and "`POST /notes` sent a JSON body that is not an object (`[]` answered 500)" in raised[0].description
    assert "the body `[]`" in raised[0].reproduction_steps and "answered 500 to `[]`" in raised[0].actual_behavior
    # Settled by its own probe, run again: still failing, then fixed.
    assert workflow._settled_by_its_own_probe(tmp_path, raised[0]) is False
    monkeypatch.setattr(ic, "_the_probe_s_report", _reporting(set())[0])
    assert workflow._settled_by_its_own_probe(tmp_path, raised[0]) is True
