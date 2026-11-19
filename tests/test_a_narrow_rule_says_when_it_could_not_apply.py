"""A narrow rule that meets an input it cannot read says so in the run's transcript (launch review LR.46).

Four checks rest on a closed reading: a fixed list of user-action verbs, fields read from the words after "with",
a contract sign-in found by its path and sent as a Bearer token, and test totals read from six runners' summaries.
Off the benchmark each met inputs it did not recognise and did nothing, silently. Each now records a
`rule_could_not_apply` note, once per run and input, and the ten-minute audit prints the counts per check. No rule's
answer changes.
"""

from __future__ import annotations

import inspect
import uuid
from pathlib import Path

import pytest

from app.acceptance import interface_contract as ic
from app.analysis import integration_checks
from app.analysis.integration_checks import _a_field_the_brief_asks_for_that_nothing_collects, _actions_required_in, \
    _source_files
from app.models.model_pin import as_the_run
from app.observability import rule_coverage
from app.observability.transcript import read_transcript
from app.tools import sandbox

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "loop"


@pytest.fixture()
def run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RUN_TRANSCRIPT", "true")
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    with as_the_run(run_id):
        yield run_id


def _noted(run_id: str, check: str | None = None) -> list[dict]:
    notes = read_transcript(run_id, {rule_coverage.KIND})
    return [n for n in notes if check is None or n.get("check") == check]


# --- the counter ---------------------------------------------------------------------------------------------------

def test_a_could_not_apply_is_written_once_per_run_and_reason(run):
    assert rule_coverage.could_not_apply("some_check", "an input it did not read")
    assert not rule_coverage.could_not_apply("some_check", "an input  it did not read")  # the same reason
    assert rule_coverage.could_not_apply("some_check", "another input")
    notes = _noted(run)
    assert [n["why"] for n in notes] == ["an input it did not read", "another input"]
    assert all(n["kind"] == "rule_could_not_apply" and n["check"] == "some_check" for n in notes)


def test_outside_a_run_nothing_is_written_and_nothing_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert rule_coverage.could_not_apply("some_check", "no run") is False
    assert not (tmp_path / "transcripts").exists() or not list((tmp_path / "transcripts").iterdir())


def test_the_audit_lines_count_the_distinct_inputs_per_check():
    records = [
        {"kind": "rule_could_not_apply", "check": "runner_totals", "why": "a"},
        {"kind": "rule_could_not_apply", "check": "runner_totals", "why": "b"},
        {"kind": "rule_could_not_apply", "check": "runner_totals", "why": "a"},
        {"kind": "rule_could_not_apply", "check": "action_verbs", "why": "c"},
        {"kind": "tool_call", "check": "action_verbs", "why": "not a note"},
    ]
    found = rule_coverage.lines(records)
    assert found[0] == "rules that could not apply (distinct inputs): runner_totals 2, action_verbs 1"
    assert "  runner_totals: a" in found and "  action_verbs: c" in found
    assert rule_coverage.lines([{"kind": "tool_call"}]) == []


def test_the_ten_minute_audit_prints_them(tmp_path, monkeypatch, capsys):
    import glob
    import json
    import runpy
    import sys

    transcript = tmp_path / "run-audit.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in [
        {"at": "2026-11-01T00:00:00+00:00", "stage": "test_and_triage", "kind": "rule_could_not_apply",
         "check": "runner_totals", "why": "a summary it did not read"},
    ]) + "\n")
    monkeypatch.setattr(glob, "glob", lambda pattern: [str(transcript)])
    monkeypatch.setattr(sys, "argv", ["audit_live.py", "run-audit"])

    runpy.run_path(str(SCRIPTS / "audit_live.py"), run_name="__main__")

    printed = capsys.readouterr().out
    assert "rules that could not apply (distinct inputs): runner_totals 1" in printed
    assert "  runner_totals: a summary it did not read" in printed


# --- the closed list of user-action verbs ---------------------------------------------------------------------------

def test_verbs_outside_the_closed_list_are_counted(run):
    required = _actions_required_in("## Acceptance criteria\n- Users can borrow, return and renew books\n", {})
    assert required == {}  # unchanged: the rule still reads nothing here
    notes = _noted(run, rule_coverage.ACTION_VERBS)
    assert len(notes) == 1 and "borrow, return, renew" in notes[0]["why"] and "skipped" in notes[0]["why"]


