"""What the harness owns is refused where the plan is made, and marked where stages look.

One run's lead planned work orders to change the acceptance setup the harness
keeps, although its brief said no work order may; its stages then made 16
refused edits of kept files and 19 refused attempts to run the kept server.
A rule in a prompt did not hold, so it is enforced on the plan itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.acceptance import suite
from app.acceptance.criteria import number
from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.agents.workspace_digest import render_workspace_digest
from app.analysis.work_orders import readiness_problems, with_the_harness_s_files_left_out
from app.stacks import contract, pack_named
from app.stacks.scaffold import scaffold

BRIEF = """# Notes

## Requirements
- Add a note with a title
- Delete a note
"""


def _runner(root: Path, pack):
    def run(argv, category, working_directory):
        commands = pack.commands(working_directory)
        if category == "test":
            unit = list(argv) == commands["unit_test"]
            target = root / working_directory / (pack.unit_report if unit else pack.acceptance_report)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("<testsuites><testcase name='smoke'/></testsuites>")
        return {"returncode": "0", "stdout": "", "stderr": ""}

    return run


@pytest.fixture
def project(tmp_path):
    pack = pack_named("browser-javascript")
    assert scaffold(tmp_path, pack, "notes", "Notes", run=_runner(tmp_path, pack)).ok
    suite.save_criteria(tmp_path, number(BRIEF))
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("test('[AC-1][AC-2] notes', async () => {});\n")
    suite.lock(tmp_path)
    return tmp_path


def _plan(*tasks: SpecialistTask) -> MilestonePlanOutput:
    return MilestonePlanOutput(selected_sprint_goal="Notes", delegated_tasks=list(tasks))


def _task(role: str, *files: str) -> SpecialistTask:
    return SpecialistTask(
        specialist_role=role, title=f"{role} work", task_description="Build it.",
        files=list(files), test_cases=["given a note, when added, then it is listed"],
    )


def test_one_answer_to_who_owns_a_path(project) -> None:
    assert contract.owned_by_the_harness(project, "notes/scripts/serve.mjs") == contract.KEPT_SETUP
    assert contract.owned_by_the_harness(project, "/notes/playwright.config.js") == contract.KEPT_SETUP
    assert contract.owned_by_the_harness(project, "notes/acceptance/notes.spec.js") == contract.LOCKED_SUITE
    assert contract.owned_by_the_harness(project, ".harness/stack-pack.json") == contract.HARNESS_RECORDS
    assert contract.owned_by_the_harness(project, "notes/src/app.js") == ""
    assert contract.owned_by_the_harness(project, "notes/package.json") == ""


def test_a_project_no_pack_scaffolded_owns_nothing(tmp_path) -> None:
    assert contract.kept_paths(tmp_path) == frozenset()
    assert contract.owned_by_the_harness(tmp_path, "notes/scripts/serve.mjs") == ""


def test_a_work_order_naming_a_kept_file_or_the_locked_suite_is_not_ready(project, monkeypatch) -> None:
    monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "on")
    plan = _plan(
        _task("backend", "notes/src/app.js", "notes/scripts/serve.mjs"),
        _task("testing", "notes/tests/app.test.js", "notes/acceptance/notes.spec.js"),
    )
    problems = readiness_problems(plan, project)
    owned = [p for p in problems if "the harness keeps" in p or "locked acceptance suite" in p]
    assert len(owned) == 2
    assert "notes/scripts/serve.mjs" in owned[0] and "fix is in a product file" in owned[0]
    assert "notes/acceptance/notes.spec.js" in owned[1]


def test_a_plan_of_product_files_is_not_held_back_by_it(project, monkeypatch) -> None:
    monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "on")
    plan = _plan(_task("backend", "notes/src/app.js"), _task("testing", "notes/tests/app.test.js"))
    assert not [p for p in readiness_problems(plan, project) if "harness" in p or "locked" in p]


def test_a_plan_dispatched_anyway_no_longer_names_them(project) -> None:
    plan = _plan(_task("backend", "notes/src/app.js", "notes/scripts/serve.mjs"))
    dispatched = with_the_harness_s_files_left_out(plan, project)
    task = dispatched.delegated_tasks[0]
    assert task.files == ["notes/src/app.js"]
    assert "`notes/scripts/serve.mjs`" in task.task_description
    assert "fix is in the product" in task.task_description
    # The original plan is not changed in place, and a clean plan is returned as it is.
    assert plan.delegated_tasks[0].files == ["notes/src/app.js", "notes/scripts/serve.mjs"]
    clean = _plan(_task("backend", "notes/src/app.js"))
    assert with_the_harness_s_files_left_out(clean, project) is clean


def test_the_digest_marks_them_and_says_what_to_do(project) -> None:
    (project / "notes" / "src").mkdir(parents=True, exist_ok=True)
    (project / "notes" / "src" / "app.js").write_text("export function addNote(title) {}\n")
    digest = render_workspace_digest(project, max_files=200)
    serve = next(line for line in digest.splitlines() if "notes/scripts/serve.mjs" in line)
    assert contract.KEPT_SETUP in serve and "do not change, run or test it" in serve
    spec = next(line for line in digest.splitlines() if "notes/acceptance/notes.spec.js" in line)
    assert contract.LOCKED_SUITE in spec and "never change it" in spec
    app = next(line for line in digest.splitlines() if "notes/src/app.js" in line)
    assert "harness" not in app
