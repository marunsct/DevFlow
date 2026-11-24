"""A record deleted twice answers not-found the second time, and a long text written is read back whole: probed.

Measured: a notes service passed every hidden acceptance test and lost two hidden quality tests no harness probe
asked - a record deleted a second time was answered 204 where the contract gives 404, and a long body of many lines
was not read back as it was written. The round-trip probe asks both from the locked contract on every green round and
again at release; a refusal of the long value is judged only from the brief (LF.1298; its own tests).
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

from app import completion_verdict
from app.acceptance import interface_contract as ic
from app.acceptance import junit, probe_coverage, probes_at_release
from app.acceptance import round_trip_probe as rp
from app.agents.specialists import SpecialistOutput
from app.graph import acceptance_nodes, workflow
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
LINES = ["AC-1 POST /notes -> 201", "AC-2 GET /notes -> 200", "AC-3 GET /notes/{noteId} -> 200, 404",
         "AC-4 PUT /notes/{noteId} -> 200, 404", "AC-5 DELETE /notes/{noteId} -> 204, 404"]
BODIES = [{"title": "milk", "body": "two litres"}]


class _Notes(BaseHTTPRequestHandler):
    """A notes service kept in memory; each flag is one fault of the kind the hidden quality tests caught."""

    deletes_again = False  # a second delete of a record answers 204
    cut_at = 0  # the store keeps only the first `cut_at` characters of a text
    one_line = False  # the store keeps a text's first line only, as a store of one record a line does
    refuses_long = False  # a create with a text over 1,000 characters is refused with 413
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

    def _id(self):
        part = self.path.rstrip("/").split("/")[-1]
        return int(part) if part.isdigit() else None

    def do_GET(self):  # noqa: N802
        records = type(self).records
        if self.path.rstrip("/") == "/notes":
            return self._answer(200, [{"id": k, **v} for k, v in sorted(records.items()) if v is not None])
        found = records.get(self._id())
        return self._answer(200, {"id": self._id(), **found}) if found else self._answer(404, {"error": "no such note"})

    def do_POST(self):  # noqa: N802
        cls = type(self)
        body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"null")
        if not isinstance(body, dict) or not isinstance(body.get("title"), str) or not body["title"].strip():
            return self._answer(400, {"error": "title"})
        texts = {k: v for k, v in body.items() if isinstance(v, str)}
        if cls.refuses_long and any(len(v) > 1000 for v in texts.values()):
            return self._answer(413, {"error": "too long"})
        new = len(cls.records) + 1
        texts = {k: v.split("\n")[0] if cls.one_line else v for k, v in texts.items()}
        cls.records[new] = {k: v[:cls.cut_at] if cls.cut_at else v for k, v in texts.items()}
        return self._answer(201, {"id": new, **cls.records[new]})

    def do_DELETE(self):  # noqa: N802
        cls, found = type(self), self._id()
        if found in cls.records and (cls.records[found] is not None or cls.deletes_again):
            cls.records[found] = None
            return self._answer(204)
        return self._answer(404, {"error": "no such note"})


def _probe(tmp_path, **faults):
    """The probe's pytest module run against a notes service with `faults`: (its report, what each failed test found)."""
    handler = type("Notes", (_Notes,), {"records": {}, **faults})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        cases, _, _ = rp.round_trip_cases(ic.parse(LINES)[0], BODIES)
        (tmp_path / "test_probe.py").write_text(rp.pytest_round_trip_checks(cases, None))
        (tmp_path / "conftest.py").write_text(
            f"import pytest\n\n@pytest.fixture\ndef base_url():\n    return 'http://127.0.0.1:{server.server_port}'\n")
        env = {**os.environ, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
        subprocess.run([sys.executable, "-m", "pytest", "test_probe.py", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                        "--junitxml=report.xml"], cwd=tmp_path, capture_output=True, text=True, env=env, timeout=300)
        report = junit.read(tmp_path / "report.xml")
        return report, [(case, found) for test in report.tests if (case := rp.the_case_of(test, cases))
                        and (found := rp.what_the_test_found(test)) is not None]
    finally:
        server.shutdown()


def test_a_second_delete_answered_204_is_found_with_the_contract_s_not_found_status(tmp_path):
    _, found = _probe(tmp_path, deletes_again=True)

    text = rp.round_trip_description(found)

    assert [case["kind"] for case, _ in found] == ["deleted_twice"]
    assert text.startswith(rp.ROUND_TRIPS_FAILED)
    assert "`DELETE /notes/{noteId}` sent twice to one record" in text
    assert "deleting the record that was already deleted answered 204; the contract says 404" in text
    assert not BANNED.search(text)


@pytest.mark.parametrize(("faults", "kept"), [
    ({"cut_at": 1000}, "read it back as 1000 characters over 21 lines, first differing at character 1000"),
    ({"cut_at": 10000}, "read it back as 10000 characters over 205 lines, first differing at character 10000"),
    ({"one_line": True}, "read it back as 48 characters over 1 lines, first differing at character 48"),
], ids=["cut at 1,000 characters", "cut at 10,000 characters", "line breaks lost"])
def test_a_store_not_keeping_a_long_text_whole_is_found_with_what_it_read_back(tmp_path, faults, kept):
    _, found = _probe(tmp_path, **faults)

    text = rp.round_trip_description(found)

    assert [case["kind"] for case, _ in found] == ["kept_whole"]
    assert {lost["field"] for lost in found[0][1]["lost"]} == {"title", "body"}
    assert f"`GET /notes/{{noteId}}` {kept}" in text
    assert not BANNED.search(text)


@pytest.mark.parametrize("faults", [{}, {"refuses_long": True}], ids=["keeps every round trip", "refuses a long text"])
def test_a_service_keeping_every_round_trip_or_refusing_a_long_text_is_not_found(tmp_path, faults):
    report, found = _probe(tmp_path, **faults)

    assert report.found and len(report.tests) == 2
    assert found == [] and not [t for t in report.tests if t.outcome == "failed"]


def test_a_delete_line_with_no_not_found_status_is_left_with_its_reason():
    lines = ic.parse(["AC-1 POST /notes -> 201", "AC-2 DELETE /notes/{id} -> 204"])[0]

    cases, asked, left = rp.round_trip_cases(lines, BODIES)

    assert cases == [] and asked == []
    assert [line for line, _ in left] == ["AC-2 DELETE /notes/{id} -> 204", "AC-1 POST /notes -> 201"]


@pytest.mark.skipif(shutil.which("node") is None, reason="no node to read the spec")
def test_the_playwright_spec_is_javascript_node_can_read(tmp_path):
    lines = ic.parse([*LINES, "AC-6 POST /auth/login -> 200"])[0]
    bodies = [*BODIES, {"username": "a", "password": "b"}]
    spec = rp.playwright_round_trip_checks(rp.round_trip_cases(lines, bodies)[0], ic.sign_in_plan(lines, bodies))
    assert "async function signedIn(request)" in spec
    (tmp_path / "round_trip.spec.mjs").write_text(spec)
    done = subprocess.run(["node", "--check", str(tmp_path / "round_trip.spec.mjs")], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def _a_project(tmp_path, monkeypatch, failed):
    """A locked contract on a pytest-probed pack; the probe's run in the sandbox gives a second delete answered 204."""
    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(probe_runner="pytest"), {"project": "app"}))
    (tmp_path / "app").mkdir(exist_ok=True)
    ic.record_at_lock(tmp_path, LINES)

    def report(project, name, probe, web, run, compiled_by="checks", bodies=None):
        probe[compiled_by](web)
        found = json.dumps({"kind": "deleted_twice", "first": 204, "second": 204, "said": "", "not_found": [404]})
        test = SimpleNamespace(name="test_round_trip[round trip 1: DELETE /notes/{noteId} sent twice to one record]",
                               outcome="failed" if failed else "passed",
                               message=f"AssertionError: {rp.MARKER} {found}" if failed else "")
        return SimpleNamespace(found=True, tests=[test])

    monkeypatch.setattr(ic, "_the_probe_s_report", report)


