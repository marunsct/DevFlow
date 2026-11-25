"""A fixer is shown its criterion's tests run on their own, a server error nothing logged comes first, and a test no
fix in this sprint can make pass goes to the QA lead before the fixer (FX.1, FX.7, FX.11; LF.1410, LF.1411, LF.1413).

Measured on a medium run, where two fixers spent 46 minutes on one criterion and changed nothing:

- a criterion's brief said its sign-in tests received 429; run on their own they received 500 - the whole suite's
  earlier tests had used up the product's sign-up limit;
- every registration answered 500 and the server's log held only access lines, so no fixer saw the exception;
- three of the criterion's tests called a route only a later sprint's criteria name (404), and the fixers were sent at
  them anyway.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import the_fix_stage
from app.acceptance import per_file, sprint_scope, suite
from app.acceptance.criteria import Criterion
from app.sprint import Defect

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
PROJECT = "items-api"
RECORD = {"pack": "a-pack-this-host-does-not-have", "project": PROJECT, "acceptance_dir": "acceptance",
          "acceptance_pattern": "*.spec.js", "acceptance_report": "test-results/acceptance.xml",
          "acceptance_test": ["npm", "run", "test:acceptance"]}
SUITE = """
test('[AC-3] signs in and lists the items', async ({ request }) => {
  const response = await request.post('/api/login', { data: { email: 'a@b.c', password: 'pw' } });
  expect(response.status()).toBe(200);
});
test('[AC-3] lists the orders of the user', async ({ request }) => {
  const response = await request.get('/api/orders');
  expect(response.status()).toBe(401);
});
test('[AC-3] lists the items', async ({ request }) => {
  const response = await request.get('/api/items');
  expect(response.status()).toBe(200);
});
"""
#: What the suite's last run, the whole suite at once, said of the sign-in test.
STALE_429 = "Error: expect(received).toBe(expected)\n\n    Expected: 200\n    Received: 429\n"


def _failed(status: int, expected: int = 200) -> str:
    return f"Error: expect(received).toBe(expected) // Object.is equality\n\n    Expected: {expected}\n    Received: {status}\n"


def _report(outcomes: dict[str, str | None]) -> str:
    cases = "".join(
        f'<testcase name="{name}" classname="items.spec.js">'
        + (f'<failure message="failed">{message}</failure>' if message else "") + "</testcase>"
        for name, message in outcomes.items())
    return f'<?xml version="1.0"?><testsuites><testsuite name="items.spec.js">{cases}</testsuite></testsuites>'


def _a_workspace(root: Path, *, later: bool = True) -> Path:
    """A product whose suite holds AC-3's tests; AC-5, a later sprint's, is the one that names orders."""
    (root / ".harness").mkdir(parents=True, exist_ok=True)
    (root / ".harness" / "stack-pack.json").write_text(json.dumps(RECORD))
    (root / PROJECT / "acceptance").mkdir(parents=True)
    (root / PROJECT / "acceptance" / "items.spec.js").write_text(SUITE)
    suite.save_criteria(root, [Criterion("AC-3", "A signed-in user sees the items", "brief"),
                               Criterion("AC-5", "A user places orders and lists the orders", "brief")])
    sprint_scope.record(root, sprint=0, of=2, not_yet_due=["AC-5"] if later else [])
    (root / suite.RESULT_FILE).write_text(json.dumps({
        "ran": True, "server_log": "",
        "criteria": {"AC-3": {"id": "AC-3", "text": "A signed-in user sees the items", "status": "failed", "tests": [
            {"name": "[AC-3] signs in and lists the items", "outcome": "failed", "message": STALE_429}]}}}))
    per_file.forget_runs()
    return root


def _the_runner(root: Path, outcomes: dict[str, str | None], server_said: str):
    """The sandbox, running one acceptance file: its report and what it printed, the server's lines among them."""
    def run(argv, category, project):
        run.commands.append(list(argv))
        report = root / PROJECT / "test-results" / "acceptance.xml"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(_report(outcomes))
        printed = "\n".join(f"[WebServer] {line}" for line in server_said.splitlines())
        return {"returncode": 1, "stdout": f"Running 3 tests\n{printed}\n  2 failed\n"}
    run.commands = []
    return run