def test_a_known_verb_beside_an_unknown_one_counts_the_unknown(run):
    required = _actions_required_in("## Acceptance criteria\n- Users can add, tag and archive bookmarks\n", {})
    assert set(required) == {"add", "archive"}
    notes = _noted(run, rule_coverage.ACTION_VERBS)
    assert len(notes) == 1 and "(tag)" in notes[0]["why"] and "skipped" not in notes[0]["why"]


def test_a_list_the_closed_verbs_read_whole_or_an_adjective_list_is_not_counted(run):
    _actions_required_in("## Acceptance criteria\n- Users can add, edit, delete tasks\n"
                         "- The page is simple, fast and lightweight\n", {})
    assert _noted(run, rule_coverage.ACTION_VERBS) == []


def test_a_state_beside_its_opposite_is_not_counted(run):
    """"Mark entries as complete/incomplete" names a state and its negation, not a list with an unknown verb."""
    _actions_required_in("## Acceptance criteria\n- Mark entries as complete/incomplete\n"
                         "- Users can mark notes read/unread\n", {})
    assert _noted(run, rule_coverage.ACTION_VERBS) == []


def test_a_list_with_a_comma_before_its_last_member_reads_every_member(run):
    """"archive, sort, and duplicate": the comma before "and" ended the list at "and", dropping its last member."""
    required = _actions_required_in("## Acceptance criteria\n- Users can archive, sort, and duplicate entries\n", {})
    assert set(required) == {"archive", "sort", "duplicate"}
    assert _noted(run, rule_coverage.ACTION_VERBS) == []


def test_toggle_is_an_action_a_user_takes(run):
    """A list app's own verb: "add, toggle and delete" required add and delete only, and noted toggle as unknown."""
    required = _actions_required_in("## Acceptance criteria\n- Users can add, toggle and delete entries\n", {})
    assert set(required) == {"add", "toggle", "delete"}
    assert _noted(run, rule_coverage.ACTION_VERBS) == []


# --- fields read from "with" ----------------------------------------------------------------------------------------

def _files(root: Path, files: dict[str, str]) -> list[Path]:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return _source_files(root)


def test_a_product_with_no_page_controls_is_counted_for_the_fields(run, tmp_path):
    root = tmp_path / "product"
    files = _files(root, {"app/server.js": "export function create(title, description) { return { title }; }\n"})
    brief = "- Add new notes with title and description\n"
    assert _a_field_the_brief_asks_for_that_nothing_collects(files, root, brief) == []
    notes = _noted(run, rule_coverage.FIELDS_GIVEN_WITH)
    assert len(notes) == 1 and "no form control" in notes[0]["why"]


def test_a_field_named_nowhere_in_the_product_is_counted(run, tmp_path):
    root = tmp_path / "product"
    files = _files(root, {"app/index.html": '<form><input type="text" placeholder="New note"></form>\n',
                          "app/app.js": "export function addNote(title) { return { title }; }\n"})
    brief = "- Create notes with ease and confidence\n"
    problems = _a_field_the_brief_asks_for_that_nothing_collects(files, root, brief)
    assert len(problems) == 1 and "`confidence`" in problems[0]  # unchanged: the finding is still made
    notes = _noted(run, rule_coverage.FIELDS_GIVEN_WITH)
    assert len(notes) == 1 and "`confidence`" in notes[0]["why"] and "possibly not a field" in notes[0]["why"]


def test_a_field_the_product_stores_but_never_collects_is_not_counted(run, tmp_path):
    root = tmp_path / "product"
    files = _files(root, {"app/index.html": '<form><input type="text" placeholder="New task"></form>\n',
                          "app/data.js": "export function addTask(title, description) { return { title, description }; }\n"})
    problems = _a_field_the_brief_asks_for_that_nothing_collects(files, root, "- Add new tasks with title and description\n")
    assert len(problems) == 1 and "`description`" in problems[0]
    assert _noted(run, rule_coverage.FIELDS_GIVEN_WITH) == []


# --- the contract probe's sign-in -----------------------------------------------------------------------------------