def test_a_green_round_raises_it_with_no_switch_and_the_probe_settles_it(tmp_path, monkeypatch):
    _a_project(tmp_path, monkeypatch, failed=True)
    monkeypatch.setattr(acceptance_nodes.suite, "is_locked", lambda root: True)
    for name in ("server_errors", "bad_body_errors", "emptied_field_errors"):
        monkeypatch.setattr(ic, name, lambda root, runner=None: [])
    monkeypatch.setenv("CONTRACT_SERVER_ERRORS_AT_A_ROUND", "on")
    for switch in ("WRONG_SHAPE_BODY_PROBE", "CONCURRENT_WRITE_PROBE", "EDGE_PROBE"):
        monkeypatch.setenv(switch, "off")
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}
    green = SpecialistOutput(changed_files=[], defects=[], decisions=[])

    raised = workflow._with_the_contract_s_server_errors(state, green, SimpleNamespace(delegated_tasks=[],
                                                                                        milestone_scope=[])).defects

    assert len(raised) == 1 and raised[0].description.startswith(rp.ROUND_TRIPS_FAILED)
    assert "already deleted answered 204; the contract says 404" in raised[0].description
    assert probes_at_release.carries_a_finding(raised[0])
    assert not BANNED.search(" ".join([raised[0].description, raised[0].reproduction_steps,
                                       raised[0].expected_behavior, raised[0].actual_behavior]))
    recorded = json.loads((tmp_path / probe_coverage.COVERAGE_FILE).read_text())["round_trip"]
    assert (recorded["considered"], recorded["asked"], recorded["probed"]) == (5, 1, 1)
    # No example body was recorded at the lock: the create line is left with why.
    assert [s["line"] for s in recorded["skipped"]] == ["AC-1 POST /notes -> 201"]
    assert ic.still_raised(tmp_path, raised[0].description, runner=lambda *a: {}) is True
    _a_project(tmp_path, monkeypatch, failed=False)
    assert ic.still_raised(tmp_path, raised[0].description, runner=lambda *a: {}) is False


def test_what_it_still_finds_at_release_is_a_blocking_gap(tmp_path, monkeypatch):
    _a_project(tmp_path, monkeypatch, failed=True)

    gaps = [g for g in probes_at_release.what_the_probes_still_find(tmp_path, runner=lambda *a: {})
            if rp.ROUND_TRIPS_FAILED in g]

    assert len(gaps) == 1 and "`DELETE /notes/{noteId}` sent twice to one record" in gaps[0]
    assert completion_verdict.is_blocking(gaps[0])
