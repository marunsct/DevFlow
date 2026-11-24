"""A long value refused where the brief sets no length limit is a finding, not a skip.

Measured (LF.1298): the hidden quality test that writes a note with a 26,000-character body and reads it back failed in
17 of 95 scored runs. On a Rust run the specification added "title max 500, body max 10000 characters" where the brief
sets no maximum; the product refused the long body with 400 and the hidden test failed. The harness's round-trip probe
sent about 20,000 characters, but took the refusal as the product's choice: with nothing read back the test skipped,
and the coverage said "1 skipped by the probe". Here the compiled probe runs under real pytest, and the Playwright
spec under plain Node, against a small notes service; only what the brief and its criteria say decides the verdict.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from app.acceptance import interface_contract as ic
from app.acceptance import junit, probes_at_release, suite
from app.acceptance import round_trip_probe as rp
from app.agents.specialists import SpecialistOutput
from app.graph import acceptance_nodes, workflow
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
LINES = ["AC-1 POST /notes -> 201", "AC-2 GET /notes -> 200", "AC-3 GET /notes/{noteId} -> 200, 404"]
BODIES = [{"title": "milk", "body": "two litres"}]
BRIEF_WITH_NO_LIMIT = ["A note has a title and a body. A title that is missing or empty is refused with 400."]


class _Notes(BaseHTTPRequestHandler):
    """A notes service kept in memory that refuses a text longer than its own limit for that field."""

    limits: dict = {}  # field -> the most characters it takes
    refused_with = 400
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

    def do_GET(self):  # noqa: N802
        records = type(self).records
        if self.path.rstrip("/") == "/notes":
            return self._answer(200, [{"id": k, **v} for k, v in sorted(records.items())])
        part = self.path.rstrip("/").split("/")[-1]
        found = records.get(int(part)) if part.isdigit() else None
        return self._answer(200, {"id": int(part), **found}) if found else self._answer(404, {"error": "no such note"})

    def do_POST(self):  # noqa: N802
        cls = type(self)
        body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"null")
        if not isinstance(body, dict) or not str(body.get("title") or "").strip():
            return self._answer(400, {"error": "title is required"})
        for field, most in cls.limits.items():
            if len(str(body.get(field) or "")) > most:
                return self._answer(cls.refused_with, {"error": f"{field} must be at most {most} characters"})
        new = len(cls.records) + 1
        cls.records[new] = {k: v for k, v in body.items() if isinstance(v, str)}
        return self._answer(201, {"id": new, **cls.records[new]})


def _a_service(**faults):
    server = ThreadingHTTPServer(("127.0.0.1", 0), type("Notes", (_Notes,), {"records": {}, **faults}))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _run_the_module(tmp_path, module, port):
    (tmp_path / "test_probe.py").write_text(module)
    (tmp_path / "conftest.py").write_text(
        f"import pytest\n\n@pytest.fixture\ndef base_url():\n    return 'http://127.0.0.1:{port}'\n")
    env = {**os.environ, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
    subprocess.run([sys.executable, "-m", "pytest", "test_probe.py", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                    "--junitxml=report.xml"], cwd=tmp_path, capture_output=True, text=True, env=env, timeout=300)
    return junit.read(tmp_path / "report.xml")


def _probe(tmp_path, brief, **faults):
    """The probe's pytest module run against the notes service: (its report, what each failed test found)."""
    server = _a_service(**faults)
    try:
        cases, _, _ = rp.round_trip_cases(ic.parse(LINES)[0], BODIES, brief)
        report = _run_the_module(tmp_path, rp.pytest_round_trip_checks(cases, None), server.server_port)
        return report, [(case, found) for test in report.tests if (case := rp.the_case_of(test, cases))
                        and (found := rp.what_the_test_found(test)) is not None]
    finally:
        server.shutdown()


