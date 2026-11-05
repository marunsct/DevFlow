"""A Python service's interface contract is probed like every other service's.

Measured: the contract probes (each line asked bare, each write with a body nothing can parse, each refused field sent
empty) ran only through Playwright, and the two Python service packs test with pytest - so on the notes-api and
tasks-api families no probe ever ran ("no runner on this stack probes a http line"), including the emptied-field
probe that closed a false acceptance on another stack. Here the compiled probe runs under real pytest against a
small service that crashes on a bad body and accepts an emptied title, and the harness reads both back.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from dataclasses import replace

from app.acceptance import interface_contract as ic
from app.acceptance import junit

CONFTEST = textwrap.dedent('''
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    import pytest

    NOTES = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _answer(self, status, body=None):
            data = json.dumps(body).encode() if body is not None else b""
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            raw = self.rfile.read(int(self.headers.get("content-length") or 0))
            return json.loads(raw)  # a body nothing can parse raises: the server answers 500

        def do_GET(self):
            self._answer(200, list(NOTES.values()))

        def do_POST(self):
            try:
                body = self._body()
            except ValueError:
                return self._answer(500)
            if not body.get("title"):
                return self._answer(422, {"detail": "title"})
            note = {"id": len(NOTES) + 1, **body}
            NOTES[note["id"]] = note
            self._answer(201, note)

        def do_PUT(self):
            note_id = int(self.path.rsplit("/", 1)[-1])
            try:
                body = self._body()
            except ValueError:
                return self._answer(500)
            NOTES[note_id] = {"id": note_id, **body}  # an emptied title is accepted: the defect
            self._answer(200, NOTES[note_id])

    @pytest.fixture(scope="session")
    def base_url():
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{server.server_address[1]}"
        server.shutdown()
''')

BODY = '{"title": "Milk", "body": "two"}'
CREATE = ic.Check(criterion="AC-1", kind="http", line="POST /notes -> 201", method="POST", path="/notes",
                  status=201, statuses=(201,))
UPDATE = ic.Check(criterion="AC-2", kind="http", line="PUT /notes/{id} -> 200", method="PUT", path="/notes/{id}",
                  status=200, statuses=(200,), made_through="/notes", bodies=f"[{BODY}]")


def _run(project, source):
    (project / "acceptance").mkdir(exist_ok=True)
    (project / "acceptance" / "conftest.py").write_text(CONFTEST)
    (project / ic.PYTEST_PROBE_FILE).write_text(source)
    subprocess.run([sys.executable, "-m", "pytest", ic.PYTEST_PROBE_FILE, "-q", "-p", "no:cacheprovider",
                    f"--junitxml={ic.REPORT_FILE}"], cwd=project, capture_output=True, timeout=120)
    return junit.read(project / ic.REPORT_FILE)


def test_a_crash_on_a_bad_body_is_read_back_as_a_server_error(tmp_path):
    asked = [CREATE, UPDATE]
    report = _run(tmp_path, ic.pytest_bad_body_checks(asked))

    failed = [t for t in report.tests if t.outcome == "failed"]
    assert len(failed) == 2
    assert {ic._the_check_of(t, asked).line for t in failed} == {CREATE.line, UPDATE.line}
    assert all(ic._a_server_error(t) == 500 for t in failed)


def test_an_emptied_field_the_service_accepts_fails(tmp_path):
    asked = [replace(UPDATE, emptied="title"), replace(CREATE, emptied="title", bodies=f"[{BODY}]")]
    report = _run(tmp_path, ic.pytest_emptied_field_checks(asked))

    outcomes = {ic._the_check_of(t, asked).line: t.outcome for t in report.tests}
    assert outcomes == {UPDATE.line: "failed", CREATE.line: "passed"}


def test_bare_lines_pass_on_a_service_that_keeps_its_contract(tmp_path):
    report = _run(tmp_path, ic.pytest_checks([replace(UPDATE, line="PUT /notes/{id} -> 200")]))
    assert [t.outcome for t in report.tests] == ["passed"]


def test_the_python_service_packs_declare_the_pytest_probe():
    from app.stacks import pack_named

    assert pack_named("python-http-api").probe_runner == "pytest"
    assert pack_named("python-flask-api").probe_runner == "pytest"
    assert pack_named("python-cli").probe_runner == ""
    assert ic.PROBE_RUNNERS["pytest"]["file"] == ic.PYTEST_PROBE_FILE