def _defect() -> Defect:
    return Defect(description="[AC-3] A signed-in user sees the items - the acceptance suite says this does not work "
                              "yet.",
                  severity="major", reproduction_steps="Run the acceptance suite and read the AC-3 tests.",
                  expected_behavior="A signed-in user sees the items",
                  actual_behavior="[AC-3] signs in and lists the items: Expected: 200; Received: 429",
                  owner="backend", affected_files=[], found_in_round=1)


ACCESS_LINES_ONLY = ('INFO:     127.0.0.1:5000 - "POST /api/login HTTP/1.1" 500 Internal Server Error\n'
                     'INFO:     127.0.0.1:5001 - "GET /api/items HTTP/1.1" 404 Not Found')
WITH_A_TRACE = ("Traceback (most recent call last):\n"
                '  File "/workspace/items-api/app/routes/auth.py", line 41, in login\n'
                "    user = users.find(email)\n"
                "sqlite3.OperationalError: no such table: users\n" + ACCESS_LINES_ONLY)


def _fixed(root: Path, monkeypatch, outcomes, server_said, *, dispute: bool = False, during=None, specification=""):
    runner = _the_runner(root, outcomes, server_said)
    monkeypatch.setattr("app.stacks.scaffold.sandbox_runner", lambda repo_root: runner)
    monkeypatch.setattr("app.graph.workflow._a_dispute_may_be_held_now", lambda state, also=None: dispute)
    state = the_fix_stage.a_state(root, _defect(), technical_specification=specification)
    update, seen = the_fix_stage.run(root, state, real_brief=True, during=during)
    return update, seen, runner


RUN_ALONE = {"[AC-3] signs in and lists the items": _failed(500), "[AC-3] lists the orders of the user": None,
             "[AC-3] lists the items": None}


def test_the_fixer_is_shown_what_its_tests_do_on_their_own_now(tmp_path, monkeypatch):
    root = _a_workspace(tmp_path)

    _, seen, runner = _fixed(root, monkeypatch, RUN_ALONE, WITH_A_TRACE)

    request = seen.requests[0]
    fresh = request[request.index("run on their own just now"):]
    # The run on its own received 500, where the whole suite's run said 429.
    assert "Received: 500" in fresh and "Received: 429" not in fresh
    assert "`[AC-3] signs in and lists the items`" in fresh
    # The server's error from that run.
    assert "sqlite3.OperationalError: no such table: users" in fresh
    # Only the file holding the criterion's tests ran, as the suite's command runs one file.
    assert runner.commands and all(c[-1].endswith("acceptance/items.spec.js") for c in runner.commands)
    assert not BANNED.search(fresh)


def test_a_server_error_nothing_logged_is_the_first_thing_the_fixer_is_asked_to_fix(tmp_path, monkeypatch):
    root = _a_workspace(tmp_path)

    _, seen, _ = _fixed(root, monkeypatch, RUN_ALONE, ACCESS_LINES_ONLY)

    request = seen.requests[0]
    asked = " ".join(request[request.index("The server error behind this failure is not logged"):].split())
    assert "`[AC-3] signs in and lists the items` received 500" in asked
    assert "log the exception with its full trace" in asked
    assert "Then run the failing test and read the trace the server prints" in asked
    assert not BANNED.search(asked)


def test_a_server_error_the_server_logged_asks_for_no_log_line(tmp_path, monkeypatch):
    root = _a_workspace(tmp_path)

    _, seen, _ = _fixed(root, monkeypatch, RUN_ALONE, WITH_A_TRACE)

    assert "is not logged" not in seen.requests[0]


def test_after_a_kept_write_the_fixer_is_told_its_first_failure_and_the_server_s_error(tmp_path, monkeypatch):
    from langchain_core.messages import ToolMessage

    from app.graph import verify_after_write

    monkeypatch.setenv("VERIFY_AFTER_WRITE", "on")
    root = _a_workspace(tmp_path)

    def a_write(stage):
        written = ToolMessage(content="Edited app/routes/auth.py", tool_call_id="1")
        return verify_after_write.after_a_write("edit_artifact", written, "r", stage).content

    _, seen, _ = _fixed(root, monkeypatch, RUN_ALONE, WITH_A_TRACE, during=a_write)

    reply = seen.during[0]
    told = reply[reply.index("they still fail"):]
    assert "`[AC-3] signs in and lists the items`" in told and "Received: 500" in told
    assert "sqlite3.OperationalError: no such table: users" in told
    assert len(told) <= 1_600
    assert not BANNED.search(told)


