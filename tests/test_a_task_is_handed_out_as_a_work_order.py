"""A task is a work order a developer new to the codebase can follow.

The operator's plan: "a technical lead will create a detailed technical
specification that will be easy to follow for the new developer". Each task
carries its files, interfaces, steps, edge cases, test cases, verification and
what is out of scope; a plan missing what can be checked without judgement is
sent back once before anyone is dispatched; and the testing task is given the
other tasks' contracts, so tests are written against the plan, not after it.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.agents.specialists import build_specialist_task_request
from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask, build_milestone_planning_request
from app.analysis.work_orders import brief_for, contract_for_testing, readiness_problems
from app.graph.workflow import start_workflow
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    ScriptedAgents,
    _approved_review,
    _document,
    _graph,
    _milestone_review,
    _repository,
    _script_through_architecture,
    _security_review,
    _specialist,
    _sprint_plan,
    agents,
    responds_with,
)


def _order(role: str = "backend", **fields: Any) -> SpecialistTask:
    base = dict(
        specialist_role=role,
        title=f"{role} work",
        task_description=f"Do the {role} work.",
        acceptance_criteria=["works"],
        files=[f"app/{role}.src"],
        interfaces=[f"do_{role}(x) -> y"],
        steps=["one", "two"],
        edge_cases=["empty x -> refused"],
        test_cases=[f"Given x, when do_{role}, then y"],
        verification=["npm test"],
        out_of_scope=["anything else"],
    )
    base.update(fields)
    return SpecialistTask(**base)


def _plan(*tasks: SpecialistTask) -> MilestonePlanOutput:
    return MilestonePlanOutput(selected_sprint_goal="goal", delegated_tasks=list(tasks))


@pytest.fixture
def enforced(monkeypatch):
    monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "on")


@pytest.fixture
def project(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".project-directory").write_text("app", encoding="utf-8")
    return tmp_path


class TestTheDefinitionOfReady:
    def test_a_complete_plan_is_ready(self, enforced, project):
        assert readiness_problems(_plan(_order("backend"), _order("testing", test_cases=[])), project) == []

    def test_a_code_task_with_no_files_is_not_ready(self, enforced, project):
        problems = readiness_problems(_plan(_order("backend", files=[]), _order("testing")), project)
        assert any("names no `files`" in p for p in problems)

    def test_a_file_outside_the_project_is_not_ready(self, enforced, project):
        problems = readiness_problems(
            _plan(_order("backend", files=["other/x.src", "docs/notes.md"]), _order("testing")), project
        )
        assert any("outside the project directory 'app/'" in p for p in problems)
        assert any("inside docs/" in p for p in problems)

    def test_a_code_task_with_no_test_cases_is_not_ready(self, enforced, project):
        problems = readiness_problems(_plan(_order("backend", test_cases=[]), _order("testing")), project)
        assert any("no `test_cases`" in p for p in problems)

    def test_code_with_no_testing_task_is_not_ready(self, enforced, project):
        problems = readiness_problems(_plan(_order("backend")), project)
        assert any("No `testing` work order" in p for p in problems)

    def test_a_refused_verification_command_is_not_ready(self, enforced, project):
        problems = readiness_problems(
            _plan(_order("backend", verification=["node -e \"console.log(1)\""]), _order("testing")), project
        )
        assert any("`verification`" in p and "not permitted" in p for p in problems)

    def test_documentation_needs_no_files_or_cases(self, enforced, project):
        assert readiness_problems(_plan(_order("documentation", files=[], test_cases=[], verification=[])), project) == []

    def test_it_can_be_switched_off(self, monkeypatch, project):
        monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "off")
        assert readiness_problems(_plan(_order("backend", files=[])), project) == []


class TestTheBrief:
    def test_the_specialist_sees_its_whole_work_order(self, project):
        task = _order("backend")
        text = build_specialist_task_request(
            task.task_description, task.acceptance_criteria, str(project), work_order=task
        )["messages"][0]["content"]
        for heading in ("Files you own in this task", "Interfaces to implement or call",
                        "--- Steps ---", "Edge cases and the rule for each",
                        "Test cases your work will be checked against", "Verify with",
                        "Out of scope - do not change"):
            assert heading in text, heading
        assert "1. one\n2. two" in text

    def test_the_testing_task_gets_the_other_tasks_contract(self):
        code, testing = _order("backend"), _order("testing", test_cases=[])
        text = contract_for_testing(testing, [code, testing])
        assert "do_backend(x) -> y" in text
        assert "Given x, when do_backend, then y" in text
        assert contract_for_testing(code, [code, testing]) == ""

    def test_an_empty_work_order_adds_nothing(self):
        assert brief_for(SpecialistTask(specialist_role="backend", task_description="Do it.")) == ""


class TestTheLeadIsGivenWhatAWorkOrderCopies:
    def test_the_contracts_carry_over_and_lessons_reach_the_lead(self):
        from app.agents.principal_architect import TechnicalSpecificationOutput

        spec = TechnicalSpecificationOutput.model_construct(
            product_scope="x", component_boundaries=["store module owns persistence"],
            domain_model=["Item {id, title}"], api_and_event_contracts=["addItem(title) -> Item"],
            data_flows=[], testing=["unit and end-to-end"],
        )
        text = build_milestone_planning_request(
            "plan", "goal", "/", specification=spec,
            carried_forward=["An empty note cannot be edited later (sprint 1 review, minor)"],
            lessons=["`node -e` was refused 5 times"],
        )["messages"][0]["content"]
        assert "addItem(title) -> Item" in text and "Item {id, title}" in text
        assert "Carried forward from earlier sprints" in text and "`carried_forward_decisions`" in text
        assert "`node -e` was refused 5 times" in text


def test_an_unready_plan_goes_back_to_the_lead_once_with_the_reasons(
    agents: ScriptedAgents, tmp_path: Any, enforced
) -> None:
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    unready = _plan(_order("backend", files=[]))
    ready = _plan(_order("backend", files=["acme-scheduling/backend.src"]), _order("testing", files=["acme-scheduling/test.src"]))
    agents.script("technical_lead", [responds_with(unready), responds_with(ready)])
    agents.script("specialist_backend", [responds_with(_specialist())])
    agents.script("specialist_testing", [responds_with(_specialist()), responds_with(_specialist())])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-work-orders")

    assert state["stage"] == "complete", state.get("error")
    second = agents.last_request_text("technical_lead")
    assert "YOUR PREVIOUS PLAN WAS NOT READY TO HAND OUT" in second
    assert "names no `files`" in second
    assert "No `testing` work order" in second
    assert "The plan that was sent back" in second


class TestAStructuredItemIsALine:
    """One run's lead wrote each test case as {"given", "when", "then"}; the
    schema wanted strings, refused it, and the next answer had no test cases."""

    def test_given_when_then_reads_as_a_sentence(self):
        task = SpecialistTask(
            specialist_role="backend", task_description="Add the edit path.",
            test_cases=[{"given": "an item titled 'a'", "when": "it is renamed to 'b'", "then": "the list shows 'b'"}],
        )
        assert task.test_cases == ["Given an item titled 'a', when it is renamed to 'b', then the list shows 'b'"]

    def test_other_keys_follow_and_a_single_key_is_its_value(self):
        task = SpecialistTask(
            specialist_role="backend", task_description="Add the edit path.",
            test_cases=[{"given": "g", "when": "w", "then": "t", "and": "nothing else changes"}],
            files=[{"path": "src/items.py"}],
            steps=[{"step": 1, "action": "write the handler"}],
        )
        assert task.test_cases == ["Given g, when w, then t; and nothing else changes"]
        assert task.files == ["src/items.py"]
        assert task.steps == ["step: 1; action: write the handler"]

    def test_strings_are_untouched(self):
        task = SpecialistTask(specialist_role="backend", task_description="Add the edit path.",
                              test_cases=["Given g, when w, then t"])
        assert task.test_cases == ["Given g, when w, then t"]


def test_a_pinned_project_directory_exists_before_anything_is_written(tmp_path):
    """Four to six calls a run were `ls` or a command in the pinned directory
    before any file had been written into it, each answered path_not_found."""
    from app.tools.repository import pin_the_directory_a_plan_names, pinned_project_directory

    pin_the_directory_a_plan_names(tmp_path, "Write shop-front/index.html and shop-front/app.js")

    assert pinned_project_directory(tmp_path) == "shop-front"
    assert (tmp_path / "shop-front").is_dir()
    assert list((tmp_path / "shop-front").iterdir()) == []


class TestAPlanThatBuildsNothing:
    """Measured on one run: the lead reasoned to its reply ceiling, answered from
    the recovery call with no work orders and a blocker, and the sprint went
    straight to a test round and two reviews of work nobody had been given."""

    def test_a_plan_with_no_work_orders_is_not_ready(self, enforced, project):
        problems = readiness_problems(_plan(), project)

        assert len(problems) == 1
        assert "hands out no work orders" in problems[0]

    def test_it_is_still_switched_off_with_the_rest(self, monkeypatch, project):
        monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "off")

        assert readiness_problems(_plan(), project) == []


class TestPathsTheWayTheProjectSeesThem:
    """A lead naming `src/app.js` means the project's `src/app.js`."""

    def _files(self, project, *paths: str) -> list[str]:
        from app.analysis.work_orders import with_paths_inside_the_project

        plan = with_paths_inside_the_project(_plan(_order("backend", files=list(paths))), project)
        return list(plan.delegated_tasks[0].files)

    def test_a_path_inside_the_project_gains_its_directory(self, project):
        assert self._files(project, "src/app.js", "index.html", "/tests/unit/a.test.js") == [
            "app/src/app.js",
            "app/index.html",
            "app/tests/unit/a.test.js",
        ]

    def test_a_path_already_in_the_project_or_in_docs_is_untouched(self, project):
        assert self._files(project, "app/src/app.js", "docs/notes.md") == ["app/src/app.js", "docs/notes.md"]

    def test_something_already_at_the_top_of_the_workspace_is_untouched(self, project):
        (project / "tools").mkdir()

        assert self._files(project, "tools/build.src") == ["tools/build.src"]

    def test_a_near_spelling_of_the_project_is_left_for_the_readiness_check(self, tmp_path):
        (tmp_path / "shop-app").mkdir()
        (tmp_path / ".project-directory").write_text("shop-app", encoding="utf-8")

        assert self._files(tmp_path, "shop_ap/core.src") == ["shop_ap/core.src"]

    def test_without_a_project_directory_nothing_changes(self, tmp_path):
        from app.analysis.work_orders import with_paths_inside_the_project

        plan = _plan(_order("backend", files=["src/app.js"]))

        assert with_paths_inside_the_project(plan, tmp_path) is plan

    def test_a_rewritten_plan_is_ready(self, enforced, project):
        from app.analysis.work_orders import with_paths_inside_the_project

        plan = with_paths_inside_the_project(
            _plan(_order("backend", files=["src/app.js"]), _order("testing", files=["tests/a.test.js"])), project
        )

        assert readiness_problems(plan, project) == []


