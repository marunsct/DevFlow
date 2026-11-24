"""Unit tests are written, kept and counted where the project's unit runner collects them (LF.1262, LF.1263).

Measured on a full-stack run (a page and a Python service): the lead's work order told the testing stage to write the
service's unit tests in a test folder inside the service's package; the pack's runner collects only the project's own
unit test folder. Both files (361 and 708 lines) were never run; the throwaway sweep before each test round deleted
them as tests no suite runs, with no stage asking for it; and the unit gate passed every round on a run that collected
no test ("No test files found").
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.analysis import project_memory
from app.stacks import contract, pack_named
from app.tools.repository import (
    PROJECT_MARKER, WORK_ORDER_FILES, RepositoryToolError, clear_the_throwaways_left_behind, write_approved_artifact,
)

_BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

A_UNIT_TEST = '''from fastapi.testclient import TestClient

from notes_app.main import app


def test_the_service_answers():
    assert TestClient(app).get("/api/health").status_code == 200
'''


def _a_page_and_service_workspace(tmp_path: Path) -> Path:
    pack = pack_named("fullstack-react-fastapi")
    assert pack is not None
    for relative, content in pack.render("notes-app", "Notes", "notes_app").items():
        target = tmp_path / "notes-app" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    contract.write(tmp_path, pack, "notes-app", "Notes", "notes_app")
    (tmp_path / PROJECT_MARKER).write_text("notes-app\n", encoding="utf-8")
    return tmp_path


def _written_by_a_stage(root: Path, relative: str, content: str = A_UNIT_TEST) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    project_memory.record(root, relative, "specialist_testing_2")
    return path


# --- LF.1262: nothing deletes a stage's unit tests --------------------------------------------------------------

def test_a_unit_test_file_in_a_folder_the_runner_does_not_collect_is_not_cleared_as_a_throwaway(tmp_path) -> None:
    root = _a_page_and_service_workspace(tmp_path)
    tests = _written_by_a_stage(root, "notes-app/notes_app/tests/test_auth.py")
    probe = _written_by_a_stage(root, "notes-app/test_import.py", "import notes_app\nprint('ok')\n")

    removed = clear_the_throwaways_left_behind(root)

    assert tests.exists()
    assert removed == ["notes-app/test_import.py"] and not probe.exists()


# --- LF.1263: a test is written where it runs ---------------------------------------------------------------------

def test_a_new_unit_test_where_the_runner_does_not_look_is_refused_with_the_path_it_collects(tmp_path) -> None:
    root = _a_page_and_service_workspace(tmp_path)

    with pytest.raises(RepositoryToolError) as refused:
        write_approved_artifact(root, "notes-app/notes_app/tests/test_auth.py", A_UNIT_TEST)

    said = str(refused.value)
    assert "'notes-app/tests/test_auth.py'" in said and "`notes-app/tests/`" in said
    assert not (root / "notes-app/notes_app/tests/test_auth.py").exists()
    assert not _BANNED.search(said)
    write_approved_artifact(root, "notes-app/tests/test_auth.py", A_UNIT_TEST)
    assert (root / "notes-app/tests/test_auth.py").is_file()


def test_a_page_test_written_beside_its_code_is_sent_to_the_folder_the_page_s_runner_collects(tmp_path) -> None:
    """The page's runner collects one sub-folder of the unit folder; the pack's own smoke test says which."""
    root = _a_page_and_service_workspace(tmp_path)

    with pytest.raises(RepositoryToolError) as refused:
        write_approved_artifact(root, "notes-app/src/__tests__/App.test.tsx", "it('renders', () => {});\n")

    assert "'notes-app/tests/client/App.test.tsx'" in str(refused.value)


def test_a_work_order_s_unit_test_files_are_named_where_the_runner_collects_them(tmp_path) -> None:
    from app.analysis.work_orders import with_tests_where_the_runner_collects

    root = _a_page_and_service_workspace(tmp_path)
    testing = SpecialistTask(
        specialist_role="testing", task_description="Write the service's unit tests.",
        files=["notes-app/notes_app/tests/test_auth.py", "notes-app/tests/client/App.test.tsx"],
        steps=["Write notes-app/notes_app/tests/test_auth.py with one test per case."],
    )
    plan = MilestonePlanOutput(selected_sprint_goal="sign in", delegated_tasks=[testing])

    fixed = with_tests_where_the_runner_collects(plan, root).delegated_tasks[0]

    assert fixed.files == ["notes-app/tests/test_auth.py", "notes-app/tests/client/App.test.tsx"]
    assert fixed.steps == ["Write notes-app/tests/test_auth.py with one test per case."]


# --- LF.1263: the unit gate does not pass on no test once tests were ordered --------------------------------------

def _a_unit_run_that_collects_nothing(monkeypatch, root: Path) -> None:
    def run(argv, category, project):
        report = root / "notes-app" / "test-results" / "unit.xml"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<testsuites>\n\n</testsuites>\n')
        return {"returncode": 0, "stdout": "No test files found, exiting with code 0\n\nno tests ran in 0.01s\n"}

    monkeypatch.setattr("app.stacks.scaffold.sandbox_runner", lambda repo_root: run)


def test_a_unit_run_that_collected_no_test_fails_once_unit_tests_were_written(tmp_path, monkeypatch) -> None:
    from app.graph.workflow import _run_unit_tests_procedurally

    root = _a_page_and_service_workspace(tmp_path)
    (root / "notes-app/notes_app/tests").mkdir(parents=True)
    (root / "notes-app/notes_app/tests/test_auth.py").write_text(A_UNIT_TEST, encoding="utf-8")
    _a_unit_run_that_collects_nothing(monkeypatch, root)

    passed, said = _run_unit_tests_procedurally(str(root))

    assert passed is False
    assert "`notes-app/tests/`" in said and "`test_*.py`" in said
    assert "`notes-app/notes_app/tests/test_auth.py` (collected as `notes-app/tests/test_auth.py`)" in said
    assert not _BANNED.search(said.split("No unit test ran", 1)[1])


def test_a_unit_run_that_collected_no_test_fails_when_the_work_orders_plan_unit_tests(tmp_path, monkeypatch) -> None:
    from app.graph.workflow import _run_unit_tests_procedurally

    root = _a_page_and_service_workspace(tmp_path)
    (root / WORK_ORDER_FILES).write_text(json.dumps({"notes-app/tests/test_notes.py": "specialist_testing_2"}))
    _a_unit_run_that_collects_nothing(monkeypatch, root)

    passed, said = _run_unit_tests_procedurally(str(root))

    assert passed is False and "`notes-app/tests/test_notes.py`" in said


def test_a_unit_run_with_no_test_passes_while_none_was_ordered(tmp_path, monkeypatch) -> None:
    """The first rounds of a product, before any unit test is ordered, are as they were."""
    from app.graph.workflow import _run_unit_tests_procedurally

    root = _a_page_and_service_workspace(tmp_path)
    _a_unit_run_that_collects_nothing(monkeypatch, root)

    passed, _ = _run_unit_tests_procedurally(str(root))

    assert passed is True


# --- the stages are told the names the runner collects ------------------------------------------------------------

def test_the_project_setup_names_every_unit_test_name_the_runner_collects(tmp_path) -> None:
    """The setup said `*.test.tsx` alone for a page and a Python service: nothing told a stage `test_*.py`."""
    root = _a_page_and_service_workspace(tmp_path)

    told = contract.describe(root, with_reference_code=False)

    line = next(line for line in told.splitlines() if line.startswith("- Unit tests:"))
    assert "`test_*.py`" in line and "`*.test.tsx`" in line
