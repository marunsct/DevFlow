"""A type checker's finding is read from the folder the code runs in, and the product's own run outranks it (LF.1455).

Measured on two medium runs. A FastAPI service kept in `backend/` with its own manifest had every
`from app.config import settings` underlined "unknown import symbol" - Pyright took the project folder as the one
import root - and three defects said "this fails when the code runs" while the harness's own measurement read 15 of
15 acceptance tests passing. Six fixers spent 43 minutes; two right fixes were reverted because their regression test
imported the same names. On the other run, assigning a string to a mapped column was raised as failing at run time.

The records below are the real ones: the workspace's files, the run's saved measurement and Pyright's own message.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.analysis import language_service as service

RECORD = json.loads((Path(__file__).parent / "fixtures" / "evidence_records" / "service_in_a_subfolder.json")
                    .read_text(encoding="utf-8"))

needs_pyright = pytest.mark.skipif(shutil.which("node") is None or service._pyright() is None,
                                   reason="no Pyright beside Node here (the worker image has one)")


def _the_workspace(root: Path) -> Path:
    project = root / "task-management-dashboard"
    for name, text in RECORD["files"].items():
        target = project / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return project


def _the_snapshot():
    from app import ci

    return ci.Snapshot(**RECORD["latest_measurement"])


@needs_pyright
def test_a_service_in_its_own_folder_has_its_imports_read_from_there(tmp_path) -> None:
    """The real tree: the routers and the acceptance fixtures import `app.*` from `backend/`, as the service runs."""
    project = _the_workspace(tmp_path)
    targets = [project / "backend/app/routers/auth.py", project / "acceptance/conftest.py",
               project / "backend/app/auth.py"]

    found = service.python_underlined_together(project, targets)

    assert found == {target: [] for target in targets}


@needs_pyright
def test_an_import_of_a_name_its_module_lacks_is_still_underlined_there(tmp_path) -> None:
    """The root moved, the check did not go blind: a name `app.config` really lacks is found."""
    project = _the_workspace(tmp_path)
    router = project / "backend/app/routers/auth.py"
    router.write_text(router.read_text(encoding="utf-8").replace(
        "from app.config import settings", "from app.config import settings_that_do_not_exist"), encoding="utf-8")

    found = service.python_underlined_together(project, [router])

    assert any("settings_that_do_not_exist" in f["message"] for f in found[router])


def test_a_type_s_opinion_of_an_assignment_is_not_a_failure_when_it_runs(tmp_path, monkeypatch) -> None:
    """Pyright's real message for `task.priority = priority` on a mapped column: nothing fails when that runs."""
    project = tmp_path / "app"
    test_file = project / "tests" / "test_models.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("x = 1\n" * 60, encoding="utf-8")
    diagnostic = {"file": str(test_file), "severity": "error", "rule": "reportAttributeAccessIssue",
                  "message": RECORD["type_opinion"]["message"], "range": {"start": {"line": 55, "character": 12}}}
    # Pyright is the external tool; its output is the record.
    monkeypatch.setattr(service, "_pyright_diagnostics", lambda project: [diagnostic])

    found = service.python_underlined_together(project, [test_file])

    assert found == {test_file: []}


def test_an_import_the_product_s_run_loaded_is_contradicted_by_the_measurement() -> None:
    from app.analysis.checker_contradicted import contradicted

    said = contradicted("task-management-dashboard/backend/app/routers/auth.py",
                        '"settings" is unknown import symbol', _the_snapshot())

    assert "acceptance test" in said and "passed" in said


@pytest.mark.parametrize("relative, message", [
    # A name inside a function fails only when the function is called: the run says nothing of it.
    ("task-management-dashboard/backend/app/routers/auth.py", '"undefined_helper" is not defined'),
    # A test file the measurement did not run.
    ("task-management-dashboard/backend/tests/test_auth.py", '"settings" is unknown import symbol'),
])
def test_what_the_run_did_not_load_is_not_contradicted(relative, message) -> None:
    from app.analysis.checker_contradicted import contradicted

    assert contradicted(relative, message, _the_snapshot()) == ""


def test_a_product_that_did_not_start_contradicts_nothing() -> None:
    from app import ci
    from app.analysis.checker_contradicted import contradicted

    snapshot = ci.Snapshot(**{**RECORD["latest_measurement"], "problem": "The product did not start"})

    assert contradicted("task-management-dashboard/backend/app/routers/auth.py",
                        '"settings" is unknown import symbol', snapshot) == ""


def _committed(root: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", message], cwd=root, check=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()


def test_at_the_gate_a_contradicted_finding_is_worded_as_the_service_s_and_recorded(tmp_path, monkeypatch) -> None:
    """The defect the run raised, as Pyright reported it from the wrong root, beside the run's own measurement."""
    from app import ci
    from app.graph import engineering

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    before = _committed(tmp_path, "before")
    project = _the_workspace(tmp_path)
    (tmp_path / ".project-directory").write_text(project.name, encoding="utf-8")
    _committed(tmp_path, "batch")
    ci.save(str(tmp_path), _the_snapshot())
    router = project / "backend/app/routers/auth.py"
    as_reported = {"file": str(router), "severity": "error", "rule": "reportAttributeAccessIssue",
                   "message": '"settings" is unknown import symbol', "range": {"start": {"line": 9, "character": 23}}}
    monkeypatch.setattr(service, "_pyright_diagnostics", lambda project: [as_reported])

    defects = engineering.underlined_in_the_batch({"milestone_plan": None}, str(tmp_path), before)

    (defect,) = [d for d in defects if "routers/auth.py" in d.description]
    assert "this fails when the code runs" not in defect.description
    assert "suspected false finding" in defect.description
    assert "acceptance test" in defect.actual_behavior
    recorded = (tmp_path / ".harness" / "check-findings.jsonl").read_text(encoding="utf-8")
    assert "contradicted" in recorded and "routers/auth.py" in recorded


def test_the_new_wording_carries_no_product_words() -> None:
    from app.analysis.checker_contradicted import SUSPECTED_FALSE
    from app.graph.engineering import REVIEWER_S_READING

    for text in (SUSPECTED_FALSE, REVIEWER_S_READING):
        assert not {"task", "tasks", "to-do", "todo", "button", "click", "checkbox"} & set(
            text.lower().replace(".", " ").replace(",", " ").replace(":", " ").split())