def test_each_sprint_s_plan_gets_its_own_readiness_attempts(
    agents: ScriptedAgents, tmp_path: Any, enforced
) -> None:
    """Measured on one run: sprint 1 spent the three attempts, nothing reset the
    count, and sprint 2's first unready plan was dispatched without being sent
    back once."""
    from app.agents.scrum_master import SprintDefinition, SprintPlanOutput

    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(SprintPlanOutput(sprints=[
        SprintDefinition(goal="Sprint 1: booking", user_value="Patients can book"),
        SprintDefinition(goal="Sprint 2: reminders", user_value="Patients are reminded"),
    ]))])
    unready = _plan(_order("backend", files=[]))
    ready = _plan(_order("backend", files=["acme-scheduling/backend.src"]), _order("testing", files=["acme-scheduling/test.src"]))
    agents.script("technical_lead", [responds_with(unready)] * 3 + [responds_with(unready), responds_with(ready)])
    agents.script("specialist_backend", [responds_with(_specialist())] * 6)
    agents.script("specialist_testing", [responds_with(_specialist())] * 8)
    agents.script("milestone_reviewer", [responds_with(_milestone_review())] * 3)
    agents.script("security_reviewer", [responds_with(_security_review())] * 3)

    start_workflow(_graph(), _document(), _repository(tmp_path), "run-work-orders-per-sprint")

    asked = [payload["messages"][0]["content"] for payload in agents.requests["technical_lead"]]
    assert len(asked) == 5, len(asked)
    assert "YOUR PREVIOUS PLAN WAS NOT READY TO HAND OUT" not in asked[3]
    assert "YOUR PREVIOUS PLAN WAS NOT READY TO HAND OUT" in asked[4]


