"""A contract line naming several methods, or saying what it is for before its arrow, is read and checked.

Measured on one run: six of eight lines were written as `AC-10, AC-3 GET/PUT/DELETE /notes/{id} for non-existent ->
404` or `AC-13 POST/PUT /notes with invalid title -> 400 or 422`; none followed a form, none was checked at release,
and the round's server-error checks had nothing to send.
"""
from __future__ import annotations

from types import SimpleNamespace

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


def _a_round_after_a_green_suite(tmp_path, *, failed: int):
    """The test round's node run on a locked suite that ran with `failed` failures, its unit tests failing.

    Returns how often the round asked for the contract's server errors.
    """
    from unittest.mock import patch

    from langgraph.checkpoint.memory import MemorySaver

    from app.agents.specialists import SpecialistOutput

    milestone = SimpleNamespace(selected_sprint_goal="Build features", milestone_scope=[], delegated_tasks=[])
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)), "milestone_plan": milestone, "test_round": 1,
        "specialist_outputs": {}, "review_defects": [], "current_sprint_index": 0,
    }
    unit_failure = workflow._the_unit_tests_fail(milestone, "AssertionError: expected 2, got 3")
    asked = []

    def contract_checks(state, test_result, milestone):
        asked.append(test_result)
        return test_result

    with patch("app.graph.acceptance_nodes.acceptance_for_round", return_value=("", [])), \
         patch("app.graph.acceptance_nodes.reopen_the_suite_for", return_value=None), \
         patch("app.graph.acceptance_nodes.beyond_repair", return_value=[]), \
         patch("app.graph.acceptance_nodes._failing_due", return_value=([], "npx playwright test")), \
         patch("app.graph.workflow._run_unit_tests_procedurally", return_value=(False, "AssertionError")), \
         patch("app.graph.acceptance_nodes.suite.is_locked", return_value=True), \
         patch("app.graph.acceptance_nodes.suite.last_result",
               return_value={"ran": True, "passed": 9 - failed, "failed": failed}), \
         patch("app.agents.specialists.what_the_files_already_prove", return_value=[]), \
         patch("app.graph.acceptance_nodes.interface_defects", return_value=[]), \
         patch("app.graph.acceptance_nodes.failing_due_defects", return_value=[]), \
         patch("app.acceptance.order_probe.at_a_green_round"), \
         patch("app.graph.workflow._with_the_contract_s_server_errors", side_effect=contract_checks), \
         patch("app.graph.workflow._run_gated_agent",
               return_value={"__test_result__": SpecialistOutput(changed_files=[], defects=[unit_failure])}):
        graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(tmp_path))
        graph.nodes["test_and_triage"].bound.invoke(state, {"configurable": {"thread_id": "t", "run_id": "r"}})
    return asked


def test_the_round_asks_whenever_the_suite_is_green(tmp_path):
    """Asked whenever the locked suite is green, whatever else the round found.

    Measured on one run, failing unit tests kept every round from being clean and the checks were never asked
    before release. A red suite has its own defects, and is not asked; a near-green one is (LF.1052).
    """
    [asked] = _a_round_after_a_green_suite(tmp_path, failed=0)
    assert [d.description for d in asked.defects][0].startswith(workflow.UNIT_TESTS_FAIL), "asked beside the unit failure"

    assert _a_round_after_a_green_suite(tmp_path, failed=3) == []


def test_a_note_among_the_statuses_is_no_part_of_the_check():
    checks, unreadable = ic.parse([
        "AC-1 POST /notes -> 201 (with Note object) or 400/422",
        "AC-3 GET /notes/{id} -> 200 (with Note object) or 404",
    ])
    assert unreadable == []
    assert [(c.method, c.statuses) for c in checks] == [("POST", (201, 400, 422)), ("GET", (200, 404))]