def test_after_a_kept_write_a_server_error_still_unlogged_is_said(tmp_path, monkeypatch):
    from langchain_core.messages import ToolMessage

    from app.graph import verify_after_write

    monkeypatch.setenv("VERIFY_AFTER_WRITE", "on")
    root = _a_workspace(tmp_path)

    def a_write(stage):
        written = ToolMessage(content="Edited app/routes/auth.py", tool_call_id="1")
        return verify_after_write.after_a_write("edit_artifact", written, "r", stage).content

    _, seen, _ = _fixed(root, monkeypatch, RUN_ALONE, ACCESS_LINES_ONLY, during=a_write)

    assert "still logs no error for `[AC-3] signs in and lists the items`" in seen.during[0]


LATER_AND_LIMITED = {"[AC-3] signs in and lists the items": _failed(429),
                     "[AC-3] lists the orders of the user": _failed(404, 401),
                     "[AC-3] lists the items": _failed(404)}
SETS_A_LIMIT = {"non_functional_requirements": ["Sign-in is rate limited to 5 requests per minute; "
                                                "past it the service answers 429."]}


def test_tests_no_fix_in_this_sprint_can_make_pass_go_to_the_lead_before_a_fixer(tmp_path, monkeypatch):
    root = _a_workspace(tmp_path)

    update, seen, _ = _fixed(root, monkeypatch, LATER_AND_LIMITED, ACCESS_LINES_ONLY, dispute=True,
                             specification=SETS_A_LIMIT)

    assert update["stage"] == "acceptance_dispute" and update["dispute_returns_to"] == "test_and_triage"
    assert "agent loop" not in seen.events, "no fixer before the lead has judged"
    reason = update["dispute_reason"]
    # A route only the later sprint's criterion names, which the product does not serve yet.
    assert "`[AC-3] lists the orders of the user`" in reason and "/api/orders" in reason
    # A limit the specification sets, met even on its own.
    assert "`[AC-3] signs in and lists the items`" in reason and "429" in reason
    # A route this sprint's criterion names is the fixer's, whatever it answered.
    assert "`[AC-3] lists the items`" not in reason
    assert not BANNED.search(reason)


def test_a_429_with_no_limit_in_the_specification_stays_the_fixer_s(tmp_path, monkeypatch):
    root = _a_workspace(tmp_path, later=False)

    update, seen, _ = _fixed(root, monkeypatch, LATER_AND_LIMITED, ACCESS_LINES_ONLY, dispute=True)

    assert update.get("stage") != "acceptance_dispute"
    assert "agent loop" in seen.events


def test_once_the_lead_may_not_be_asked_the_fixer_is_told_which_tests_are_not_its_own(tmp_path, monkeypatch):
    root = _a_workspace(tmp_path)

    update, seen, _ = _fixed(root, monkeypatch, LATER_AND_LIMITED, ACCESS_LINES_ONLY, dispute=False,
                             specification=SETS_A_LIMIT)

    assert "agent loop" in seen.events
    request = seen.requests[0]
    held = request[request.index("Not yours to make pass in this sprint"):]
    held = held[:held.index("\n\n") if "\n\n" in held else len(held)]
    assert "`[AC-3] lists the orders of the user`" in held and "`[AC-3] lists the items`" not in held
    assert not BANNED.search(held)


def test_the_builder_of_server_code_is_told_to_log_a_server_error_s_exception():
    from app.agents.specialists import _system_prompt

    told = " ".join(_system_prompt("backend").split())
    start = told.index("Where the product catches an exception and answers with a server error")
    sentence = told[start:told.index("see its cause.", start) + len("see its cause.")]

    assert "logs that exception with its full trace first" in sentence
    assert not BANNED.search(sentence)
