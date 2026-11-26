"""A sprint whose criteria already pass is not accepted before the harness's probes have run on its product (LF.1523).

Measured on one run of a service in parallel mode: sprint 1 built the routes sprint 2 was planned to add, so every
criterion due by sprint 2 passed when it opened. The sprint closed with nothing to build and went to its reviews with
no test round; the contract probes run only in a round, so none saw its routes. At release the edge probe found
`DELETE /items/{id}` answering 500 at id `99999999999999999999` (`OverflowError: Python int too large`), a gap no fixer
was ever given.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app.acceptance import interface_contract as ic
from app.acceptance import suite
from app.stacks import contract, pack_named

from workflow_nodes import a_lead, a_test_round

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
LINES = ["AC-13 GET /items -> 200", "AC-15 DELETE /items/{id} -> 204, 404"]
WHY = "Every criterion due by sprint 2 already passes (AC-13, AC-15), on a run of the acceptance suite made at the start."

#: The measured product's fault on the standard library: an id past 64 bits reaches SQLite and the handler answers 500.
PRODUCT = '''
import json, os, sqlite3, sys, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DB = sqlite3.connect(":memory:", check_same_thread=False)
DB.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, title TEXT, done INTEGER)")


class Items(BaseHTTPRequestHandler):
    def _answer(self, status, raw=b""):
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health":
            return self._answer(200, b'{"status": "ok"}')
        return self._answer(200, b"[]") if self.path.rstrip("/") == "/items" else self._answer(404, b"{}")

    def do_DELETE(self):
        part = self.path.rsplit("/", 1)[1]
        if not part.lstrip("-").isdigit():
            return self._answer(404, b'{"detail": "Not found"}')
        try:
            gone = DB.execute("DELETE FROM items WHERE id = ?", (int(part),)).rowcount
        except Exception:
            traceback.print_exc()
            return self._answer(500, b'{"detail": "Internal Server Error"}')
        return self._answer(204) if gone else self._answer(404, b'{"detail": "Not found"}')


ThreadingHTTPServer(("127.0.0.1", int(os.environ["PORT"])), Items).serve_forever()
'''


def _the_sandbox(argv, category, working_directory, *, root):
    """The probe's run, as the sandbox would make it: the project's interpreter is this one."""
    argv = [sys.executable if part == ".venv/bin/python" else part for part in argv]
    env = {**os.environ, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
    done = subprocess.run([*argv, "-o", "addopts="], cwd=root / working_directory, capture_output=True, text=True,
                          env=env, timeout=300)
    return {"returncode": str(done.returncode), "stdout": done.stdout, "stderr": done.stderr}


@pytest.fixture
def a_service_whose_delete_crashes_on_a_huge_id(tmp_path, monkeypatch):
    """A workspace from a Python service pack, its locked suite green, its product `PRODUCT` started by `start.sh`."""
    pack = pack_named("python-flask-api")
    contract.write(tmp_path, pack, "items", "Items")
    project = tmp_path / "items"
    (project / "acceptance").mkdir(parents=True)
    (project / "acceptance" / "conftest.py").write_text(pack.files["acceptance/conftest.py"])
    (project / "product.py").write_text(PRODUCT)
    (project / "start.sh").write_text(f'#!/bin/sh\ncd "$(dirname "$0")" && exec {sys.executable} product.py\n')
    suite.lock(tmp_path)
    ic.record_at_lock(tmp_path, LINES)
    monkeypatch.setattr(suite, "_sandbox_runner", lambda root: lambda *a: _the_sandbox(*a, root=tmp_path))
    monkeypatch.setenv("CONTRACT_SERVER_ERRORS_AT_A_ROUND", "on")
    monkeypatch.setenv("EDGE_PROBE", "on")
    return tmp_path


def _sprint_two_opens(root, **state):
    """The lead's node at sprint 2 of 2, every criterion due already passing."""
    return a_lead(root, None, state={"current_sprint_index": 1, "decisions": [], **state},
                  patches={"app.graph.acceptance_nodes.sprint_already_done": lambda state: WHY})


AFTER_A_REVIEW = {"milestone_review": SimpleNamespace(status="accepted")}


@pytest.mark.parametrize("before", [{}, AFTER_A_REVIEW], ids=["no review has read the code", "a review has"])
def test_a_sprint_with_nothing_to_build_goes_to_a_test_round_when_a_probe_finds_a_crash(
        a_service_whose_delete_crashes_on_a_huge_id, before):
    update, _ = _sprint_two_opens(a_service_whose_delete_crashes_on_a_huge_id, **before)

    assert update["stage"] == "test_and_triage"
    assert update["milestone_plan"].delegated_tasks == []
    assert update["milestone_plan"].selected_sprint_goal == "Users can share notes"
    (decision,) = update["decisions"]
    assert decision["point"] == "sprint" and decision["decision"] == "measure it in a test round first"
    assert "DELETE /items/{id}" in decision["rationale"] and WHY in decision["rationale"]


def test_the_round_it_goes_to_raises_the_crash_for_the_product_s_fixer(a_service_whose_delete_crashes_on_a_huge_id):
    root = a_service_whose_delete_crashes_on_a_huge_id
    closed, _ = _sprint_two_opens(root, **AFTER_A_REVIEW)

    update, asked = a_test_round(root, state={
        "current_sprint_index": 1, "milestone_plan": closed["milestone_plan"], "test_round": closed["test_round"]},
        patches={
            "app.graph.acceptance_nodes.suite.is_locked": lambda root: True,
            "app.graph.acceptance_nodes.suite.last_result": lambda root: {"ran": True, "passed": 27, "failed": 0},
            "app.graph.workflow._run_unit_tests_procedurally": lambda root: (True, ""),
        })

    assert asked == [], "the harness's own round: no model is asked"
    assert update["stage"] == "defect_remediation"
    (defect,) = [d for d in update["remediation"].defects if d.status == "open"]
    assert "`DELETE /items/{id}` at id `99999999999999999999`" in defect.actual_behavior
    assert "answered 500" in defect.actual_behavior and "OverflowError" in defect.actual_behavior
    assert defect.owner == "backend"


def test_a_probe_switched_off_is_not_asked_and_the_sprint_closes_as_before(
        a_service_whose_delete_crashes_on_a_huge_id, monkeypatch):
    from app.graph import delivery, engineering

    monkeypatch.setattr(delivery, "write_evidence", lambda *a, **k: None)
    monkeypatch.setattr(engineering, "accepted_state", lambda root: None)
    monkeypatch.setenv("EDGE_PROBE", "off")

    update, _ = _sprint_two_opens(a_service_whose_delete_crashes_on_a_huge_id, **AFTER_A_REVIEW)

    assert update["stage"] == "release"
    (decision,) = update["decisions"]
    assert decision["decision"] == "accept without new work"


def test_what_the_harness_says_of_such_a_sprint_uses_none_of_the_banned_words(a_service_whose_delete_crashes_on_a_huge_id):
    update, _ = _sprint_two_opens(a_service_whose_delete_crashes_on_a_huge_id)

    (note,) = update["milestone_plan"].integration_notes
    opening = update["decisions"][0]["rationale"].split("\n- ", 1)[0]
    assert not BANNED.search(note) and not BANNED.search(opening)
    assert not BANNED.search(update["decisions"][0]["decision"])
