"""A plan with code and no testing work order is given one by the harness, not sent back.

"No `testing` work order" recurred identically: five send-backs in one day
across three runs, each a full re-plan of about ten minutes.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.analysis import work_orders
from app.analysis.work_orders import readiness_problems, with_a_testing_work_order
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _plan(*tasks):
    return MilestonePlanOutput.model_construct(selected_sprint_goal="Notes over HTTP", delegated_tasks=list(tasks))


def _backend(files):
    return SpecialistTask(
        specialist_role="backend", title="Routes", task_description="Serve the notes.",
        files=files, interfaces=["GET /notes -> 200 [Note]"], test_cases=["given no notes, GET /notes answers []"],
    )


def test_the_harness_writes_the_missing_testing_work_order_from_the_project_s_test_layout(monkeypatch, tmp_path):
    pack = SimpleNamespace(unit_dir="tests", unit_pattern="*.test.ts", unit_test=("npm", "test"))
    monkeypatch.setattr(contract, "the_pack", lambda root: (pack, {}))
    monkeypatch.setattr(work_orders, "_pinned_project_directory", lambda root: "notes-api")

    plan, added = with_a_testing_work_order(_plan(_backend(["notes-api/src/app.ts", "notes-api/src/store.ts"])), tmp_path)

    assert added
    testing = plan.delegated_tasks[-1]
    assert testing.specialist_role == "testing"
    assert testing.files == ["notes-api/tests/app.test.ts", "notes-api/tests/store.test.ts"]
    assert testing.test_cases == ["given no notes, GET /notes answers []"]
    assert testing.verification == ["npm test"]
    assert not BANNED.search(testing.title + testing.task_description)
    assert not any("testing` work order" in p for p in readiness_problems(plan, None))


def test_without_a_test_layout_to_name_files_the_plan_goes_back_as_before(monkeypatch, tmp_path):
    monkeypatch.setattr(contract, "the_pack", lambda root: None)
    plan = _plan(_backend(["notes-api/src/app.ts"]))

    assert with_a_testing_work_order(plan, tmp_path) == (plan, False)


def test_the_lead_is_told_every_rule_the_harness_checks():
    from app.agents import technical_lead

    source = open(technical_lead.__file__, encoding="utf-8").read()
    assert "a file the sprint's scope names that no work order lists" in source
    assert "one the\n  harness keeps" in source


def test_each_file_s_test_is_named_by_its_own_language_s_pattern(monkeypatch, tmp_path):
    """Measured on one gate run: a page-and-Python-service pack named `config.py`'s test `tests/config.test.tsx`."""
    pack = SimpleNamespace(unit_dir="tests", unit_pattern="*.test.tsx", unit_test=("npm", "test"),
                           unit_test_names=("*.test.tsx", "test_*.py"))
    monkeypatch.setattr(contract, "the_pack", lambda root: (pack, {}))
    monkeypatch.setattr(work_orders, "_pinned_project_directory", lambda root: "shop")

    plan, added = with_a_testing_work_order(_plan(_backend(["shop/shop_pkg/config.py", "shop/src/App.tsx"])), tmp_path)

    assert added and plan.delegated_tasks[-1].files == ["shop/tests/test_config.py", "shop/tests/App.test.tsx"]


def test_a_work_order_with_nothing_to_test_from_takes_the_sprint_s_criteria() -> None:
    """Measured on one gate run: a re-plan's one work order had neither test cases nor criteria, and went back."""
    from app.analysis.work_orders import with_test_cases_from_its_criteria

    order = SpecialistTask(specialist_role="backend", title="Wire it", task_description="Wire the service.",
                           files=["shop/shop_pkg/main.py"], interfaces=["the app"], test_cases=[])
    spec = SimpleNamespace(test_cases=["given a note, the list shows it (store.py)"])

    plan = with_test_cases_from_its_criteria(_plan(order), spec, ["AC-1: a user signs in"])

    assert plan.delegated_tasks[0].test_cases == ["AC-1: a user signs in"]