class TestCasesFromTheCriteria:
    """One run's lead answered `test_cases: []` for all seven work orders three
    times running, the third with concrete acceptance criteria on every one."""

    def _cases(self, *tasks: SpecialistTask) -> list[list[str]]:
        from app.analysis.work_orders import with_test_cases_from_its_criteria

        plan = with_test_cases_from_its_criteria(_plan(*tasks))
        return [list(task.test_cases) for task in plan.delegated_tasks]

    def test_a_code_work_order_without_cases_takes_its_criteria(self):
        assert self._cases(
            _order("ui_ux", test_cases=[], acceptance_criteria=["The form has a title field.", " "])
        ) == [["The form has a title field."]]

    def test_cases_the_lead_wrote_are_kept(self):
        assert self._cases(_order("backend")) == [["Given x, when do_backend, then y"]]

    def test_testing_and_documentation_are_left_as_they_are(self):
        assert self._cases(
            _order("testing", test_cases=[], acceptance_criteria=["suite passes"]),
            _order("documentation", test_cases=[], acceptance_criteria=["README explains setup"]),
        ) == [[], []]

    def test_with_no_criteria_either_it_is_still_not_ready(self, enforced, project):
        from app.analysis.work_orders import with_test_cases_from_its_criteria

        plan = with_test_cases_from_its_criteria(
            _plan(_order("backend", files=["app/x.src"], test_cases=[], acceptance_criteria=[]), _order("testing", files=["app/t.src"]))
        )

        assert any("no `test_cases`" in p for p in readiness_problems(plan, project))

    def test_a_plan_that_takes_them_is_ready(self, enforced, project):
        from app.analysis.work_orders import with_test_cases_from_its_criteria

        plan = with_test_cases_from_its_criteria(
            _plan(_order("backend", files=["app/x.src"], test_cases=[]), _order("testing", files=["app/t.src"]))
        )

        assert readiness_problems(plan, project) == []


