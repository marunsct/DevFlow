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
            if self.path != "/notes":
                return self._answer(422, {"detail": "username"})
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


def test_a_write_that_never_takes_the_field_is_skipped_not_passed(tmp_path):
    """Measured on one run: the emptied `title` was sent to `/signup`, which takes no title; refused for that, the
    check passed and proved nothing."""
    signup = ic.Check(criterion="AC-3", kind="http", line="POST /signup -> 201", method="POST", path="/signup",
                      status=201, statuses=(201,), emptied="title", bodies='[{"username": "a"}, ' + BODY + ']')
    report = _run(tmp_path, ic.pytest_emptied_field_checks([signup]))
    assert [t.outcome for t in report.tests] == ["skipped"]


def test_the_playwright_probe_asks_the_plain_body_first():
    check = replace(UPDATE, emptied="title")
    source = ic.playwright_emptied_field_checks([check], [{"title": "Milk", "body": "two"}])
    assert ic.NOT_THIS_WRITE_S_BODY in source
    assert source.index("const plain") < source.index("const answer")


SIGNED_CONFTEST = textwrap.dedent('''
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    import pytest

    USERS, ITEMS = {}, {}

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

        def do_GET(self):
            if self.headers.get("Authorization", "")[:9] != "Bearer t-":
                return self._answer(401)
            self._answer(200, list(ITEMS.values()))

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("content-length") or 0))
            body = json.loads(raw)
            if self.path == "/signup":
                USERS[body["username"]] = body["password"]
                return self._answer(201, {"username": body["username"]})
            if self.path == "/signin":
                if USERS.get(body.get("username")) != body.get("password"):
                    return self._answer(401)
                return self._answer(200, {"token": "t-" + body["username"]})
            if self.headers.get("Authorization", "")[:9] != "Bearer t-":
                return self._answer(401)
            item = {"id": len(ITEMS) + 1, "title": body.get("title", ""), "done": False}
            ITEMS[item["id"]] = item  # an empty title is accepted: the defect
            self._answer(201, item)

    @pytest.fixture(scope="session")
    def base_url():
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{server.server_address[1]}"
        server.shutdown()
''')


def test_a_write_behind_sign_in_is_reached_with_a_token(tmp_path):
    """Measured on one run: behind sign-in, the emptied-field probe of `POST /items` was answered 401 before the body
    was read, so the write the probe exists for was never asked."""
    bodies = [{"username": "ann", "password": "secret-1"}, {"title": "Milk"}]
    contract = [
        ic.Check(criterion="AC-1", kind="http", line="POST /signup -> 201", method="POST", path="/signup",
                 status=201, statuses=(201,)),
        ic.Check(criterion="AC-2", kind="http", line="POST /signin -> 200", method="POST", path="/signin",
                 status=200, statuses=(200,)),
        ic.Check(criterion="AC-3", kind="http", line="POST /items -> 201", method="POST", path="/items",
                 status=201, statuses=(201,), emptied="title"),
    ]
    (tmp_path / "acceptance").mkdir()
    (tmp_path / "acceptance" / "conftest.py").write_text(SIGNED_CONFTEST)
    # As `emptied_field_checks` asks them: every write, once per field an example body carries.
    asked = [replace(c, emptied="title") for c in contract]
    (tmp_path / ic.PYTEST_PROBE_FILE).write_text(ic.pytest_emptied_field_checks(asked, bodies))
    subprocess.run([sys.executable, "-m", "pytest", ic.PYTEST_PROBE_FILE, "-q", "-p", "no:cacheprovider",
                    f"--junitxml={ic.REPORT_FILE}"], cwd=tmp_path, capture_output=True, timeout=120)
    report = junit.read(tmp_path / ic.REPORT_FILE)
    outcomes = {ic._the_check_of(t, asked).path: t.outcome for t in report.tests}
    assert outcomes["/items"] == "failed"  # reached with a token, and the empty title it accepted is found