def _http(line: str, method: str, path: str, *statuses: int) -> ic.Check:
    return ic.Check(criterion="AC-1", kind="http", line=line, method=method, path=path,
                    status=statuses[0] if statuses else 0, statuses=tuple(statuses))


def test_a_contract_behind_a_sign_in_the_rule_cannot_find_is_counted(run):
    contract = [_http("POST /auth/authenticate -> 200", "POST", "/auth/authenticate", 200),
                _http("GET /items without credentials -> 401", "GET", "/items", 401)]
    assert ic.sign_in_plan(contract, [{"email": "a@b.c", "password": "p"}]) is None
    notes = _noted(run, rule_coverage.CONTRACT_SIGN_IN)
    assert len(notes) == 1 and "no POST path reads as signing in" in notes[0]["why"]


def test_a_sign_in_with_no_secret_in_any_body_is_counted(run):
    contract = [_http("POST /login -> 200", "POST", "/login", 200)]
    assert ic.sign_in_plan(contract, [{"email": "a@b.c"}]) is None
    notes = _noted(run, rule_coverage.CONTRACT_SIGN_IN)
    assert len(notes) == 1 and "no example body carries" in notes[0]["why"]


def test_a_cookie_sign_in_is_counted_and_the_plan_is_unchanged(run):
    contract = [_http("POST /login -> 200 (sets a session cookie)", "POST", "/login", 200)]
    plan = ic.sign_in_plan(contract, [{"email": "a@b.c", "password": "p"}])
    assert plan == {"signup": "", "signin": "/login", "body": {"email": "a@b.c", "password": "p"}}
    notes = _noted(run, rule_coverage.CONTRACT_SIGN_IN)
    assert len(notes) == 1 and "not a bearer token" in notes[0]["why"]


def test_a_bearer_sign_in_the_rule_reads_and_a_contract_with_no_sign_in_are_not_counted(run):
    contract = [_http("POST /api/auth/register -> 201", "POST", "/api/auth/register", 201),
                _http("POST /api/auth/login -> 200", "POST", "/api/auth/login", 200)]
    assert ic.sign_in_plan(contract, [{"email": "a@b.c", "password": "p"}]) is not None
    assert ic.sign_in_plan([_http("POST /notes -> 201", "POST", "/notes", 201)], []) is None
    assert _noted(run, rule_coverage.CONTRACT_SIGN_IN) == []


def test_a_body_probe_refused_at_sign_in_is_counted(run):
    ic._count_a_sign_in_the_probe_could_not_make(_http("POST /items -> 201", "POST", "/items", 201))
    notes = _noted(run, rule_coverage.CONTRACT_SIGN_IN)
    assert len(notes) == 1 and "`POST /items` refused the body probe at sign-in" in notes[0]["why"]


# --- the runners' totals --------------------------------------------------------------------------------------------

def test_a_test_run_in_a_summary_no_runner_reads_is_counted(run, tmp_path):
    workspace = tmp_path / "product-workspace"
    workspace.mkdir()
    result = {"returncode": 0, "stdout": "Build Summary: 3/3 steps succeeded; 5/5 tests passed\n", "stderr": ""}
    sandbox._record_execution(str(workspace), "qa", ["zig", "build", "test"], result, category="test")
    notes = _noted(run, rule_coverage.RUNNER_TOTALS)
    assert len(notes) == 1 and "`zig build test` printed no totals" in notes[0]["why"]


def test_a_test_run_a_runner_reads_or_a_command_that_is_not_a_test_is_not_counted(run, tmp_path):
    workspace = tmp_path / "product-workspace"
    workspace.mkdir()
    read = {"returncode": 0, "stdout": "===== 5 passed in 0.12s =====\n", "stderr": ""}
    sandbox._record_execution(str(workspace), "qa", ["pytest"], read, category="test")
    maven = {"returncode": 0, "stdout": "[INFO] Tests run: 5, Failures: 0, Errors: 0, Skipped: 0\n", "stderr": ""}
    sandbox._record_execution(str(workspace), "qa", ["mvn", "test"], maven, category="test")
    sandbox._record_execution(str(workspace), "qa", ["npm", "install"], {"returncode": 0, "stdout": "added 3"},
                              category="install")
    sandbox._record_execution(str(workspace), "qa", ["mvn", "test"], {"returncode": None, "error": "not found"},
                              category="test")
    assert _noted(run, rule_coverage.RUNNER_TOTALS) == []