def test_a_body_the_brief_sets_no_limit_on_refused_with_400_is_found(tmp_path):
    _, found = _probe(tmp_path, BRIEF_WITH_NO_LIMIT, limits={"title": 500, "body": 10000})

    text = rp.round_trip_description(found)

    assert [case["kind"] for case, _ in found] == ["kept_whole"]
    assert {lost["field"] for lost in found[0][1]["lost"]} == {"title", "body"}
    assert "`body` sent as 19599 characters over 400 lines was refused with 400" in text
    assert "body must be at most 10000 characters" in text
    assert "the brief sets no maximum length for `body`" in text
    assert not BANNED.search(text)


@pytest.mark.parametrize(("brief", "limits"), [
    (["- `body`: text, at most 5000 characters"], {"body": 5000}),
    (["A note has a title (max 200) and a body of up to 10,000 characters."], {"title": 200, "body": 10000}),
    (["A body that is too long is refused with 400."], {"body": 10000}),
], ids=["at most", "max and up to", "too long refused"])
def test_a_refusal_of_a_field_the_brief_holds_to_a_most_length_is_not_found(tmp_path, brief, limits):
    _, found = _probe(tmp_path, brief, limits=limits)

    assert found == []


@pytest.mark.parametrize("faults", [{}, {"limits": {"body": 10000}, "refused_with": 413}],
                         ids=["keeps the long text", "refuses the whole request as too large"])
def test_a_service_keeping_the_long_text_or_refusing_it_as_too_large_is_not_found(tmp_path, faults):
    report, found = _probe(tmp_path, BRIEF_WITH_NO_LIMIT, **faults)

    assert report.found and found == []


def test_with_no_brief_known_a_refusal_is_not_judged(tmp_path):
    report, found = _probe(tmp_path, None, limits={"title": 500, "body": 10000})

    assert found == [] and [t.outcome for t in report.tests] == ["skipped"]


@pytest.mark.parametrize(("text", "held"), [
    ("- body: string, at most 5000 characters", ["body"]),
    ("title max 500, body max 10000 characters", ["title", "body"]),
    ("A title of up to 200 characters; a body free of any limit", ["title"]),
    ('Note: {"title": {"type": "string", "maxLength": 200}, "body": {"type": "string"}}', ["title"]),
    ("title: 1-200 characters", ["title"]),
    ("A title longer than 120 characters is refused", ["title"]),
    ("A note has a title and a body; the title must not be empty", []),
    ("Up to 50 notes are listed per page, each with a title and a body", []),
    ("The request body is at most 1 MB", []),
])
def test_a_most_length_is_read_field_by_field(text, held):
    assert ic.fields_held_to_a_ceiling([text], ["title", "body"]) == held


#: Just enough of Playwright's `test` and `request` to run the compiled spec in plain Node against a service.
PLAYWRIGHT_IN_NODE = textwrap.dedent("""
    const BASE = process.env.BASE;
    const cases = [];
    const test = (name, body) => cases.push([name, body]);
    test.skip = (skipped, why) => { if (skipped) throw { skipped: why }; };
    const expect = () => ({});
    const request = { fetch: async (path, options) => {
      const answer = await fetch(BASE + path, { method: options.method, headers: options.headers,
        body: options.data === undefined ? undefined : String(options.data) });
      const text = await answer.text();
      return { status: () => answer.status, text: async () => text };
    } };
    // THE SPEC
    const outcomes = [];
    for (const [name, body] of cases) {
      try { await body({ request }); outcomes.push([name, 'passed', '']); }
      catch (error) { outcomes.push([name, error.skipped ? 'skipped' : 'failed', String(error.skipped || error.message)]); }
    }
    console.log(JSON.stringify(outcomes));
""")


