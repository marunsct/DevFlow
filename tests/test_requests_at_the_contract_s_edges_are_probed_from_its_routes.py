"""Requests at the edges of the interface contract are compiled from its routes and example bodies, and probed.

Deep review 2026-11-18, item B1: the hidden quality tests most often lose on requests no locked test sends - a field
missing, null, empty, only spaces, of the wrong type, very long; an id that is not a number or already deleted; a
delete sent twice - and three hand-built probes covered part of it. The generated probe holds the product only to
narrow invariants: never a 5xx, a refused write stores and changes nothing, a create reads back as it was sent.
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

from app.acceptance import edge_probe as ep
from app.acceptance import interface_contract as ic
from app.acceptance import junit
from app.agents.specialists import SpecialistOutput
from app.graph import acceptance_nodes, workflow
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
LINES = ["AC-1 POST /notes -> 201", "AC-2 GET /notes -> 200", "AC-3 GET /notes/{noteId} -> 200, 404",
         "AC-4 POST /auth/login -> 200", "AC-5 PUT /notes/{noteId} -> 200, 404", "AC-6 DELETE /notes/{noteId} -> 204, 404"]
BODIES = [{"title": "milk"}, {"username": "a", "password": "b"}]


def _ids():
    return [case["id"] for case in ep.edge_cases(ic.parse(LINES)[0], BODIES)]


def test_each_field_of_each_write_and_each_id_of_each_route_is_asked_and_sign_in_is_not():
    ids = _ids()

    for form in ("missing", "null", "empty", "only spaces", "a number (12345)", "5000 characters long",
                 "in several scripts"):
        assert any(i.endswith(f"POST /notes with `title` {form}") for i in ids), form
        assert any(i.endswith(f"PUT /notes/{{noteId}} with `title` {form}") for i in ids), form
    for route in ("GET /notes/{noteId}", "DELETE /notes/{noteId}"):
        for value in ("not-a-number", "-1", "99999999999999999999"):
            assert any(i.endswith(f"{route} at id `{value}`") for i in ids), (route, value)
    assert any(i.endswith("DELETE /notes/{noteId} at an id already deleted") for i in ids)
    assert any(i.endswith("POST /notes with its example body") for i in ids)
    assert not any("/auth/login" in i or "password" in i for i in ids)


class _Notes(BaseHTTPRequestHandler):
    """A notes service; `broken` fails at each edge the probe asks, the other keeps every invariant."""

    broken = False
    records: dict = {}

    def log_message(self, *args):  # noqa: D401 - quiet
        pass

    def _answer(self, status, body=None):
        raw = json.dumps(body).encode() if body is not None else b""
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        raw = self.rfile.read(int(self.headers.get("content-length") or 0))
        try:
            return json.loads(raw or b"null")
        except ValueError:
            return None

    def _id(self):
        part = self.path.rstrip("/").split("/")[-1]
        if not part.isdigit():
            return None if not type(self).broken else int(part)  # broken: int() of "not-a-number" raises -> 500
        return int(part)

    def _valid(self, body):
        title = body.get("title") if isinstance(body, dict) else None
        return isinstance(title, str) and title.strip() != ""

    def handle_one_request(self):  # an exception answers 500, as a framework does
        try:
            super().handle_one_request()
        except Exception:  # noqa: BLE001
            self._answer(500, {"error": "boom"})

    def do_GET(self):  # noqa: N802
        records = type(self).records
        if self.path.rstrip("/") == "/notes":
            return self._answer(200, [{"id": k, **v} for k, v in sorted(records.items())])
        found = self._id()
        if found not in records:
            return self._answer(404, {"error": "no such note"})
        return self._answer(200, {"id": found, **records[found]})

    def do_POST(self):  # noqa: N802
        cls, body = type(self), self._body()
        if cls.broken:
            if isinstance(body, dict) and isinstance(body.get("title"), str) and len(body["title"]) > 1000:
                raise ValueError("too long for the column")
            new = len(cls.records) + 1
            cls.records[new] = {"title": str((body or {}).get("title"))[:100]}  # stored before it is checked
            if not self._valid(body):
                return self._answer(400, {"error": "title"})
            return self._answer(201, {"id": new, **cls.records[new]})
        if not self._valid(body):
            return self._answer(400, {"error": "title"})
        new = len(cls.records) + 1
        cls.records[new] = {"title": body["title"]}
        return self._answer(201, {"id": new, **cls.records[new]})

    def do_PUT(self):  # noqa: N802
        cls, body, found = type(self), self._body(), self._id()
        if found not in cls.records:
            return self._answer(404, {"error": "no such note"})
        if cls.broken:
            cls.records[found] = {"title": (body or {}).get("title") if isinstance(body, dict) else None}
        if not self._valid(body):
            return self._answer(400, {"error": "title"})
        cls.records[found] = {"title": body["title"]}
        return self._answer(200, {"id": found, **cls.records[found]})

    def do_DELETE(self):  # noqa: N802
        cls, found = type(self), self._id()
        if found not in cls.records:
            if cls.broken:
                raise KeyError(found)
            return self._answer(404, {"error": "no such note"})
        del cls.records[found]
        return self._answer(204)


def _run_the_pytest_module(tmp_path, broken):
    handler = type("Notes", (_Notes,), {"broken": broken, "records": {}})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        lines = ic.parse(LINES)[0]
        cases = ep.edge_cases(lines, BODIES)
        (tmp_path / "test_probe.py").write_text(ep.pytest_edge_checks(cases, None))
        (tmp_path / "conftest.py").write_text(
            f"import pytest\n\n@pytest.fixture\ndef base_url():\n    return 'http://127.0.0.1:{server.server_port}'\n")
        env = {**os.environ, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
        subprocess.run([sys.executable, "-m", "pytest", "test_probe.py", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                        "--junitxml=report.xml"], cwd=tmp_path, capture_output=True, text=True, env=env, timeout=300)
        report = junit.read(tmp_path / "report.xml")
        return report, [(case, found) for test in report.tests if (case := ep._the_case_of(test, cases))
                        and (found := ep.what_the_test_found(test)) is not None]
    finally:
        server.shutdown()


def test_a_product_failing_at_each_edge_is_found_and_one_keeping_every_invariant_passes(tmp_path):
    (tmp_path / "broken").mkdir()
    (tmp_path / "kept").mkdir()

    report, found = _run_the_pytest_module(tmp_path / "broken", broken=True)

    assert report.found
    kinds = {(case["what"], f["kind"]) for case, f in found}
    assert ("with `title` 5000 characters long", "server_error") in kinds
    assert ("with `title` empty", "stored_on_refusal") in kinds
    assert ("with `title` only spaces", "changed_on_refusal") in kinds
    assert ("in several scripts", "not_kept") not in kinds  # under 100 characters: kept whole
    assert ("at id `not-a-number`", "server_error") in kinds
    assert ("at an id already deleted", "server_error") in kinds

    report, found = _run_the_pytest_module(tmp_path / "kept", broken=False)

    assert report.found and len(report.tests) == len(_ids())
    assert found == [] and not [t for t in report.tests if t.outcome == "failed"]


def test_a_value_cut_short_is_found_when_the_record_is_read_back():
    case = {"method": "POST", "shown": "/notes", "what": "with `title` 5000 characters long", "list": "/notes"}
    found = {"kind": "not_kept", "status": 201, "field": "title", "sent": 5000, "kept": "x" * 60, "kept_length": 100}

    text = ep.edge_description([(case, found)])

    assert text.startswith(ep.EDGE_CASES_FAILED)
    assert "`POST /notes` with `title` 5000 characters long answered 201" in text
    assert "(100 characters) where 5000 characters were sent" in text
    assert "AC-" not in text and not BANNED.search(text)


@pytest.mark.skipif(shutil.which("node") is None, reason="no node to read the spec")
def test_the_playwright_spec_is_javascript_node_can_read(tmp_path):
    lines = ic.parse([*LINES, "AC-7 POST /auth/signup -> 201"])[0]
    spec = ep.playwright_edge_checks(ep.edge_cases(lines, BODIES), ic.sign_in_plan(lines, BODIES))
    assert "async function signedIn(request)" in spec
    (tmp_path / "edge.spec.mjs").write_text(spec)
    done = subprocess.run(["node", "--check", str(tmp_path / "edge.spec.mjs")], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def _project(tmp_path, monkeypatch):
    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(probe_runner="pytest"), {"project": "app"}))
    (tmp_path / "app").mkdir()
    ic.record_at_lock(tmp_path, LINES)


def _reporting(failed: bool):
    def report(project, name, probe, web, run, compiled_by="checks", bodies=None):
        probe[compiled_by](web)
        found = json.dumps({"kind": "server_error", "status": 500, "said": "Traceback"})
        test = SimpleNamespace(name="test_edge[edge 1: GET /notes/{noteId} at id `not-a-number`]",
                               outcome="failed" if failed else "passed",
                               message=f"AssertionError: {ep.MARKER} {found}" if failed else "")
        return SimpleNamespace(found=True, tests=[test])
    return report


def test_a_green_round_raises_it_behind_its_switch_and_the_probe_settles_it(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    monkeypatch.setattr(acceptance_nodes.suite, "is_locked", lambda root: True)
    for name in ("server_errors", "bad_body_errors", "emptied_field_errors"):
        monkeypatch.setattr(ic, name, lambda root, runner=None: [])
    monkeypatch.setattr(ic, "_the_probe_s_report", _reporting(failed=True))  # the probe's run in the sandbox
    monkeypatch.setenv("CONTRACT_SERVER_ERRORS_AT_A_ROUND", "on")
    monkeypatch.setenv("WRONG_SHAPE_BODY_PROBE", "off")
    monkeypatch.setenv("CONCURRENT_WRITE_PROBE", "off")
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}
    green = SpecialistOutput(changed_files=[], defects=[], decisions=[])
    milestone = SimpleNamespace(delegated_tasks=[], milestone_scope=[])

    monkeypatch.setenv("EDGE_PROBE", "off")
    assert workflow._with_the_contract_s_server_errors(state, green, milestone).defects == []
    monkeypatch.setenv("EDGE_PROBE", "on")
    raised = workflow._with_the_contract_s_server_errors(state, green, milestone).defects

    assert len(raised) == 1 and raised[0].description.startswith(ep.EDGE_CASES_FAILED)
    assert "`GET /notes/{noteId}` at id `not-a-number` answered 500 (it said: Traceback)" in raised[0].description
    assert not BANNED.search(" ".join([raised[0].description, raised[0].reproduction_steps,
                                       raised[0].expected_behavior, raised[0].actual_behavior]))
    assert ic.still_raised(tmp_path, raised[0].description, runner=lambda *a: {}) is True
    monkeypatch.setattr(ic, "_the_probe_s_report", _reporting(failed=False))
    assert ic.still_raised(tmp_path, raised[0].description, runner=lambda *a: {}) is False
