"""Every body probe signs in with the sign-up body the criteria write, and reaches the writes behind the sign-in.

Measured on one run: a Python HTTP API behind sign-in - `POST /signup` and `POST /signin` with
`{"username": ..., "password": ...}`, `/items` only with `Authorization: Bearer <token>` - shipped two hidden quality
failures: a title of only spaces was taken, and items created at the same moment were not all kept. The release
probes that exist for both never reached `POST /items`: the bodies were written in the brief's criteria, the probes
took theirs from the specification only, and so they had no body carrying a password, signed in as no one and were
answered 401 ("sign-in answered first"); the emptied-field probe found no body carrying a title. Apart from that, the
bad-body probe signed in only with the bodies a record-making write carried, so a create on a contract with no update
was asked signed in as no one even when the example bodies held the sign-up body.

Each probe here runs as the pytest module it writes, against a small product on a local port that answers 401
without a token.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from app.acceptance import concurrent_write_probe as cw
from app.acceptance import interface_contract as ic
from app.acceptance import suite
from app.acceptance import wrong_shape_body_probe as ws
from app.acceptance.criteria import Criterion
from app.stacks import contract

LINES = ["AC-1 POST /signup -> 201", "AC-2 POST /signin -> 200", "AC-3 POST /items -> 201", "AC-4 GET /items -> 200",
         "AC-5 PATCH /items/{id} -> 200, 404"]
CRITERIA = [
    Criterion("AC-1", 'A visitor makes an account and signs in: POST /signup and POST /signin with '
                      '{"username": ..., "password": ...}; sign-in answers {"token": ...}.', "brief"),
    Criterion("AC-3", 'A signed-in user adds an item: POST /items with {"title": ...} answers 201; a title that is '
                      'empty or only spaces is refused.', "brief"),
    Criterion("AC-4", "A signed-in user lists their items with GET /items.", "brief"),
]
#: A specification that names the routes but does not repeat the bodies the criteria write.
SPECIFICATION = SimpleNamespace(api_and_event_contracts=[
    "POST /items creates an item for the signed-in user and answers 201 with the item",
    "Every /items call needs `Authorization: Bearer <token>` and answers 401 without it",
])


class _Product(BaseHTTPRequestHandler):
    """Accounts and items behind a bearer token, with the faults the probes exist for: a title of spaces is taken,
    the store is not serialised, and a body that is not a JSON object makes the item routes fail."""

    accounts: dict = {}
    tokens: set = set()
    items: dict = {}

    def log_message(self, *args):  # noqa: D401 - quiet
        pass

    def _answer(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        return self.rfile.read(int(self.headers.get("content-length") or 0))

    def _signed_in(self):
        return (self.headers.get("authorization") or "").removeprefix("Bearer ") in type(self).tokens

    def _a_title(self, raw):
        found = json.loads(raw or b"{}")  # unparsable bytes raise: a server failure
        return found["title"]  # a body that is not an object raises too

    def do_GET(self):  # noqa: N802
        if not self._signed_in():
            return self._answer(401, {"detail": "not signed in"})
        self._answer(200, [{"id": k, "title": v} for k, v in sorted(type(self).items.items())])

    def do_POST(self):  # noqa: N802
        raw, cls = self._body(), type(self)
        if self.path in ("/signup", "/signin"):
            try:
                found = json.loads(raw)
                username, password = found["username"], found["password"]
            except (ValueError, KeyError, TypeError):
                return self._answer(400, {"detail": "username and password are required"})
            if self.path == "/signup":
                cls.accounts[username] = password
                return self._answer(201, {"username": username})
            if cls.accounts.get(username) != password:
                return self._answer(401, {"detail": "wrong username or password"})
            token = f"t{len(cls.tokens) + 1}"
            cls.tokens.add(token)
            return self._answer(200, {"token": token})
        if not self._signed_in():
            return self._answer(401, {"detail": "not signed in"})
        try:
            title = self._a_title(raw)
        except KeyError:
            return self._answer(400, {"detail": "title is required"})
        except Exception:  # noqa: BLE001 - the fault: a body it cannot read fails the server
            return self._answer(500, {"detail": "internal error"})
        if title == "":
            return self._answer(400, {"detail": "title is required"})
        new = len(cls.items) + 1
        time.sleep(0.3)  # read, wait, write: creates at the same moment share an id
        cls.items[new] = title
        self._answer(201, {"id": new, "title": title})

    def do_PATCH(self):  # noqa: N802
        if not self._signed_in():
            return self._answer(401, {"detail": "not signed in"})
        try:
            title = self._a_title(self._body())
        except KeyError:
            return self._answer(400, {"detail": "title is required"})
        except Exception:  # noqa: BLE001 - the fault
            return self._answer(500, {"detail": "internal error"})
        number = int(self.path.rsplit("/", 1)[-1]) if self.path.rsplit("/", 1)[-1].isdigit() else 0
        if number not in type(self).items:
            return self._answer(404, {"detail": "no such item"})
        if title == "":
            return self._answer(400, {"detail": "title is required"})
        type(self).items[number] = title
        self._answer(200, {"id": number, "title": title})


@pytest.fixture
def product(tmp_path, monkeypatch):
    """A project whose suite is locked with `LINES` and `CRITERIA`, its product listening; the runner runs the probe."""
    handler = type("Product", (_Product,), {"accounts": {}, "tokens": set(), "items": {}})
    server = type("Server", (ThreadingHTTPServer,), {"request_queue_size": 64})(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    project = tmp_path / "app"
    (project / "acceptance").mkdir(parents=True)
    (project / "acceptance" / "conftest.py").write_text(
        f"import pytest\n\n@pytest.fixture\ndef base_url():\n    return 'http://127.0.0.1:{server.server_port}'\n")
    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(probe_runner="pytest"), {"project": "app"}))
    for switch in ("CONCURRENT_WRITE_PROBE", "CONTRACT_PROBE_WITH_A_BAD_BODY", "WRONG_SHAPE_BODY_PROBE"):
        monkeypatch.setenv(switch, "on")
    suite.save_criteria(tmp_path, CRITERIA)

    def run(argv, _kind, _project):
        env = {**os.environ, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
        done = subprocess.run([sys.executable, *argv[1:], "-o", "addopts="], cwd=project, capture_output=True,
                              text=True, env=env, timeout=180)
        return {"returncode": done.returncode, "stdout": done.stdout}

    yield SimpleNamespace(root=tmp_path, run=run)
    server.shutdown()


def test_the_concurrent_write_probe_signs_in_and_finds_creates_that_share_an_id(product):
    ic.record_at_lock(product.root, LINES, specification=SPECIFICATION)

    errors = cw.concurrent_write_errors(product.root, runner=product.run)

    assert [(c.method, c.path) for c, _ in errors] == [("POST", "/items")]
    assert errors[0][1]["same_id"]


def test_a_lock_that_kept_no_bodies_still_signs_the_probe_in_with_the_criteria_s(product):
    """A suite locked before the criteria were read for bodies, as a run already under way has it."""
    ic.record_at_lock(product.root, LINES, specification=SPECIFICATION)
    suite._save_state(product.root, {**suite._state(product.root), "interface_contract_bodies": []})  # noqa: SLF001

    errors = cw.concurrent_write_errors(product.root, runner=product.run)

    assert [(c.method, c.path) for c, _ in errors] == [("POST", "/items")]


def test_the_emptied_field_probe_signs_in_and_finds_a_title_of_only_spaces_taken(product):
    ic.record_at_lock(product.root, LINES, specification=SPECIFICATION)

    accepted = ic.emptied_field_errors(product.root, runner=product.run)

    assert {(c.method, c.path, c.emptied, c.blank) for c, _ in accepted} == {
        ("POST", "/items", "title", True), ("PATCH", "/items/{id}", "title", True)}


def test_the_wrong_shape_probe_signs_in_and_finds_the_item_routes_failing(product):
    ic.record_at_lock(product.root, LINES, specification=SPECIFICATION)

    errors = ws.wrong_shape_errors(product.root, runner=product.run)

    assert {(c.method, c.path) for c, _, _ in errors} == {("POST", "/items"), ("PATCH", "/items/{id}")}


def test_the_bad_body_probe_signs_in_and_finds_the_item_routes_failing(product):
    ic.record_at_lock(product.root, LINES, specification=SPECIFICATION)

    errors = ic.bad_body_errors(product.root, runner=product.run)

    assert {(c.method, c.path) for c, _ in errors} == {("POST", "/items"), ("PATCH", "/items/{id}")}


def test_the_bad_body_probe_of_a_create_signs_in_on_a_contract_with_no_update(product):
    """The sign-up body is among the example bodies, but no write the probe asks makes a record to carry it."""
    specification = SimpleNamespace(api_and_event_contracts=[
        'POST /signup with {"username": "ana", "password": "correct horse"} answers 201',
        'POST /items with {"title": "milk"} answers 201',
    ])
    ic.record_at_lock(product.root, LINES[:4], specification=specification)

    errors = ic.bad_body_errors(product.root, runner=product.run)

    assert [(c.method, c.path) for c, _ in errors] == [("POST", "/items")]


def test_a_sign_up_body_past_the_cap_is_kept_beside_every_record_body():
    record_bodies = [{"title": "milk"}, {"name": "home"}, {"text": "hello"}, {"title": "eggs", "done": True}]
    specification = SimpleNamespace(api_and_event_contracts=[
        'POST /items with {"title": "milk"}', 'POST /lists with {"name": "home"}', 'POST /notes with {"text": "hello"}',
        'PUT /items/{id} with {"title": "eggs", "done": true}',
        'POST /signup with {"username": "ana", "password": "correct horse"}',
    ])

    bodies = ic.example_bodies(specification)

    assert {"username": "ana", "password": "correct horse"} in bodies
    assert all(body in bodies for body in record_bodies)
