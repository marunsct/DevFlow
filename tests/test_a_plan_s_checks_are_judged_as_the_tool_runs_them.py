"""A plan's checks are judged as the command tool would run them, not stricter.

Measured on one gate run: a re-plan was sent back for seven problems, six of
them a `python -c` check the tool would have run from a scratch file, and one
`npm run build 2>&1 | tail -5` whose trimming changes nothing the command does.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.analysis import work_orders
from app.analysis.planned_commands import commands_the_sandbox_would_refuse


def test_inline_code_the_tool_runs_from_a_file_is_not_refused():
    for line in ('`.venv/bin/python -c "from shop.auth import login; print(1)"`',
                 '`python3 -c "import json"`', '`node -e "console.log(1)"`'):
        assert commands_the_sandbox_would_refuse(line, "backend_specialist", None) == [], line


def test_trailing_output_trimming_is_dropped_from_a_check(monkeypatch, tmp_path):
    monkeypatch.setattr(work_orders, "_pinned_project_directory", lambda root: "shop")
    order = SpecialistTask(specialist_role="ui_ux", title="Page", task_description="Build the page.",
                           files=["shop/src/App.tsx"], interfaces=["the page"], test_cases=["it renders"],
                           verification=["npm run build 2>&1 | tail -5", "npm test | grep passed", "npm test"])
    plan = MilestonePlanOutput.model_construct(selected_sprint_goal="g", delegated_tasks=[order])

    checked = work_orders.with_the_project_directory_cd_dropped(plan, tmp_path).delegated_tasks[0].verification

    assert checked == ["npm run build", "npm test | grep passed", "npm test"]
