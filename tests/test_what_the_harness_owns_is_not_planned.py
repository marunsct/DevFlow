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


def test_a_restyle_needs_no_testing_work_order_and_no_test_cases(project, monkeypatch) -> None:
    """One run's milestone revision changed only a stylesheet; the rule sent it
    back twice for "No `testing` work order", and the lead invented one to
    "execute unit tests" that named no files. Styling has no behaviour a unit
    test can exercise - the acceptance suite checks it where a person meets it."""
    from app.analysis.file_kinds import is_presentation

    monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "on")
    restyle = SpecialistTask(
        specialist_role="ui_ux", title="Responsive layout", task_description="Stack the form on narrow screens.",
        files=["notes/styles.css", "notes/assets/icon.svg"],
    )
    assert readiness_problems(_plan(restyle), project) == []
    behaviour = _task("ui_ux", "notes/src/app.js")
    assert any("No `testing` work order" in p for p in readiness_problems(_plan(behaviour), project))
    assert is_presentation("notes/styles.css") and not is_presentation("notes/index.html")


def test_the_harness_s_setup_is_not_counted_against_the_product_s_size(project) -> None:
    """A brief's line cap is the product's. Counted, the kept server and page
    check - over a hundred lines - went against it."""
    from app.analysis.integration_checks import _measure_sizes, _source_files

    (project / "notes" / "src").mkdir(parents=True, exist_ok=True)
    (project / "notes" / "src" / "app.js").write_text("export function add(a, b) {\n  return a + b;\n}\n")

    application, tests, stray, counted = _measure_sizes(_source_files(project), project)

    names = {name for _, name in application}
    assert "notes/src/app.js" in names
    assert not [name for name in counted if contract.owned_by_the_harness(project, name)]


def test_after_the_harness_s_own_repairs_its_files_raise_no_readiness_problem(project, monkeypatch) -> None:
    """HR2.P.1: the repairs ran after the check, so 125 of 140 resends were for what they then fixed anyway."""
    monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "on")
    plan = _plan(
        _task("backend", "notes/src/app.js", "notes/scripts/serve.mjs"),
        _task("testing", "notes/tests/app.test.js", "notes/acceptance/notes.spec.js"),
    )
    assert [p for p in readiness_problems(plan, project) if "the harness keeps" in p or "locked acceptance suite" in p]
    repaired = with_the_harness_s_files_left_out(plan, project)
    assert not [p for p in readiness_problems(repaired, project) if "the harness keeps" in p or "locked acceptance suite" in p]


def test_the_planner_repairs_before_it_checks() -> None:
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    check = source.index("        problems = readiness_problems(\n            update[\"milestone_plan\"],")
    assert source.rindex("update[\"milestone_plan\"] = with_the_harness_s_files_left_out(", 0, check) > \
        source.rindex("with_a_testing_work_order(", 0, check)
    assert source.rindex("update[\"milestone_plan\"] = with_refused_commands_noted(", 0, check) > \
        source.rindex("with_a_testing_work_order(", 0, check)


def test_a_testing_order_that_writes_nothing_is_left_to_the_test_round(project, monkeypatch) -> None:
    """Measured: a plan was sent back three times for "Run unit tests to verify ..." orders listing no files."""
    from app.analysis.work_orders import with_run_only_testing_orders_left_to_the_test_round

    monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "on")
    run_only = SpecialistTask(specialist_role="testing", title="Verify", task_description="Run the unit tests to verify the fix.",
                              files=[], test_cases=["given the fix, when the tests run, then they pass"])
    plan = _plan(_task("backend", "notes/src/app.js"), _task("testing", "notes/tests/app.test.js"), run_only)
    assert [p for p in readiness_problems(plan, project) if "names no `files`" in p]

    left, labels = with_run_only_testing_orders_left_to_the_test_round(plan)

    assert len(labels) == 1 and len(left.delegated_tasks) == 2
    assert not [p for p in readiness_problems(left, project) if "names no `files`" in p]
    assert any("Verified by the harness's test round" in note for note in left.integration_notes)


def test_a_plan_of_only_run_only_orders_is_left_as_it_is_for_the_check(project) -> None:
    from app.analysis.work_orders import with_run_only_testing_orders_left_to_the_test_round

    run_only = SpecialistTask(specialist_role="testing", title="Verify", task_description="Run the tests.", files=[],
                              test_cases=["x"])
    plan = _plan(run_only)
    assert with_run_only_testing_orders_left_to_the_test_round(plan) == (plan, [])


def test_the_measured_run_only_orders_are_left_and_a_writing_order_is_not() -> None:
    from app.analysis.work_orders import _ONLY_RUNS, _WRITES

    for said in ("Run unit tests to verify database fix and model/route corrections",
                 "Run Playwright acceptance suite to verify all previously failing criteria"):
        assert _ONLY_RUNS.search(said) and not _WRITES.search(said), said
    assert _WRITES.search("Run the suite, then add tests for the empty title")
    assert not _ONLY_RUNS.search("do testing work")
