"""A server error the contract's probes meet carries what the product's server printed for that request.

Measured on one run: the edge probe's `DELETE /items/99999999999999999999` answered 500 on a Flask service on SQLite,
and the defect showed only the framework's HTML error page. The service had printed its traceback -
`OverflowError: Python int too large to convert to SQLite INTEGER` - to the log its acceptance setup keeps; no fixer
was shown it, five fixes in a row left the defect open and the sprint was planned again twice.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from types import SimpleNamespace

from app.acceptance import edge_probe as ep
from app.acceptance import interface_contract as ic
from app.acceptance import suite, what_went_wrong
from app.agents.specialists import ReportedDefect, SpecialistOutput
from app.graph import workflow
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
LINES = ["AC-1 GET /items -> 200", "AC-2 GET /items/{id} -> 200, 404", "AC-3 DELETE /items/{id} -> 204, 404"]
OVERFLOW = "OverflowError: Python int too large to convert to SQLite INTEGER"

#: A service on the standard library and SQLite that fails the way the measured one did: an id past 64 bits reaches
#: sqlite3, and a framework-style handler answers an HTML error page and prints the traceback.
PRODUCT = '''
import json, os, sqlite3, sys, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DB = sqlite3.connect(":memory:", check_same_thread=False)
DB.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, title TEXT)")
PAGE = (b"<!doctype html>\\n<html lang=en>\\n<title>500 Internal Server Error</title>\\n<h1>Internal Server Error</h1>"
        b"\\n<p>The server encountered an internal error and was unable to complete your request. Either the server "
        b"is overloaded or there is an error in the application.</p>\\n")


class Items(BaseHTTPRequestHandler):
    def _answer(self, status, raw, kind="application/json"):
        self.send_response(status)
        self.send_header("content-type", kind)
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _serve(self, method):
        try:
            if self.path == "/health":
                return self._answer(200, b'{"status": "ok"}')
            if self.path.rstrip("/") == "/items":
                return self._answer(200, json.dumps([]).encode())
            part = self.path.rsplit("/", 1)[1]
            if method == "DELETE":
                if not part.lstrip("-").isdigit():
                    return self._answer(404, b'{"error": "not found"}')
                gone = DB.execute("DELETE FROM items WHERE id = ?", (int(part),)).rowcount
                return self._answer(204 if gone else 404, b"" if gone else b'{"error": "not found"}')
            row = DB.execute("SELECT id, title FROM items WHERE id = ?", (int(part),)).fetchone()
            return self._answer(200 if row else 404, json.dumps(row or {"error": "not found"}).encode())
        except Exception:
            print(f"[2026-11-20 05:05:43,123] ERROR in app: Exception on {self.path} [{method}]", file=sys.stderr)
            traceback.print_exc()
            return self._answer(500, PAGE, "text/html; charset=utf-8")

    def do_GET(self):
        self._serve("GET")

    def do_DELETE(self):
        self._serve("DELETE")


ThreadingHTTPServer(("127.0.0.1", int(os.environ["PORT"])), Items).serve_forever()
'''


def _the_sandbox(argv, category, working_directory, *, root):
    """The probe's run, as the sandbox would make it: the project's interpreter is this one."""
    argv = [sys.executable if part == ".venv/bin/python" else part for part in argv]
    env = {**os.environ, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
    done = subprocess.run([*argv, "-o", "addopts="], cwd=root / working_directory, capture_output=True, text=True,
                          env=env, timeout=300)
    return {"returncode": str(done.returncode), "stdout": done.stdout, "stderr": done.stderr}


def _a_flask_project_on_sqlite(tmp_path, monkeypatch):
    """A workspace built from the Flask pack, its kept acceptance setup starting `PRODUCT` through `start.sh`."""
    pack = pack_named("python-flask-api")
    contract.write(tmp_path, pack, "items", "Items")
    project = tmp_path / "items"
    (project / "acceptance").mkdir(parents=True)
    (project / "acceptance" / "conftest.py").write_text(pack.files["acceptance/conftest.py"])
    (project / "product.py").write_text(PRODUCT)
    (project / "start.sh").write_text(f'#!/bin/sh\ncd "$(dirname "$0")" && exec {sys.executable} product.py\n')
    ic.record_at_lock(tmp_path, LINES)
    monkeypatch.setattr(suite, "_sandbox_runner", lambda root: lambda *a: _the_sandbox(*a, root=tmp_path))
    monkeypatch.setenv("EDGE_PROBE", "on")


def test_an_edge_probe_500_on_a_huge_id_names_the_error_the_server_printed_and_its_known_cause(tmp_path, monkeypatch):
    _a_flask_project_on_sqlite(tmp_path, monkeypatch)
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}
    green = SpecialistOutput(changed_files=[], defects=[], decisions=[])

    raised = workflow._with_an_edge_case_defect(state, green, SimpleNamespace(delegated_tasks=[], milestone_scope=[]))

    assert len(raised.defects) == 1
    defect = raised.defects[0]
    assert defect.description.startswith(ep.EDGE_CASES_FAILED)
    each = {part.split(" answered")[0]: part for part in defect.actual_behavior.split("; ")}
    huge = each["`DELETE /items/{id}` at id `99999999999999999999`"]
    assert "answered 500" in huge and "the server printed:" in huge and OVERFLOW in huge and "product.py" in huge
    assert "Exception on" not in huge and "ValueError" not in huge, "the traceback's exception, not the header line"
    assert "<!doctype" not in defect.description.lower() and "500 Internal Server Error" in huge
    not_a_number = each["`GET /items/{id}` at id `not-a-number`"]
    assert "ValueError: invalid literal for int()" in not_a_number and OVERFLOW not in not_a_number
    assert OVERFLOW in defect.description
    with_its_cause = with_known_causes(tmp_path, [defect])[0].actual_behavior
    assert KNOWN_CAUSE in with_its_cause and "9223372036854775807" in with_its_cause


def test_the_server_error_probe_names_what_the_server_printed_for_its_request(tmp_path, monkeypatch):
    _a_flask_project_on_sqlite(tmp_path, monkeypatch)

    errors = ic.server_errors(tmp_path)

    assert [(check.method, check.path, status) for check, status in errors] == [
        ("GET", f"/items/{ic.AN_ID_THAT_IS_NOT_A_NUMBER}", 500)]
    said = ic.what_a_server_error_said(tmp_path)
    assert said.startswith(f"`GET /items/{ic.AN_ID_THAT_IS_NOT_A_NUMBER}` answered 500")
    assert "the server printed:" in said and "ValueError: invalid literal for int()" in said
    assert "<!doctype" not in said.lower()
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}
    defect = workflow._with_a_server_error_defect(state, SpecialistOutput(changed_files=[], defects=[], decisions=[]),
                                                  SimpleNamespace(delegated_tasks=[], milestone_scope=[]),
                                                  errors).defects[0]
    assert "ValueError: invalid literal for int()" in defect.actual_behavior


def test_an_error_printed_after_its_access_line_is_tied_to_that_request_and_not_the_next():
    """An ASGI server prints the request's access line first and its traceback after it."""
    printed = "\n".join([
        'INFO:     127.0.0.1:5000 - "GET /items/abc HTTP/1.1" 404 Not Found',
        'INFO:     127.0.0.1:5000 - "DELETE /items/99999999999999999999 HTTP/1.1" 500 Internal Server Error',
        "ERROR:    Exception in ASGI application",
        "Traceback (most recent call last):",
        '  File "/venv/lib/python3.12/site-packages/starlette/routing.py", line 73, in app',
        '  File "/app/items/routes.py", line 40, in remove',
        "    db.execute(...)",
        OVERFLOW,
        'INFO:     127.0.0.1:5000 - "GET /items/-1 HTTP/1.1" 500 Internal Server Error',
        "ERROR:    Exception in ASGI application",
        "Traceback (most recent call last):",
        '  File "/app/items/routes.py", line 22, in read',
        "KeyError: -1",
    ])

    found = what_went_wrong.what_the_server_printed_for(printed, "/items/99999999999999999999", "DELETE")

    assert OVERFLOW in found and 'File "/app/items/routes.py", line 40' in found
    assert "KeyError" not in found and "site-packages" not in found
    assert what_went_wrong.what_the_server_printed_for(printed, "/items/abc", "GET") == ""


