"""A contract line naming several methods, or saying what it is for before its arrow, is read and checked.

Measured on one run: six of eight lines were written as `AC-10, AC-3 GET/PUT/DELETE /notes/{id} for non-existent ->
404` or `AC-13 POST/PUT /notes with invalid title -> 400 or 422`; none followed a form, none was checked at release,
and the round's server-error checks had nothing to send.
"""
from __future__ import annotations

import inspect

from app.acceptance import interface_contract as ic
from app.graph import workflow

LINES = [
    "AC-10, AC-3, AC-4, AC-5 GET/PUT/DELETE /notes/{id} for non-existent -> 404",
    "AC-13, AC-18 POST/PUT /notes/{id} with invalid title -> 400 or 422",
    "AC-13 POST /notes with invalid title -> 400 or 422",
    "AC-1 POST /notes -> 201",
]


def test_each_method_of_a_line_is_its_own_check_with_the_line_s_note():
    checks, unreadable = ic.parse(LINES)
    assert unreadable == []
    assert [(c.method, c.path, c.statuses, c.note) for c in checks[:3]] == [
        ("GET", "/notes/{id}", (404,), "for non-existent"),
        ("PUT", "/notes/{id}", (404,), "for non-existent"),
        ("DELETE", "/notes/{id}", (404,), "for non-existent"),
    ]
    assert checks[0].criterion == "AC-10" and checks[-1].note == ""


def test_a_line_about_another_request_is_probed_for_server_errors_but_not_judged_on_its_status(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.stacks import contract

    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(files={"playwright.config.js": ""}, probe_runner="playwright"), {"project": "app"}))
    (tmp_path / "app").mkdir()
    ic.record_at_lock(tmp_path, ["AC-9 POST /signup (duplicate) -> 409", "AC-13 POST/PUT /notes/{id} with invalid title -> 400"])
    web = ic.checkable(ic.the_locked_contract(tmp_path))
    assert [(c.method, c.path) for c in web] == [("POST", "/signup"), ("POST", "/notes/999999999"), ("PUT", "/notes/999999999")]

    def runner(argv, category, where):
        (tmp_path / where / "test-results").mkdir(exist_ok=True)
        (tmp_path / where / ic.REPORT_FILE).write_text(
            '<testsuites><testsuite name="c" tests="3">'
            '<testcase name="[AC-9] contract 1: AC-9 POST /signup (duplicate) -&gt; 409"><failure message="x">Received: 422</failure></testcase>'
            '<testcase name="[AC-13] contract 2: x"><failure message="x">Received: 404</failure></testcase>'
            '<testcase name="[AC-13] contract 3: x"><failure message="x">Received: 500</failure></testcase>'
            "</testsuite></testsuites>")
        return {"returncode": "1"}

    gaps = ic.what_the_contract_checks_find(tmp_path, runner=runner)
    failed = [g for g in gaps if "does not keep its interface contract" in g]
    assert len(failed) == 1 and "contract 3" in failed[0]
    unchecked = [g for g in gaps if "were not checked at release" in g]
    assert len(unchecked) == 1 and "the line is about (duplicate)" in unchecked[0] and "about with invalid title" in unchecked[0]
    assert [(c.method, s) for c, s in ic.server_errors(tmp_path, runner=runner)] == [("PUT", 500)]


def test_a_recorded_contract_without_notes_still_reads(tmp_path):
    check = ic.Check(**{"criterion": "AC-1", "kind": "http", "line": "AC-1 GET /x -> 200", "method": "GET", "path": "/x",
                        "status": 200, "statuses": [200], "role": "", "name": "", "command": "", "exit_code": 0})
    assert check.note == ""


def test_the_round_asks_whenever_the_suite_is_green():
    source = inspect.getsource(workflow)
    assert ('        if not failing_due and int(saved_run.get("failed") or 0) == 0:\n'
            "            test_result = _with_the_contract_s_server_errors(state, test_result, milestone)") in source