def test_a_status_only_a_particular_request_draws_is_unchecked_not_failed(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.stacks import contract

    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(files={"playwright.config.js": ""}, probe_runner="playwright"), {"project": "app"}))
    (tmp_path / "app").mkdir()
    ic.record_at_lock(tmp_path, ["AC-18 POST /notes -> 413", "AC-20 GET /admin -> 401"])

    def runner(argv, category, where):
        (tmp_path / where / "test-results").mkdir(exist_ok=True)
        (tmp_path / where / ic.REPORT_FILE).write_text(
            '<testsuites><testsuite name="c" tests="2">'
            '<testcase name="[AC-18] contract 1: x"><failure message="x">Expected: 413\nReceived: 400</failure></testcase>'
            '<testcase name="[AC-20] contract 2: x"><failure message="x">Expected: 401\nReceived: 200</failure></testcase>'
            "</testsuite></testsuites>")
        return {"returncode": "1"}

    gaps = ic.what_the_contract_checks_find(tmp_path, runner=runner)
    failed = [g for g in gaps if "does not keep its interface contract" in g]
    assert len(failed) == 1 and "contract 2" in failed[0]
    assert any("AC-18 POST /notes -> 413 (the probe sends a bare request" in g for g in gaps)


def test_a_bodiless_write_refused_for_its_body_is_unchecked_not_failed(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.stacks import contract

    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(files={"playwright.config.js": ""}, probe_runner="playwright"), {"project": "app"}))
    (tmp_path / "app").mkdir()
    ic.record_at_lock(tmp_path, ["AC-11 PUT /notes/999 -> 404", "AC-3 GET /notes/999 -> 404"])

    def runner(argv, category, where):
        (tmp_path / where / "test-results").mkdir(exist_ok=True)
        (tmp_path / where / ic.REPORT_FILE).write_text(
            '<testsuites><testsuite name="c" tests="2">'
            '<testcase name="[AC-11] contract 1: x"><failure message="x">Expected: 404\nReceived: 400</failure></testcase>'
            '<testcase name="[AC-3] contract 2: x"><failure message="x">Expected: 404\nReceived: 400</failure></testcase>'
            "</testsuite></testsuites>")
        return {"returncode": "1"}

    gaps = ic.what_the_contract_checks_find(tmp_path, runner=runner)
    failed = [g for g in gaps if "does not keep its interface contract" in g]
    assert len(failed) == 1 and "contract 2" in failed[0]  # a GET has no body to refuse
    assert any("AC-11 PUT /notes/999 -> 404 (the probe sends a bare request" in g for g in gaps)


def test_a_line_with_no_criterion_is_checked_and_charges_none():
    """Measured on the held-out family: `GET /health -> 200` was set aside as following no form and never probed."""
    checks, unreadable = ic.parse(["GET /health -> 200", "AC-1 POST /signup -> 201"])
    assert unreadable == []
    assert [(c.criterion, c.method, c.path, c.statuses) for c in checks][0] == ("", "GET", "/health", (200,))
    spec = ic.playwright_checks(ic.checkable(checks))
    assert '"contract 1: GET /health -> 200"' in spec and "[] contract" not in spec


def test_a_bare_write_refused_with_the_other_refusal_is_unchecked_not_failed(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.stacks import contract

    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(files={"playwright.config.js": ""}, probe_runner="playwright"), {"project": "app"}))
    (tmp_path / "app").mkdir()
    ic.record_at_lock(tmp_path, ["AC-7 POST /notes -> 400"])

    def runner(argv, category, where):
        (tmp_path / where / "test-results").mkdir(exist_ok=True)
        (tmp_path / where / ic.REPORT_FILE).write_text(
            '<testsuites><testsuite name="c" tests="1">'
            '<testcase name="[AC-7] contract 1: x"><failure message="x">Expected: 400\nReceived: 422</failure></testcase>'
            "</testsuite></testsuites>")
        return {"returncode": "1"}

    # Measured on one run: the probe's bodiless request drew 422 where the line said 400; the brief allows either.
    gaps = ic.what_the_contract_checks_find(tmp_path, runner=runner)
    assert not [g for g in gaps if "does not keep its interface contract" in g]
    assert any("AC-7 POST /notes -> 400 (the probe sends a bare request" in g for g in gaps)