# --- model-facing text: none is added, and the reasons stay in plain words -------------------------------------------

def test_the_reasons_avoid_the_banned_words():
    import re

    banned = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
    texts = [inspect.getsource(rule_coverage), *rule_coverage.CHECKS.values(),
             inspect.getsource(integration_checks._count_the_verbs_the_closed_list_misses),
             inspect.getsource(ic._count_a_sign_in_the_probe_could_not_make),
             inspect.getsource(sandbox._count_a_test_run_whose_totals_were_not_read)]
    assert not [t for t in texts if banned.search(t)]


SUREFIRE = """<?xml version="1.0"?>
<testsuite name="app.notes_api.NoteServiceTest" tests="3">
  <testcase name="createsANote" classname="app.notes_api.NoteServiceTest"/>
  <testcase name="listsNotes" classname="app.notes_api.NoteServiceTest"/>
  <testcase name="refusesAnEmptyTitle" classname="app.notes_api.NoteServiceTest"><failure message="expected 400">x</failure></testcase>
</testsuite>"""


def _a_java_project(root: Path) -> list[str]:
    from app.stacks import contract, pack_named

    contract.write(root, pack_named("java-spring-api"), "notes-api", "Notes")
    (root / "notes-api" / "target" / "surefire-reports").mkdir(parents=True)
    return contract.read(root)["unit_test"]


def test_a_quiet_green_unit_run_is_counted_from_the_report_it_wrote(run, tmp_path):
    """Measured on three Java runs: `mvn -q` prints no summary on a green run, though Surefire's reports held it."""
    workspace = tmp_path / "product-workspace"
    workspace.mkdir()
    command = _a_java_project(workspace)
    (workspace / "notes-api/target/surefire-reports/TEST-app.notes_api.NoteServiceTest.xml").write_text(SUREFIRE)
    quiet = {"returncode": 1, "stdout": "  .   ____          _            __ _ _\n 2026-11-17 INFO Started", "stderr": ""}

    assert sandbox._the_counts_its_report_holds(str(workspace), command, 12.0) == {"passed": 2, "failed": 1, "tests": 3}
    sandbox._record_execution(str(workspace), "qa", command, quiet, category="test", duration_seconds=12.0)
    assert _noted(run, rule_coverage.RUNNER_TOTALS) == []


def test_a_report_older_than_the_command_or_another_command_is_not_read(run, tmp_path):
    import os
    import time

    workspace = tmp_path / "product-workspace"
    workspace.mkdir()
    command = _a_java_project(workspace)
    report = workspace / "notes-api/target/surefire-reports/TEST-app.notes_api.NoteServiceTest.xml"
    report.write_text(SUREFIRE)
    os.utime(report, (time.time() - 3600, time.time() - 3600))
    assert sandbox._the_counts_its_report_holds(str(workspace), command, 12.0) == {}
    report.touch()
    assert sandbox._the_counts_its_report_holds(str(workspace), ["mvn", "-q", "-B", "verify"], 12.0) == {}


def test_a_pack_command_that_ran_no_test_is_not_a_summary_left_unread(run, tmp_path):
    """Measured on the C# and Java runs: a unit command whose tests did not compile wrote no report and named no
    totals, and the counter called it a runner whose summary no reader knows - most of its notes."""
    workspace = tmp_path / "product-workspace"
    workspace.mkdir()
    command = _a_java_project(workspace)
    broken = {"returncode": 1, "stdout": "[ERROR] COMPILATION ERROR : cannot find symbol", "stderr": ""}

    sandbox._record_execution(str(workspace), "qa", command, broken, category="test", duration_seconds=3.0)
    assert _noted(run, rule_coverage.RUNNER_TOTALS) == []
    sandbox._record_execution(str(workspace), "qa", ["zig", "build", "test"], {"stdout": "5/5 tests passed"},
                              category="test")
    assert len(_noted(run, rule_coverage.RUNNER_TOTALS)) == 1  # a command of the agent's own is still counted
