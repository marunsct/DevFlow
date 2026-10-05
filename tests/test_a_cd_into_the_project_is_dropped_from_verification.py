"""`cd <the project directory> && <command>` in a work order's verification is the command.

Two runs in a row: the lead wrote every verification as
`cd /simple-to-do-list-app && npm test`, the readiness check refused each as
"will not run as written" (there is no shell), and each cost a re-plan.
"""

from __future__ import annotations

from types import SimpleNamespace

from pydantic import BaseModel

from app.analysis.work_orders import with_the_project_directory_cd_dropped


class _Task(BaseModel):
    verification: list[str] = []


class _Plan(BaseModel):
    delegated_tasks: list[_Task] = []


def _workspace(tmp_path):
    (tmp_path / ".project-directory").write_text("notes-app\n")
    (tmp_path / "notes-app").mkdir()
    return tmp_path


def _dropped(tmp_path, *commands: str) -> list[str]:
    plan = _Plan(delegated_tasks=[_Task(verification=list(commands))])
    return with_the_project_directory_cd_dropped(plan, _workspace(tmp_path)).delegated_tasks[0].verification


def test_a_cd_into_the_project_directory_is_dropped(tmp_path) -> None:
    assert _dropped(
        tmp_path,
        "cd /notes-app && npm test",
        "cd notes-app && npx playwright test --grep 'AC-1'",
        "cd ./notes-app/ ; node --test tests/a.test.js",
        "`cd /notes-app && npm test`",
    ) == ["npm test", "npx playwright test --grep 'AC-1'", "node --test tests/a.test.js", "npm test"]


def test_any_other_shell_use_is_left_for_the_readiness_check(tmp_path) -> None:
    kept = [
        "cd /notes-app/src && npm test",
        "npm test && npm run lint",
        "cd /elsewhere && npm test",
        "npm test",
    ]
    assert _dropped(tmp_path, *kept) == kept


def test_without_a_project_directory_nothing_changes(tmp_path) -> None:
    plan = _Plan(delegated_tasks=[_Task(verification=["cd /x && npm test"])])
    assert with_the_project_directory_cd_dropped(plan, tmp_path) is plan


def test_the_workflow_drops_it_before_the_readiness_check() -> None:
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    assert source.index("with_the_project_directory_cd_dropped(\n") < source.index("problems = readiness_problems(")