class TestTheBestAttemptIsDispatched:
    """One run's second attempt was six work orders with three small problems;
    the third, after a reasoning spiral, was two - and the third was dispatched."""

    def test_fewer_problems_wins_then_more_work_orders(self):
        from app.graph.workflow import _the_better_plan

        good = _plan(_order("backend"), _order("ui_ux"), _order("testing"))
        thin = _plan(_order("ui_ux"))

        kept, problems = _the_better_plan((thin, ["a"]), (good.model_dump_json(), ["b"]))
        assert len(kept.delegated_tasks) == 3 and problems == ["b"]

        kept, problems = _the_better_plan((thin, ["a"]), (good.model_dump_json(), ["b", "c"]))
        assert kept is thin and problems == ["a"]

    def test_with_nothing_earlier_or_nothing_readable_the_current_one_stays(self):
        from app.graph.workflow import _the_better_plan

        plan = _plan(_order("backend"))

        assert _the_better_plan((plan, ["a"]), ("", []))[0] is plan
        assert _the_better_plan((plan, ["a"]), ("{not json", ["b"]))[0] is plan


def test_when_the_attempts_run_out_the_best_one_is_dispatched(
    agents: ScriptedAgents, tmp_path: Any, enforced
) -> None:
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    # Each has one problem - no testing work order - and the first has the most
    # work orders, so it is the one the sprint gets.
    best = _plan(_order("backend", files=["acme-scheduling/a.src"]), _order("database", files=["acme-scheduling/b.src"]))
    thin = _plan(_order("backend", files=["acme-scheduling/a.src"]))
    agents.script("technical_lead", [responds_with(best), responds_with(thin), responds_with(thin)])
    agents.script("specialist_backend", [responds_with(_specialist())] * 3)
    agents.script("specialist_database", [responds_with(_specialist())] * 3)
    agents.script("specialist_testing", [responds_with(_specialist())] * 3)
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-best-attempt")

    assert len(agents.requests["technical_lead"]) == 3
    assert agents.requests["specialist_database"], "the best attempt's database work order was never dispatched"
    assert state["stage"] == "complete", state.get("error")