def test_the_plan_reads_the_contract_s_own_sign_in():
    contract = [ic.Check(criterion="AC-1", kind="http", line="POST /api/auth/register -> 201", method="POST",
                         path="/api/auth/register"),
                ic.Check(criterion="AC-2", kind="http", line="POST /api/auth/login -> 200", method="POST",
                         path="/api/auth/login")]
    plan = ic.sign_in_plan(contract, [{"title": "x"}, {"email": "a@b.c", "password": "p"}])
    assert plan == {"signup": "/api/auth/register", "signin": "/api/auth/login",
                    "body": {"email": "a@b.c", "password": "p"}}
    assert ic.sign_in_plan(contract[:1], [{"password": "p"}]) is None


def test_the_playwright_body_probe_signs_in_too():
    contract = [ic.Check(criterion="AC-2", kind="http", line="POST /signin -> 200", method="POST", path="/signin",
                         status=200, statuses=(200,)),
                replace(CREATE, emptied="title")]
    source = ic.playwright_emptied_field_checks(contract[1:], [{"username": "a", "password": "p"}, {"title": "x"}])
    assert "signedIn" not in source  # no sign-in line among the checks it was given
    source = ic.playwright_emptied_field_checks([replace(contract[0], emptied="username"), contract[1]],
                                               [{"username": "a", "password": "p"}, {"title": "x"}])
    assert "...(await signedIn(request))" in source


def test_a_bare_line_behind_sign_in_is_asked_signed_in_unless_it_is_the_refusal(tmp_path):
    """Measured on one run: `GET /items -> 200` behind sign-in was asked unsigned, answered 401, and was reported at
    release as a contract the product does not keep - three such false lines."""
    bodies = [{"username": "ann", "password": "secret-1"}, {"title": "Milk"}]
    contract = [
        ic.Check(criterion="AC-1", kind="http", line="POST /signup -> 201", method="POST", path="/signup",
                 status=201, statuses=(201,)),
        ic.Check(criterion="AC-2", kind="http", line="POST /signin -> 200", method="POST", path="/signin",
                 status=200, statuses=(200,)),
        ic.Check(criterion="AC-3", kind="http", line="GET /items -> 200", method="GET", path="/items",
                 status=200, statuses=(200,)),
        ic.Check(criterion="AC-4", kind="http", line="GET /items -> 401", method="GET", path="/items",
                 status=401, statuses=(401,)),
    ]
    (tmp_path / "acceptance").mkdir()
    (tmp_path / "acceptance" / "conftest.py").write_text(SIGNED_CONFTEST)
    (tmp_path / ic.PYTEST_PROBE_FILE).write_text(ic.pytest_checks(contract[2:] + contract[:2], bodies))
    subprocess.run([sys.executable, "-m", "pytest", ic.PYTEST_PROBE_FILE, "-q", "-p", "no:cacheprovider",
                    f"--junitxml={ic.REPORT_FILE}"], cwd=tmp_path, capture_output=True, timeout=120)
    asked = contract[2:] + contract[:2]
    outcomes = {ic._the_check_of(t, asked).line: t.outcome for t in junit.read(tmp_path / ic.REPORT_FILE).tests}
    assert outcomes["GET /items -> 200"] == "passed" and outcomes["GET /items -> 401"] == "passed"


def test_the_playwright_bare_line_signs_in_only_when_the_line_is_not_the_refusal():
    contract = [ic.Check(criterion="AC-2", kind="http", line="POST /signin -> 200", method="POST", path="/signin",
                         status=200, statuses=(200,)),
                ic.Check(criterion="AC-3", kind="http", line="GET /items -> 200", method="GET", path="/items",
                         status=200, statuses=(200,)),
                ic.Check(criterion="AC-4", kind="http", line="GET /items -> 401", method="GET", path="/items",
                         status=401, statuses=(401,))]
    source = ic.playwright_checks(contract, [{"username": "a", "password": "p"}])
    signed = [line for line in source.splitlines() if "request.fetch(" in line and "/items" in line]
    assert "signedIn" in signed[0] and "signedIn" not in signed[1]
    assert "signedIn" not in ic.playwright_checks(contract[1:], [])
