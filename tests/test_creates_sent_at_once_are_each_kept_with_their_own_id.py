"""Creates sent at the same moment are each kept, each with its own id: probed behind `CONCURRENT_WRITE_PROBE`.

Measured: in several benchmark families products lost writes made at the same moment - two records given one id, or
one overwriting another - which only an external quality test caught; the locked suite sends one write at a time.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from app.acceptance import concurrent_write_probe as cw
from app.acceptance import interface_contract as ic
from app.acceptance import junit
from app.agents.specialists import SpecialistOutput
from app.graph import acceptance_nodes, workflow
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
LINES = ["AC-1 POST /notes -> 201", "AC-2 GET /notes -> 200", "AC-3 GET /notes/{noteId} -> 200, 404",
         "AC-4 POST /auth/login -> 200", "AC-5 PUT /notes/{noteId} -> 200, 404"]


def _lines():
    return ic.parse(LINES)[0]


def test_the_create_line_is_asked_and_sign_in_and_routes_with_a_parameter_are_not():
    asked, unasked = cw.concurrent_write_checks(_lines())
    assert [(c.method, c.path) for c in asked] == [("POST", "/notes")]
    assert any(u.startswith("AC-4 POST /auth/login") for u in unasked)


def test_the_playwright_spec_sends_the_creates_at_once_and_reads_the_list_route():
    lines = _lines()
    asked, _ = cw.concurrent_write_checks(lines)
    spec = cw.playwright_concurrent_write_checks(asked, lines, [{"title": "milk"}])
    assert "Promise.all(Array.from({ length: c.at_once }" in spec
    case = json.loads(re.search(r"const c = (\{.*\});", spec).group(1))
    assert case == {"path": "/notes", "list": "/notes", "parameter": "noteId", "bodies": [{"title": "milk"}], "at_once": 16}
    assert "contract 1: AC-1 POST /notes -> 201 sent 16 at once" in spec
    assert f"const WRITES_AT_ONCE = {json.dumps(cw.MARKER)};" in spec
    # A body object is sent as the object it is; only raw text needs bytes.
    assert "data: body, headers" in spec


@pytest.mark.skipif(shutil.which("node") is None, reason="no node to read the spec")
def test_the_playwright_spec_is_javascript_node_can_read(tmp_path):
    lines = ic.parse([*LINES, "AC-6 POST /auth/signup -> 201"])[0]
    asked, _ = cw.concurrent_write_checks(lines)
    spec = cw.playwright_concurrent_write_checks(asked, lines, [{"title": "milk"}, {"username": "a", "password": "b"}])
    assert "async function signedIn(request)" in spec  # the sign-in the other body probes use
    (tmp_path / "contract.spec.mjs").write_text(spec)
    done = subprocess.run(["node", "--check", str(tmp_path / "contract.spec.mjs")], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


class _Store(BaseHTTPRequestHandler):
    """A store giving each record the next id; `racy` reads the count, waits, then writes, as an unserialised store does."""

    racy = False
    records: dict = {}
    lock = threading.Lock()

    def log_message(self, *args):  # noqa: D401 - quiet
        pass

    def _answer(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        self._answer(200, [{"id": k, **v} for k, v in sorted(type(self).records.items())])

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
        cls = type(self)
        if cls.racy:
            new = len(cls.records) + 1
            # A window wide enough that the probe's creates, released together, all read the count before any
            # writes even on a loaded machine: at 0.05 s a loaded suite once let them miss each other.
            time.sleep(0.3)
            cls.records[new] = body
        else:
            with cls.lock:
                new = len(cls.records) + 1
                cls.records[new] = body
        self._answer(201, {"id": new, **body})


def _run_the_pytest_module(tmp_path, racy):
    handler = type("Store", (_Store,), {"racy": racy, "records": {}, "lock": threading.Lock()})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        lines = _lines()
        asked, _ = cw.concurrent_write_checks(lines)
        (tmp_path / "test_probe.py").write_text(cw.pytest_concurrent_write_checks(asked, lines, [{"title": "milk"}]))
        (tmp_path / "conftest.py").write_text(
            f"import pytest\n\n@pytest.fixture\ndef base_url():\n    return 'http://127.0.0.1:{server.server_port}'\n")
        env = {**os.environ, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
        subprocess.run([sys.executable, "-m", "pytest", "test_probe.py", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                        "--junitxml=report.xml"], cwd=tmp_path, capture_output=True, text=True, env=env, timeout=120)
        return junit.read(tmp_path / "report.xml")
    finally:
        server.shutdown()


def test_the_pytest_module_finds_an_unserialised_store_and_passes_a_serialised_one(tmp_path):
    (tmp_path / "racy").mkdir()
    (tmp_path / "safe").mkdir()
    racy = _run_the_pytest_module(tmp_path / "racy", racy=True)
    assert racy.found and [t.outcome for t in racy.tests] == ["failed"]
    found = cw.what_the_test_found(racy.tests[0])
    assert found["sent"] == 16 and found["made"] == 16 and found["same_id"] and found["listed"] < 16
    safe = _run_the_pytest_module(tmp_path / "safe", racy=False)
    assert safe.found and [t.outcome for t in safe.tests] == ["passed"]


def test_the_defect_says_what_was_sent_what_came_back_and_what_to_do():
    check = cw.concurrent_write_checks(_lines())[0][0]
    found = {"sent": 10, "body": {"title": "milk"}, "statuses": [201] * 9 + [500], "same_id": ["3"], "made": 9,
             "listed": 7, "list": "/notes"}
    text = cw.concurrent_write_description([(check, found)])
    assert text.startswith(cw.CONCURRENT_WRITES_LOST)
    assert '`POST /notes` was sent 10 creates at once, each with the body `{"title": "milk"}`' in text
    assert "201 x9, 500 x1" in text and "(`3`)" in text and "`GET /notes` listed 7 of the 9 created" in text
    assert cw.SAID in text.lower() and "serialise the store's writes" in text
    assert "AC-" not in text and not BANNED.search(text)


def test_a_failed_test_s_findings_are_read_back_from_its_message():
    message = 'Error: WRITES AT ONCE: {"sent": 10, "statuses": [500], "same_id": [], "made": 0, "listed": null}\n  at x'
    assert cw.what_the_test_found(SimpleNamespace(message=message))["statuses"] == [500]
    assert cw.what_the_test_found(SimpleNamespace(message="Timed out")) is None


def _project(tmp_path, monkeypatch):
    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(probe_runner="playwright"), {"project": "app"}))
    (tmp_path / "app").mkdir()
    ic.record_at_lock(tmp_path, LINES)


def _reporting(failed: bool):
    asked = []

    def report(project, name, probe, web, run, compiled_by="checks", bodies=None):
        asked.append(probe[compiled_by](web))
        found = json.dumps({"sent": 10, "body": {}, "statuses": [201] * 10, "same_id": ["1"], "made": 10, "listed": 1,
                            "list": "/notes"})
        test = SimpleNamespace(name="[AC-1] contract 1: AC-1 POST /notes -> 201 sent 10 at once",
                               outcome="failed" if failed else "passed",
                               message=f"Error: {cw.MARKER} {found}" if failed else "")
        return SimpleNamespace(found=True, tests=[test])
    return report, asked


def test_off_it_is_not_asked_and_on_it_is_raised_and_settled(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    report, asked = _reporting(failed=True)
    monkeypatch.setattr(ic, "_the_probe_s_report", report)
    monkeypatch.setenv("CONCURRENT_WRITE_PROBE", "off")
    assert cw.concurrent_write_errors(tmp_path) is None and asked == []

    monkeypatch.setenv("CONCURRENT_WRITE_PROBE", "on")
    errors = cw.concurrent_write_errors(tmp_path, runner=lambda *a: {})
    assert [(c.method, c.path) for c, _ in errors] == [("POST", "/notes")] and "Promise.all" in asked[0]
    text = cw.concurrent_write_description(errors)
    assert ic.still_raised(tmp_path, text, runner=lambda *a: {}) is True
    monkeypatch.setattr(ic, "_the_probe_s_report", _reporting(failed=False)[0])
    assert ic.still_raised(tmp_path, text, runner=lambda *a: {}) is False
    monkeypatch.setenv("CONCURRENT_WRITE_PROBE", "off")
    assert ic.still_raised(tmp_path, text) is False  # switched off: nothing can settle it, so it does not stay open


def test_a_green_round_raises_it_behind_its_switch(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    monkeypatch.setattr(acceptance_nodes.suite, "is_locked", lambda root: True)
    monkeypatch.setattr(ic, "server_errors", lambda root, runner=None: [])
    monkeypatch.setattr(ic, "bad_body_errors", lambda root, runner=None: [])
    monkeypatch.setattr(ic, "emptied_field_errors", lambda root, runner=None: [])
    monkeypatch.setattr(ic, "_the_probe_s_report", _reporting(failed=True)[0])
    monkeypatch.setenv("CONTRACT_SERVER_ERRORS_AT_A_ROUND", "on")
    monkeypatch.setenv("WRONG_SHAPE_BODY_PROBE", "off")
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}
    green = SpecialistOutput(changed_files=[], defects=[], decisions=[])
    milestone = SimpleNamespace(delegated_tasks=[], milestone_scope=[])

    monkeypatch.setenv("CONCURRENT_WRITE_PROBE", "off")
    assert workflow._with_the_contract_s_server_errors(state, green, milestone).defects == []
    monkeypatch.setenv("CONCURRENT_WRITE_PROBE", "on")
    raised = workflow._with_the_contract_s_server_errors(state, green, milestone).defects
    assert len(raised) == 1 and raised[0].description.startswith(cw.CONCURRENT_WRITES_LOST)
    assert "16 `POST /notes` requests at the same moment" in raised[0].reproduction_steps
    assert not BANNED.search(" ".join([raised[0].description, raised[0].reproduction_steps,
                                       raised[0].expected_behavior, raised[0].actual_behavior]))


def test_what_it_could_not_ask_is_a_release_gap(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    monkeypatch.setenv("CONCURRENT_WRITE_PROBE", "on")

    def skipped(project, name, probe, web, run, compiled_by="checks", bodies=None):
        return SimpleNamespace(found=True, tests=[SimpleNamespace(name="contract 1: x", outcome="skipped", message="")])

    monkeypatch.setattr(ic, "_the_probe_s_report", skipped)
    assert cw.concurrent_write_errors(tmp_path, runner=lambda *a: {}) == []
    gaps = cw.what_it_did_not_ask(tmp_path)
    assert gaps and "were not sent 16 creates at once" in gaps[0] and "AC-1 POST /notes" in gaps[0]
    assert not BANNED.search(gaps[0])
    monkeypatch.setenv("CONCURRENT_WRITE_PROBE", "off")
    assert cw.what_it_did_not_ask(tmp_path) == []