class TestAWorkOrderWithNothingToTest:
    def test_a_manifest_only_work_order_needs_no_test_cases(self, enforced, project):
        problems = readiness_problems(
            _plan(_order("backend", files=["app/package.json"], test_cases=[], acceptance_criteria=[]), _order("testing", files=["app/t.src"])),
            project,
        )
        assert not any("no `test_cases`" in p for p in problems)

    def test_one_that_also_writes_product_code_still_does(self, enforced, project):
        problems = readiness_problems(
            _plan(_order("backend", files=["app/package.json", "app/cart.js"], test_cases=[], acceptance_criteria=[]), _order("testing", files=["app/t.src"])),
            project,
        )
        assert any("no `test_cases`" in p for p in problems)


class TestAVerificationThatBorrowsAFile:
    """One run's backend work order said "Verify with: node --test
    simple-to-do-list-app/tests/tasks.test.js"; the testing work order owned
    that file, and the backend specialist tried to write it seven times."""

    def _noted(self, *tasks):
        from app.analysis.work_orders import with_borrowed_files_noted

        return with_borrowed_files_noted(_plan(*tasks)).delegated_tasks

    def test_the_owner_is_named_and_writing_it_is_ruled_out(self):
        backend, testing = self._noted(
            _order("backend", files=["app/tasks.js"], verification=["node --test app/tests/tasks.test.js"]),
            _order("testing", title="Unit tests", files=["app/tests/tasks.test.js"], verification=["node --test"]),
        )

        assert "`app/tests/tasks.test.js` is written by work order 2 (testing: Unit tests)" in backend.task_description
        assert "Do not write it yourself" in backend.task_description
        assert "written by" not in testing.task_description

    def test_a_path_relative_to_the_project_is_recognised(self):
        backend, _ = self._noted(
            _order("backend", files=["app/tasks.js"], verification=["node --test ./tests/tasks.test.js"]),
            _order("testing", files=["app/tests/tasks.test.js"]),
        )

        assert "app/tests/tasks.test.js" in backend.task_description

    def test_its_own_files_and_plain_commands_add_nothing(self):
        plan = _plan(
            _order("backend", files=["app/tasks.js"], verification=["node --check app/tasks.js", "npm test"]),
            _order("testing", files=["app/tests/tasks.test.js"]),
        )
        from app.analysis.work_orders import with_borrowed_files_noted

        assert with_borrowed_files_noted(plan) is plan


class TestEveryFileTheSprintNamesHasAnOwner:
    """One run's sprint scope named index.html, style.css, app.js, ui.js and
    model.js; the plan covered only the state and storage modules, and the gap
    was found by the milestone review after the sprint had been built."""

    SCOPE = "Build the app.\nCreate index.html, style.css, app.js and state.js.\nAdd state.test.js."

    def test_a_named_file_no_work_order_lists_is_a_problem(self, enforced, project):
        problems = readiness_problems(
            _plan(_order("backend", files=["app/state.js"]), _order("testing", files=["app/state.test.js"])),
            project, sprint_scope=self.SCOPE,
        )

        found = [p for p in problems if "no work order lists" in p]
        assert found and "index.html" in found[0] and "style.css" in found[0] and "app.js" in found[0]
        assert "state.js" not in found[0].split("lists")[0].replace("state.test.js", "")

    def test_a_file_that_already_exists_needs_no_work_order(self, enforced, project):
        for name in ("index.html", "style.css", "app.js"):
            (project / "app" / name).write_text("x", encoding="utf-8")

        problems = readiness_problems(
            _plan(_order("backend", files=["app/state.js"]), _order("testing", files=["app/state.test.js"])),
            project, sprint_scope=self.SCOPE,
        )

        assert not any("no work order lists" in p for p in problems)

    def test_without_a_scope_nothing_changes(self, enforced, project):
        assert readiness_problems(_plan(_order("backend"), _order("testing", test_cases=[])), project) == []
