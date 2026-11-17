"""A locked suite that gives no answer is run one file at a time by the harness.

One run's suite timed out on its first run (exit 124, no test reported) and a
frontier model spent 38 minutes running its files one by one to find the
product's `start()` resolved before its socket was bound.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.specialists import SpecialistOutput
from app.acceptance.per_file import _the_command_for, defects_from, each_file
from app.graph import workflow

RECORD = {
    "project": "notes-api", "acceptance_dir": "tests/acceptance", "acceptance_pattern": "*.test.ts",
    "acceptance_test": ["node", "--test", "--test-reporter=junit", "tests/acceptance/**/*.test.ts"],
}


def test_the_suite_s_selection_is_replaced_by_one_file():
    assert _the_command_for(RECORD["acceptance_test"], "tests/acceptance/a.test.ts", "tests/acceptance", "*.test.ts") == [
        "node", "--test", "--test-reporter=junit", "tests/acceptance/a.test.ts"]
    assert _the_command_for(["pytest", "-q"], "tests/acceptance/test_a.py", "tests/acceptance", "test_*.py") == [
        "pytest", "-q", "tests/acceptance/test_a.py"]


def test_each_file_runs_alone_and_what_hangs_or_fails_is_a_defect(tmp_path):
    folder = tmp_path / "notes-api" / "tests" / "acceptance"
    folder.mkdir(parents=True)
    for name in ("crud.test.ts", "restart.test.ts", "start.test.ts", "notes.md"):
        (folder / name).write_text("//")
    ran = []

    def run(argv, category, working_directory):
        ran.append((argv[-1], category, working_directory))
        if argv[-1].endswith("crud.test.ts"):
            return {"returncode": 124, "error": "Command timed out after 60 seconds."}
        if argv[-1].endswith("restart.test.ts"):
            return {"returncode": 1, "stdout": "AssertionError: expected 1 note, got 0"}
        return {"returncode": 0, "stdout": "ok"}

    runs = each_file(tmp_path, RECORD, run)
    defects = defects_from(runs, "backend", 60)

    assert [(r["file"], r["outcome"]) for r in runs] == [
        ("notes-api/tests/acceptance/crud.test.ts", "hung"),
        ("notes-api/tests/acceptance/restart.test.ts", "failed"),
        ("notes-api/tests/acceptance/start.test.ts", "finished"),
    ]
    assert all(category == "probe" and where == "notes-api" for _, category, where in ran)
    assert len(defects) == 2 and all(d.owner == "backend" for d in defects)
    assert "does not finish within 60 s" in defects[0].description
    assert "expected 1 note, got 0" in defects[1].description


def _a_suite_that_gave_no_answer(tmp_path, monkeypatch) -> None:
    from app.graph import acceptance_nodes
    from app.stacks import contract, scaffold

    folder = tmp_path / "notes-api" / "tests" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "crud.test.ts").write_text("//")
    monkeypatch.setattr(acceptance_nodes.suite, "is_locked", lambda root: True)
    monkeypatch.setattr(contract, "read", lambda root: RECORD)
    monkeypatch.setattr(scaffold, "sandbox_runner", lambda root: lambda argv, category, where: {
        "returncode": 124, "error": "Command timed out after 60 seconds."})
    monkeypatch.setattr(scaffold, "entrypoint_is_still_the_stub", lambda root: None)
    monkeypatch.setattr(workflow, "_run_unit_tests_procedurally", lambda root: (None, ""))


MILESTONE = SimpleNamespace(selected_sprint_goal="g", milestone_scope=[], delegated_tasks=[])


@pytest.mark.parametrize("mode", ["fast", "thorough"])
def test_the_test_round_tries_it_before_the_testing_specialist(tmp_path, monkeypatch, mode):
    """In every delivery mode, and only for a suite whose saved run gave no answer."""
    from workflow_nodes import a_test_round, reported

    monkeypatch.setenv("DELIVERY_MODE", mode)
    _a_suite_that_gave_no_answer(tmp_path, monkeypatch)
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}

    diagnosed = workflow._diagnosed_file_by_file(state, {}, MILESTONE, 1)
    assert diagnosed is not None and "does not finish within 60 s" in diagnosed.defects[0].description
    assert workflow._diagnosed_file_by_file(state, {"ran": True}, MILESTONE, 1) is None

    found = SpecialistOutput(changed_files=[], defects=[reported("crud.test.ts does not finish within 60 s")])
    update, calls = a_test_round(tmp_path, patches={
        "app.graph.workflow._diagnosed_file_by_file": lambda state, saved_run, milestone, test_round: found})
    assert calls == [], "the testing specialist was asked although the harness had the round's answer"
    assert [d.description for d in update["remediation"].defects] == ["crud.test.ts does not finish within 60 s"]