@pytest.mark.skipif(shutil.which("node") is None, reason="no node to run the compiled spec")
@pytest.mark.parametrize(("brief", "faults", "outcome"), [
    (BRIEF_WITH_NO_LIMIT, {"limits": {"body": 10000}}, "failed"),
    (["- body: string, at most 5000 characters"], {"limits": {"body": 10000}}, "passed"),
    (BRIEF_WITH_NO_LIMIT, {}, "passed"),
], ids=["refused where the brief sets no limit", "refused where the brief sets one", "kept whole"])
def test_the_playwright_probe_finds_a_long_value_refused_where_the_brief_sets_no_limit(tmp_path, brief, faults, outcome):
    server = _a_service(**faults)
    cases, _, _ = rp.round_trip_cases(ic.parse(LINES)[0], BODIES, brief)
    spec = rp.playwright_round_trip_checks(cases).replace("import { test, expect } from '@playwright/test';", "")
    (tmp_path / "spec.mjs").write_text(PLAYWRIGHT_IN_NODE.replace("// THE SPEC", spec, 1))
    try:
        done = subprocess.run(["node", str(tmp_path / "spec.mjs")], capture_output=True, text=True, timeout=60,
                              env={**os.environ, "BASE": f"http://127.0.0.1:{server.server_address[1]}"})
    finally:
        server.shutdown()

    outcomes = json.loads(done.stdout.strip().splitlines()[-1])
    assert [o for _, o, _ in outcomes] == [outcome], done.stderr
    found = rp.what_the_test_found(SimpleNamespace(message=outcomes[0][2]))
    assert (found or {}).get("lost", [{}])[0].get("refused") == (400 if outcome == "failed" else None)


def _a_project(tmp_path, monkeypatch, port):
    """A locked contract on a pytest-probed pack whose probe runs, in place of the sandbox, against a local service."""
    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(probe_runner="pytest"), {"project": "app"}))
    (tmp_path / "app").mkdir(exist_ok=True)
    ic.record_at_lock(tmp_path, LINES)
    state = suite._state(tmp_path)
    state["interface_contract_bodies"] = BODIES
    suite._save_state(tmp_path, state)
    runs = tmp_path / "runs"

    def report(project, name, probe, web, run, compiled_by="checks", bodies=None):
        runs.mkdir(exist_ok=True)
        return _run_the_module(runs, probe[compiled_by](web), port)

    monkeypatch.setattr(ic, "_the_probe_s_report", report)


def test_a_green_round_raises_it_from_the_run_s_brief_and_release_still_finds_it(tmp_path, monkeypatch):
    server = _a_service(limits={"body": 10000})
    try:
        _a_project(tmp_path, monkeypatch, server.server_port)
        monkeypatch.setattr(acceptance_nodes.suite, "is_locked", lambda root: True)
        for name in ("server_errors", "bad_body_errors", "emptied_field_errors"):
            monkeypatch.setattr(ic, name, lambda root, runner=None: [])
        monkeypatch.setattr(ic, "kept_empty_errors", lambda root, brief=None, runner=None: [])
        monkeypatch.setenv("CONTRACT_SERVER_ERRORS_AT_A_ROUND", "on")
        for switch in ("WRONG_SHAPE_BODY_PROBE", "CONCURRENT_WRITE_PROBE", "EDGE_PROBE"):
            monkeypatch.setenv(switch, "off")
        state = {"repository": SimpleNamespace(root_path=str(tmp_path)),
                 "document": SimpleNamespace(text=BRIEF_WITH_NO_LIMIT[0])}
        green = SpecialistOutput(changed_files=[], defects=[], decisions=[])

        raised = workflow._with_the_contract_s_server_errors(
            state, green, SimpleNamespace(delegated_tasks=[], milestone_scope=[])).defects

        assert len(raised) == 1 and "`body` sent as 19599 characters over 400 lines was refused with 400" \
            in raised[0].description
        assert not BANNED.search(" ".join([raised[0].description, raised[0].reproduction_steps,
                                           raised[0].expected_behavior, raised[0].actual_behavior]))
        gaps = [g for g in probes_at_release.what_the_probes_still_find(tmp_path, runner=lambda *a: {})
                if rp.ROUND_TRIPS_FAILED in g]
        assert len(gaps) == 1 and "was refused with 400" in gaps[0]
    finally:
        server.shutdown()