def test_a_javascript_error_names_the_frame_nearest_it():
    printed = ("Error: no such column: title\n    at Store.remove (/app/src/store.js:12:5)\n"
               "    at Router.handle (/app/src/routes.js:30:3)\n    at next (/app/node_modules/express/lib/router.js:9:1)\n")

    found = what_went_wrong.what_the_server_printed(printed)

    assert found == "Error: no such column: title (at Store.remove (/app/src/store.js:12:5))"


def _probed(printed):
    case = {"method": "DELETE", "shown": "/items/{id}", "path": "/items/99999999999999999999",
            "what": "at id `99999999999999999999`", "made_through": ""}
    page = ("<!doctype html> <html lang=en> <title>500 Internal Server Error</title> <h1>Internal Server Error</h1> "
            "<p>The server encountered an internal error and was unable to complete your request.")
    return ep.edge_description(ep.with_what_the_server_printed([(case, {"kind": "server_error", "status": 500,
                                                                         "said": page})], printed))


def test_an_edge_probe_500_whose_server_printed_nothing_names_only_the_answer():
    text = _probed("")

    assert "`DELETE /items/{id}` at id `99999999999999999999` answered 500 (it said: an HTML page, " in text
    assert "500 Internal Server Error" in text and "printed" not in text


def test_an_error_printed_for_no_named_request_is_shown_as_printed_while_the_probe_ran():
    text = _probed("Traceback (most recent call last):\n  File \"/app/items/store.py\", line 12, in remove\n"
                   f"{OVERFLOW}\n")

    assert f"while the probe ran, the server printed: {OVERFLOW} (File \"/app/items/store.py\", line 12" in text
    assert not BANNED.search(text)


def test_a_python_defect_carrying_the_sqlite_overflow_is_given_its_cause(tmp_path):
    contract.write(tmp_path, pack_named("python-http-api"), "items", "Items")
    defect = ReportedDefect(description=f"{ep.EDGE_CASES_FAILED} `DELETE /items/{{id}}` answered 500",
                            severity="major", reproduction_steps="send it", expected_behavior="a 404",
                            actual_behavior=f"answered 500 (the server printed: {OVERFLOW})", affected_files=[],
                            owner="backend")

    found = with_known_causes(tmp_path, [defect])[0].actual_behavior

    assert KNOWN_CAUSE in found and "-9223372036854775808" in found and "404" in found
    assert not BANNED.search(found)
