"""A failing criterion's defect carries what the product's server logged while the suite ran: its error and its frames.

Measured on one run: `POST /notes` answered 500, every test that created a note failed on `res.json()` of "Internal
Server Error", and the server had logged `Error: Internal server error at NotesRepository.save
(src/services/persistence.ts:44)` - in the suite's output, under Playwright's `[WebServer]` prefix - and no fixer was
shown it: five fixers in a row changed nothing or chased the tests.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.graph import acceptance_nodes

OUTPUT = """Running 15 tests using 1 worker
[WebServer] Listening on http://127.0.0.1:23011
[WebServer] Error: Internal server error
[WebServer]     at NotesRepository.save (file://notes-api/src/services/persistence.ts:44:13)
[WebServer]     at NotesRepository.create (file://notes-api/src/services/persistence.ts:30:5)
[WebServer]     at Array.<anonymous> (file://notes-api/src/routes/notes.ts:31:27)
[WebServer]     at #dispatch (file://notes-api/node_modules/hono/dist/hono-base.js:276:34)
[WebServer]     at async node:internal/modules/esm/loader:647:26
  1) [AC-1] creates a note
"""


def test_the_server_s_error_and_its_frames_in_the_product_are_kept():
    logged = acceptance_nodes.what_the_server_logged(OUTPUT)

    assert "Error: Internal server error" in logged
    assert "persistence.ts:44" in logged and "notes.ts:31" in logged
    assert "node_modules" not in logged and "node:internal" not in logged
    assert "Listening on" not in logged


def test_nothing_logged_is_nothing_said():
    assert acceptance_nodes.what_the_server_logged("Running 15 tests\n  1) [AC-1] x\n") == ""


def test_each_failing_criterion_s_defect_carries_it(tmp_path):
    from app.acceptance import junit, suite
    from tests.test_acceptance_stages import ALL_THREE, _authored, _plan, _state

    _authored(tmp_path, ALL_THREE)
    suite.lock(tmp_path)
    measured = suite.AcceptanceResult(ran=True, exit_code=1, command="npm run test:acceptance", output=OUTPUT,
                                      report=junit.Report(found=True, tests=[
                                          junit.TestResult(name="[AC-1] adds", outcome="failed", message="SyntaxError"),
                                          junit.TestResult(name="[AC-2] deletes")]))
    suite._judged(tmp_path, measured, True)
    state = _state(tmp_path, sprint_plan=_plan(["AC-1", "AC-2"], ["AC-3"]), current_sprint_index=0)

    [defect] = acceptance_nodes.failing_due_defects(state, [])

    assert defect.description.startswith("[AC-1")
    assert "persistence.ts:44" in defect.actual_behavior and "Error: Internal server error" in defect.actual_behavior


def test_an_error_the_product_put_in_place_of_the_one_it_caught_is_named(tmp_path):
    """Measured on the same run: the logged frame was `throw new Error('Internal server error')` inside `catch (_)`;
    the real cause - the folder the write needed did not exist - was thrown away, and the fixers saw only the
    replacement."""
    project = tmp_path / "notes-api"
    (project / "src" / "services").mkdir(parents=True)
    (project / "src" / "services" / "persistence.ts").write_text(
        "export class R {\n  save(notes) {\n    try {\n      write(notes);\n    } catch (_) {\n"
        "      throw new Error('Internal server error');\n    }\n  }\n}\n")
    logged = ("Error: Internal server error\n"
              "    at R.save (file://notes-api/src/services/persistence.ts:6:13)")

    said = acceptance_nodes.what_the_logged_frames_hide(tmp_path, logged)

    assert "notes-api/src/services/persistence.ts" in said and "line 6" in said
    assert "throws its own error in place of the one it caught" in said


def test_a_frame_on_an_ordinary_line_says_nothing(tmp_path):
    project = tmp_path / "notes-api" / "src"
    project.mkdir(parents=True)
    (project / "app.ts").write_text("export function f() {\n  return g();\n}\n")

    assert acceptance_nodes.what_the_logged_frames_hide(tmp_path, "Error: x\n    at f (file://notes-api/src/app.ts:2:3)") == ""


def test_the_server_s_errors_are_kept_from_the_whole_output_not_its_tail(tmp_path, monkeypatch):
    """Measured on the next run: the error behind `POST /notes` answering 500 was logged early in a long run, the
    result kept only the output's last 3,000 characters, and the defects showed a later `NotFoundError` instead."""
    from app.acceptance import junit, suite

    early = "[WebServer] TypeError: Cannot read properties of undefined (reading 'title')\n" \
            "[WebServer]     at createNote (file://notes-api/src/app.ts:41:20)\n"
    long_tail = "".join(f"  {n}) [AC-{n}] something failed\n" for n in range(400))
    monkeypatch.setattr(suite, "_command", lambda root: (["npx", "playwright", "test"], "report.xml", "notes-api"))
    monkeypatch.setattr(junit, "read", lambda path: junit.Report(found=True, tests=[junit.TestResult(name="[AC-1] x", outcome="failed")]))
    monkeypatch.setattr(suite, "criteria", lambda root: [])

    result = suite.run(tmp_path, save=False, runner=lambda argv, category, project: {"returncode": 1, "stdout": early + long_tail})

    assert "app.ts:41" in result.server_log and "app.ts:41" not in result.output
    assert result.as_dict()["server_log"] == result.server_log


#: A medium run's measurement as it saved it: every sign-up answered 500 and the server logged the trace (LF.1401:
#: seven rewrites after a surrender found no file, because such a criterion's defect named none).
SIGN_UP = json.loads((Path(__file__).parent / "captured"
                      / "acceptance-result-a-sign-up-answers-500-with-a-logged-trace.json").read_text())


def _a_criterion_failing_with(tmp_path, message):
    from app.acceptance import junit, suite
    from tests.test_acceptance_stages import ALL_THREE, _authored, _plan, _state

    for name in ("main.py", "routes.py"):
        path = tmp_path / "task-management-dashboard" / "task_management_dashboard" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("app = None\n")
    _authored(tmp_path, ALL_THREE)
    suite.lock(tmp_path)
    measured = suite.AcceptanceResult(
        ran=True, exit_code=1, command="npm run test:acceptance", output="", server_log=SIGN_UP["server_log"],
        report=junit.Report(found=True, tests=[
            junit.TestResult(name=SIGN_UP["AC-1"]["name"], outcome="failed", message=message),
            junit.TestResult(name="[AC-2] deletes")]))
    suite._judged(tmp_path, measured, True)
    state = _state(tmp_path, sprint_plan=_plan(["AC-1", "AC-2"], ["AC-3"]), current_sprint_index=0)
    [defect] = acceptance_nodes.failing_due_defects(state, [])
    return defect


def test_a_criterion_answered_5xx_names_the_product_files_its_logged_trace_names(tmp_path):
    defect = _a_criterion_failing_with(tmp_path, SIGN_UP["AC-1"]["message"])

    assert defect.affected_files == ["task-management-dashboard/task_management_dashboard/routes.py",
                                     "task-management-dashboard/task_management_dashboard/main.py"]
    assert "no such column: users.username" in defect.actual_behavior


def test_a_criterion_that_failed_without_a_5xx_is_given_no_file_from_the_log(tmp_path):
    defect = _a_criterion_failing_with(tmp_path, SIGN_UP["AC-1"]["message"].replace("Received: 500", "Received: 400"))

    assert defect.affected_files == []
