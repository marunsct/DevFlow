"""At each test round the product's foundation is smoked, and while it fails only that is fixed (LF.1268).

Measured on a medium run: sign-up answered 500 for hours (its tables were never created), then the routes answered 404
under a doubled prefix, and 24 of 24 per-criterion fixers of a sprint worked on a product where no account could be
made; each was judged by the suite's pass count, which could not move. The smoke - the product answers, a fresh
account is made and signs in, one record is made and read back - runs against a small product on a local port, as the
pytest module it writes, the way the contract's other probes run.
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
from pathlib import Path
from types import SimpleNamespace

import pytest

import the_fix_stage
from workflow_nodes import a_test_round, reported

from app.acceptance import foundation_smoke as smoke
from app.acceptance import interface_contract as ic
from app.acceptance import suite
from app.acceptance.criteria import Criterion
from app.graph import start_first
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

LINES = ["AC-1 POST /api/signup -> 201", "AC-1 POST /api/signin -> 200", "AC-2 POST /api/items -> 201",
         "AC-2 GET /api/items -> 200", "AC-3 GET /api/items/{id} -> 200, 404"]
CRITERIA = [
    Criterion("AC-1", 'A visitor makes an account and signs in: POST /api/signup and POST /api/signin with '
                      '{"username": ..., "password": ...}; sign-in answers {"access_token": ...}.', "brief"),
    Criterion("AC-2", 'A signed-in user adds an item: POST /api/items with {"title": ...} answers 201.', "brief"),
    Criterion("AC-3", "A signed-in user reads one item with GET /api/items/{id}.", "brief"),
]
SPECIFICATION = SimpleNamespace(api_and_event_contracts=["Every /api/items call needs `Authorization: Bearer <token>`"])


class _Product(BaseHTTPRequestHandler):
    """Accounts and items behind a bearer token. `fault` makes sign-up fail on a missing table, or mounts every route
    under a doubled prefix."""

    fault = ""
    log_file: Path = Path()
    accounts: dict = {}
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

    def _route(self):
        if type(self).fault == "doubled prefix":
            return self.path[len("/api"):] if self.path.startswith("/api/api/") else ""
        return self.path

    def _signed_in(self):
        return (self.headers.get("authorization") or "") == "Bearer good-token"

    def do_GET(self):  # noqa: N802
        route = self._route()
        if route == "/api/items":
            return self._answer(200, list(type(self).items.values())) if self._signed_in() else self._answer(401, {})
        if route.startswith("/api/items/"):
            if not self._signed_in():
                return self._answer(401, {})
            found = type(self).items.get(route.rsplit("/", 1)[-1])
            return self._answer(200, found) if found else self._answer(404, {"detail": "no such item"})
        self._answer(404, {"detail": "Not Found"})

    def do_POST(self):  # noqa: N802
        route, cls = self._route(), type(self)
        body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
        if route == "/api/signup":
            if cls.fault == "no tables":
                with cls.log_file.open("a") as log:
                    log.write("INFO: POST /api/signup\nTraceback (most recent call last):\n"
                              '  File "app/routes/auth.py", line 12, in signup\n'
                              "sqlite3.OperationalError: no such table: users\n")
                return self._answer(500, {"detail": "Internal Server Error"})
            cls.accounts[body["username"]] = body["password"]
            return self._answer(201, {"username": body["username"]})
        if route == "/api/signin":
            if cls.accounts.get(body.get("username")) != body.get("password"):
                return self._answer(401, {"detail": "wrong username or password"})
            return self._answer(200, {"access_token": "good-token", "token_type": "bearer"})
        if route == "/api/items":
            if not self._signed_in():
                return self._answer(401, {})
            if not str(body.get("title") or "").strip():
                return self._answer(422, {"detail": "title is required"})
            made = {"id": len(cls.items) + 1, "title": body["title"]}
            cls.items[str(made["id"])] = made
            return self._answer(201, made)
        self._answer(404, {"detail": "Not Found"})


def _a_product(tmp_path, monkeypatch, fault=""):
    """A project whose suite is locked with `LINES` and `CRITERIA`, its product listening with `fault`."""
    project = tmp_path / "app"
    (project / "acceptance").mkdir(parents=True)
    (project / "test-results").mkdir()
    handler = type("Product", (_Product,), {"fault": fault, "accounts": {}, "items": {},
                                            "log_file": project / suite.SERVICE_LOG})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    (project / "acceptance" / "conftest.py").write_text(
        f"import pytest\n\n@pytest.fixture\ndef base_url():\n    return 'http://127.0.0.1:{server.server_port}'\n")
    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(probe_runner="pytest", kind="http_api"), {"project": "app"}))
    suite.save_criteria(tmp_path, CRITERIA)
    ic.record_at_lock(tmp_path, LINES, specification=SPECIFICATION)
    runs: list[list[str]] = []

    def run(argv, _kind, _project):
        runs.append(list(argv))
        env = {**os.environ, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
        done = subprocess.run([sys.executable, *argv[1:], "-o", "addopts="], cwd=project, capture_output=True,
                              text=True, env=env, timeout=180)
        return {"returncode": done.returncode, "stdout": done.stdout}

    # The sandbox is Docker; the module runs here instead, against the local product.
    monkeypatch.setattr(suite, "_sandbox_runner", lambda root: run)
    monkeypatch.setattr(suite, "is_locked", lambda root: True)
    return SimpleNamespace(root=tmp_path, run=run, runs=runs, server=server)


def _the_round(product, found):
    """A test round whose testing specialist reports `found`, on the locked suite of `product`."""
    update, _ = a_test_round(product.root, found, patches={
        "app.graph.acceptance_nodes.suite.is_locked": lambda root: True,
        "app.acceptance.suite.is_locked": lambda root: True,
    })
    return update["remediation"].defects


CRITERION_DEFECTS = [reported("[AC-2] An item can be added - the acceptance suite says this does not work yet."),
                     reported("[AC-3] An item can be read - the acceptance suite says this does not work yet.")]


def test_a_sign_up_that_fails_is_one_defect_and_every_other_waits(tmp_path, monkeypatch):
    product = _a_product(tmp_path, monkeypatch, fault="no tables")

    defects = _the_round(product, CRITERION_DEFECTS)

    smoked = [d for d in defects if smoke.is_a_smoke_defect(d)]
    assert len(smoked) == 1 and smoked[0].severity == "blocking" and smoked[0].status == "open"
    assert "`POST /api/signup` answered 500" in smoked[0].description
    assert "no such table: users" in smoked[0].actual_behavior, "the server's log is handed to the fixer"
    held = start_first.held_back(defects)
    assert held == {at for at, d in enumerate(defects) if not smoke.is_a_smoke_defect(d)} and len(held) == 2
    kept = json.loads((tmp_path / smoke.RECORD_FILE).read_text())
    assert (kept["held"], kept["step"], kept["status"]) == (False, "sign_up", 500)
    product.server.shutdown()


def test_routes_missing_at_the_contract_s_path_are_one_defect_naming_it(tmp_path, monkeypatch):
    product = _a_product(tmp_path, monkeypatch, fault="doubled prefix")

    result = smoke.run(product.root)

    assert (result.held, result.step, result.method, result.path, result.status) == (
        False, "sign_up", "POST", "/api/signup", 404)
    defect = smoke.a_defect(result, "backend")
    assert "`POST /api/signup` answered 404" in defect.description
    product.server.shutdown()


def test_a_create_missing_at_the_contract_s_path_names_it_after_the_account_steps(tmp_path, monkeypatch):
    """The account routes answer where the contract says; the record routes only under a doubled prefix."""
    product = _a_product(tmp_path, monkeypatch)
    product.server.RequestHandlerClass.fault = ""
    original = _Product._route

    def only_the_items_doubled(self):
        if self.path.startswith("/api/items"):
            return ""
        return original(self)

    monkeypatch.setattr(product.server.RequestHandlerClass, "_route", only_the_items_doubled)

    result = smoke.run(product.root)

    assert (result.held, result.step, result.path, result.status) == (False, "create", "/api/items", 404)
    assert result.passed == ["start", "sign_up", "sign_in"]
    product.server.shutdown()


def test_a_sound_product_holds_and_the_round_goes_on_as_before(tmp_path, monkeypatch):
    product = _a_product(tmp_path, monkeypatch)

    defects = _the_round(product, CRITERION_DEFECTS)

    assert not [d for d in defects if smoke.is_a_smoke_defect(d)]
    assert start_first.held_back(defects) == set()
    kept = json.loads((tmp_path / smoke.RECORD_FILE).read_text())
    assert kept["held"] is True and kept["passed"] == ["start", "sign_up", "sign_in", "create", "read"]
    product.server.shutdown()


def test_the_smoke_s_defect_is_closed_once_the_smoke_holds(tmp_path, monkeypatch):
    product = _a_product(tmp_path, monkeypatch, fault="no tables")
    failed = smoke.run(product.root)
    raised = smoke.a_defect(failed, "backend")
    assert ic.still_raised(product.root, raised.description) is True
    product.server.RequestHandlerClass.fault = ""

    assert ic.still_raised(product.root, raised.description) is False
    product.server.shutdown()


def test_a_command_line_product_is_not_smoked(tmp_path, monkeypatch):
    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(probe_runner="", kind="cli"), {"project": "app"}))
    (tmp_path / "app").mkdir()
    ic.record_at_lock(tmp_path, ["AC-1 command wordstats --help -> exit 0", "AC-2 command wordstats a.txt -> exit 0"])
    runs = []
    monkeypatch.setattr(suite, "_sandbox_runner", lambda root: lambda *argv: runs.append(argv) or {})
    monkeypatch.setattr(suite, "is_locked", lambda root: True)

    defects = _the_round(SimpleNamespace(root=tmp_path), CRITERION_DEFECTS)

    assert runs == [] and not [d for d in defects if smoke.is_a_smoke_defect(d)]
    assert start_first.held_back(defects) == set()


def test_a_create_a_later_sprint_builds_is_not_asked():
    lines = ic.parse(LINES)[0]
    bodies = [{"username": "ana", "password": "x"}, {"title": "milk"}]

    plan, _ = smoke.the_smoke(lines, bodies, due=["AC-1"])

    assert plan["sign_in"]["signup"] == "/api/signup" and plan["create"] is None


def test_a_contract_with_nothing_due_past_the_start_is_not_smoked():
    plan, why = smoke.the_smoke(ic.parse(LINES)[0], [{"title": "milk"}], due=[])

    assert plan is None and why


def test_while_the_smoke_s_defect_is_open_only_it_is_sent_a_fixer(tmp_path):
    criteria = [the_fix_stage.a_defect(f"[AC-{n}] criterion {n} fails", affected_files=[f"app/part{n}.js"],
                                       kind="failing_test") for n in range(1, 4)]
    failed = smoke.Result(held=False, step="sign_up", method="POST", path="/signup", status=500)
    foundation = the_fix_stage.a_defect(smoke.description(failed), affected_files=[], severity="blocking")
    state = the_fix_stage.a_state(tmp_path, *criteria[:2], foundation, criteria[2])

    _, seen = the_fix_stage.run(tmp_path, state)

    assert [stage for stage, _ in seen.shown] == ["defect_fix_2_2"]


def test_the_defect_text_holds_no_product_words():
    failed = smoke.Result(held=False, step="create", method="POST", path="/items", status=404, said="Not Found",
                          passed=["start", "sign_up", "sign_in"], server_log="INFO: POST /items 404")
    defect = smoke.a_defect(failed, "backend")

    assert not BANNED.search(" ".join([defect.description, defect.reproduction_steps, defect.expected_behavior,
                                       defect.actual_behavior]))


@pytest.mark.skipif(shutil.which("node") is None, reason="no node to read the spec")
def test_the_playwright_spec_is_javascript_node_can_read(tmp_path):
    plan, _ = smoke.the_smoke(ic.parse(LINES)[0], [{"username": "ana", "password": "x"}, {"title": "milk"}])
    (tmp_path / "smoke.spec.mjs").write_text(smoke.playwright_smoke([plan]))

    done = subprocess.run(["node", "--check", str(tmp_path / "smoke.spec.mjs")], capture_output=True, text=True)

    assert done.returncode == 0, done.stderr


def test_a_round_whose_suite_passes_asks_no_smoke(tmp_path, monkeypatch):
    """A small product's green round is as it always was: no smoke run to wait for."""
    product = _a_product(tmp_path, monkeypatch, fault="no tables")

    update, _ = a_test_round(product.root, [], patches={
        "app.graph.acceptance_nodes.suite.is_locked": lambda root: True,
        "app.acceptance.suite.is_locked": lambda root: True,
        "app.graph.acceptance_nodes.suite.last_result": lambda root: {"ran": True, "passed": 5, "failed": 0},
    })

    defects = getattr(update.get("remediation"), "defects", [])
    assert not [d for d in defects if smoke.is_a_smoke_defect(d)]
    assert json.loads((tmp_path / smoke.RECORD_FILE).read_text())["passed"] == [], "no smoke step was asked"
    product.server.shutdown()


def test_the_next_round_s_smoke_that_holds_closes_the_defect_and_releases_the_others(tmp_path, monkeypatch):
    product = _a_product(tmp_path, monkeypatch, fault="no tables")
    patches = {"app.graph.acceptance_nodes.suite.is_locked": lambda root: True,
               "app.acceptance.suite.is_locked": lambda root: True}
    first, _ = a_test_round(product.root, CRITERION_DEFECTS, patches=patches)
    product.server.RequestHandlerClass.fault = ""

    update, _ = a_test_round(product.root, CRITERION_DEFECTS, patches=patches,
                             state={"remediation": first["remediation"], "test_round": 2})

    defects = update["remediation"].defects
    assert [d.status for d in defects if smoke.is_a_smoke_defect(d)] == ["fixed"]
    assert start_first.held_back(defects) == set()
    product.server.shutdown()
