"""The acceptance suite is written and locked a sprint at a time where the product is planned as more (LF.1266).

Measured on a medium brief: the whole suite - 97 tests for 13 criteria - was written and locked before any code, one
account per test and seven copies of its helpers, and locked "with these still open". For a product that may be
planned as more than one sprint, the plan now comes first; each sprint's tests are written and locked by QA at that
sprint's start, against the running product of the earlier sprints; each lock only adds; and at release every criterion
has locked tests or is named as a gap. A product planned as one sprint is written, locked and planned as before.

These drive the real nodes on a three-sprint plan; the model calls and the sandbox's edge (the test command, run by
this interpreter) are the only stand-ins.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.acceptance import by_sprint, junit, sprint_scope, suite
from app.acceptance.criteria import Criterion
from app.agents.scrum_master import SprintDefinition, SprintPlanOutput
from app.graph import acceptance_nodes as nodes
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
PROJECT = "items"
CONFIG = {"configurable": {"thread_id": "t"}}
CTX = nodes.Context(model=None, judgement_model=None, checkpointer=None, repo_root=None)
CRITERIA = [Criterion(f"AC-{n}", text, "brief") for n, text in enumerate((
    "An item can be added", "An item can be renamed", "An item can be deleted",
    "Items are listed newest first", "Items can be searched by name", "Items can be exported",
), 1)]
#: Two criteria a sprint, three sprints.
PLAN = [["AC-1", "AC-2"], ["AC-3", "AC-4"], ["AC-5", "AC-6"]]


def _plan(groups=PLAN) -> SprintPlanOutput:
    return SprintPlanOutput(sprints=[
        SprintDefinition(goal=f"Sprint {n} of the item store", user_value="v", criteria=list(ids))
        for n, ids in enumerate(groups, 1)])


def _workspace(root: Path) -> Path:
    contract.write(root, pack_named("python-http-api"), PROJECT, "Items")
    (root / PROJECT / "acceptance").mkdir(parents=True, exist_ok=True)
    suite.save_criteria(root, CRITERIA)
    return root


def _state(root: Path, **extra: Any) -> dict[str, Any]:
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "document": SimpleNamespace(text="# Items\n" + "".join(f"- {c.text}\n" for c in CRITERIA)),
        "product_intake": SimpleNamespace(product_name="Items", success_measures=[]),
        **extra,
    }


class RealPytest:
    """The sandbox's edge: runs the suite's command with this interpreter, in the project, and records each argv."""

    def __init__(self, root: Path) -> None:
        self.root, self.commands = root, []

    def __call__(self, argv, category, where):
        if category != "test":
            return {"returncode": "0"}
        self.commands.append(list(argv))
        done = subprocess.run(
            [sys.executable, *argv[1:], "-p", "no:cacheprovider"], cwd=self.root / where,
            capture_output=True, text=True, timeout=120, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        return {"returncode": str(done.returncode), "stdout": done.stdout, "stderr": done.stderr}


def _a_test_of(criterion: str) -> str:
    """A test of one criterion that fails as a product not built yet fails it."""
    number = criterion.split("-")[1]
    return (f"def test_ac{number}_holds():\n"
            f"    answer = {{'status': 404}}\n"
            f"    assert answer['status'] == 200, 'the product answered 404'\n\n")


class Writers:
    """QA's agent loop at its edge: each call writes one new file of tests for the criteria it was asked for."""

    def __init__(self, root: Path) -> None:
        self.root, self.asked, self.reviews = root, [], 0
        self.also: dict[str, str] = {}

    def __call__(self, state, config, *, stage_name, agent, initial_request, output_key, next_stage):
        text = initial_request["messages"][-1]["content"]
        if output_key == "__acceptance_review__":
            self.reviews += 1
            return {output_key: SimpleNamespace(approved=True, findings=[]), "stage": next_stage}
        section = text.split("--- Acceptance criteria ---")[1].split("---")[0]
        ids = re.findall(r"AC-\d+", section)
        self.asked.append((ids, text))
        folder = self.root / PROJECT / "acceptance"
        name = f"test_part_{len(self.asked)}.py"
        (folder / name).write_text("".join(_a_test_of(i) for i in ids))
        for relative, content in self.also.items():
            (self.root / relative).write_text(content)
        return {output_key: SimpleNamespace(blockers=[]), "stage": next_stage}


@pytest.fixture
def thorough(tmp_path, monkeypatch):
    """A thorough run: six criteria may be planned as up to two sprints, so the suite is written a sprint at a time."""
    monkeypatch.setenv("DELIVERY_MODE", "thorough")
    writers = Writers(_workspace(tmp_path))
    runner = RealPytest(tmp_path)
    monkeypatch.setattr("app.graph.workflow._run_gated_agent", writers)
    monkeypatch.setattr("app.agents.specialists.create_specialist_agent", lambda *a, **k: object())
    monkeypatch.setattr("app.agents.acceptance_reviewer.create_acceptance_reviewer_agent", lambda *a, **k: object())
    monkeypatch.setattr(suite, "_sandbox_runner", lambda root: runner)
    return SimpleNamespace(root=tmp_path, writers=writers, runner=runner)


def _tests_ran(root: Path) -> list[str]:
    return sorted(test.name for test in junit.read(root / PROJECT / "test-results" / "acceptance.xml").tests)


def _start_sprint(root: Path, index: int, plan=None) -> dict[str, Any]:
    """`sprint_acceptance` at sprint `index` (0-based); the update."""
    return nodes.sprint_acceptance(_state(root, sprint_plan=plan or _plan(), current_sprint_index=index), CONFIG, CTX)


def _write_and_lock(root: Path, index: int, plan=None) -> dict[str, Any]:
    """A sprint's start through its lock: the review's update."""
    state = _state(root, sprint_plan=plan or _plan(), current_sprint_index=index)
    started = nodes.sprint_acceptance(state, CONFIG, CTX)
    assert started["stage"] == "acceptance_author"
    written = nodes.acceptance_author({**state, **started}, CONFIG, CTX)
    return nodes.acceptance_review({**state, **started, **written}, CONFIG, CTX)


def _declared(root: Path) -> list[str]:
    return sorted(name for _, name in suite.declared_tests(root))


class TestTheOrder:
    def test_a_product_that_may_take_more_than_one_sprint_is_planned_before_any_test_is_written(self, thorough):
        update = nodes.acceptance_author(_state(thorough.root), CONFIG, CTX)

        assert update["stage"] == "scrum_master"
        assert thorough.writers.asked == []
        assert not suite.is_locked(thorough.root) and _declared(thorough.root) == []

    def test_its_plan_goes_to_sprint_one_s_tests_with_the_criteria_numbered(self, thorough, monkeypatch):
        from workflow_node_stubs import run_node

        nodes.acceptance_author(_state(thorough.root), CONFIG, CTX)

        seen = run_node(monkeypatch, thorough.root, "scrum_master", answer=_plan(),
                        technical_specification="The specification.")

        assert seen.update["stage"] == "sprint_acceptance"
        asked = seen.requests[0][1]["messages"][-1]["content"]
        assert all(c.id in asked for c in CRITERIA)

    def test_a_product_planned_as_one_sprint_is_written_whole_then_planned_as_before(self, thorough, monkeypatch):
        monkeypatch.setenv("DELIVERY_MODE", "fast")

        written = nodes.acceptance_author(_state(thorough.root), CONFIG, CTX)
        locked = nodes.acceptance_review({**_state(thorough.root), **written}, CONFIG, CTX)

        assert written["stage"] == "acceptance_review"
        assert thorough.writers.asked[0][0] == [c.id for c in CRITERIA]
        assert locked["stage"] == "scrum_master" and suite.is_locked(thorough.root)
        assert not by_sprint.is_on(thorough.root)


class TestSprintOne:
    @pytest.fixture
    def planned(self, thorough):
        nodes.acceptance_author(_state(thorough.root), CONFIG, CTX)
        return thorough

    def test_only_sprint_one_s_criteria_are_written_before_sprint_one(self, planned):
        state = _state(planned.root, sprint_plan=_plan(), current_sprint_index=0)
        started = nodes.sprint_acceptance(state, CONFIG, CTX)

        nodes.acceptance_author({**state, **started}, CONFIG, CTX)

        ids, text = planned.writers.asked[0]
        assert ids == ["AC-1", "AC-2"]
        assert "sprint 1's part, of 3" in text

    def test_sprint_one_s_lock_holds_its_tests_alone_and_goes_to_its_lead(self, planned):
        locked = _write_and_lock(planned.root, 0)

        assert locked["stage"] == "technical_lead" and suite.is_locked(planned.root)
        assert _declared(planned.root) == ["test_ac1_holds", "test_ac2_holds"]
        assert _tests_ran(planned.root) == ["test_ac1_holds", "test_ac2_holds"]
        assert locked["acceptance_open_problems"] == []
        assert {c["status"] for k, c in locked["acceptance_result"]["criteria"].items() if k in PLAN[2]} == {"not_yet_due"}


class TestALaterSprint:
    @pytest.fixture
    def sprint_one_locked(self, thorough):
        nodes.acceptance_author(_state(thorough.root), CONFIG, CTX)
        _write_and_lock(thorough.root, 0)
        return thorough

    def test_the_next_sprint_starts_at_its_own_tests(self, sprint_one_locked):
        from app.graph.nodes.closing import sprint_advance_node

        update = sprint_advance_node(_state(sprint_one_locked.root, sprint_plan=_plan(), current_sprint_index=0), CONFIG)

        assert update["stage"] == "sprint_acceptance" and update["current_sprint_index"] == 1

    def test_sprint_two_s_tests_are_written_and_locked_at_its_start_and_sprint_one_s_still_run(self, sprint_one_locked):
        root = sprint_one_locked.root
        first = (root / PROJECT / "acceptance" / "test_part_1.py").read_text()

        locked = _write_and_lock(root, 1)

        assert sprint_one_locked.writers.asked[-1][0] == ["AC-3", "AC-4"]
        assert locked["stage"] == "technical_lead" and suite._state(root)["lock_version"] == 2
        assert (root / PROJECT / "acceptance" / "test_part_1.py").read_text() == first
        assert _tests_ran(root) == ["test_ac1_holds", "test_ac2_holds", "test_ac3_holds", "test_ac4_holds"]

    def test_its_writers_are_told_what_is_locked_and_what_decides_a_test(self, sprint_one_locked):
        _write_and_lock(sprint_one_locked.root, 1)

        text = sprint_one_locked.writers.asked[-1][1]
        assert "items/acceptance/test_part_1.py" in text and "put back" in text
        assert "never open the product's files" in text
        assert "Nothing of the product's features is built yet" not in text

    def test_a_change_to_an_earlier_sprint_s_file_is_put_back_and_said(self, sprint_one_locked):
        root = sprint_one_locked.root
        earlier = root / PROJECT / "acceptance" / "test_part_1.py"
        first = earlier.read_text()
        sprint_one_locked.writers.also = {f"{PROJECT}/acceptance/test_part_1.py": "def test_ac1_holds():\n    pass\n"}
        state = _state(root, sprint_plan=_plan(), current_sprint_index=1)
        started = nodes.sprint_acceptance(state, CONFIG, CTX)
        written = nodes.acceptance_author({**state, **started}, CONFIG, CTX)

        sent = nodes.acceptance_review({**state, **started, **written}, CONFIG, CTX)

        assert earlier.read_text() == first
        assert sent["stage"] == "acceptance_author"
        said = [item for item in sent["acceptance_feedback"] if "test_part_1.py" in item and "back as it was locked" in item]
        assert said and not BANNED.search(said[0])

    def test_qa_adding_a_sprint_is_refused_a_write_to_an_earlier_sprint_s_file(self, sprint_one_locked, monkeypatch):
        from app.tools import repository

        _start_sprint(sprint_one_locked.root, 1)
        monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda default="": "acceptance_author_0")

        with pytest.raises(repository.RepositoryToolError) as refused:
            repository.write_approved_artifact(sprint_one_locked.root, f"{PROJECT}/acceptance/test_part_1.py", "x = 1\n")

        assert "earlier sprint" in str(refused.value)
        assert not BANNED.search(str(refused.value))

    def test_qa_adding_a_sprint_may_write_a_new_file(self, sprint_one_locked, monkeypatch):
        from app.tools import repository

        _start_sprint(sprint_one_locked.root, 1)
        monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda default="": "acceptance_author_0")

        repository.write_approved_artifact(sprint_one_locked.root, f"{PROJECT}/acceptance/test_part_2.py", _a_test_of("AC-3"))

        assert (sprint_one_locked.root / PROJECT / "acceptance" / "test_part_2.py").is_file()

    def test_an_addition_that_never_runs_is_left_out_and_the_run_goes_on(self, sprint_one_locked, monkeypatch):
        root = sprint_one_locked.root
        state = _state(root, sprint_plan=_plan(), current_sprint_index=1, acceptance_round=nodes.MAX_ACCEPTANCE_ROUNDS + 2)
        nodes.sprint_acceptance(state, CONFIG, CTX)
        (root / PROJECT / "acceptance" / "test_part_2.py").write_text("def test_ac3_holds(:\n")

        update = nodes.acceptance_review(state, CONFIG, CTX)

        assert update["stage"] == "technical_lead"
        assert not (root / PROJECT / "acceptance" / "test_part_2.py").exists()
        assert set(suite.deferred(root)) == {"AC-3", "AC-4"} and suite.is_locked(root)


class TestTheRelease:
    @pytest.fixture
    def two_sprints_locked(self, thorough):
        nodes.acceptance_author(_state(thorough.root), CONFIG, CTX)
        _write_and_lock(thorough.root, 0)
        _write_and_lock(thorough.root, 1)
        return thorough

    def _release(self, root: Path, monkeypatch) -> dict[str, Any]:
        from app.graph import delivery

        monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)
        return delivery.release(_state(root, sprint_plan=_plan(), current_sprint_index=2), CONFIG, None)

    def test_the_release_has_qa_write_the_tests_of_a_criterion_no_locked_test_names(self, two_sprints_locked, monkeypatch):
        update = self._release(two_sprints_locked.root, monkeypatch)

        assert update["stage"] == "acceptance_author" and update["acceptance_return_to"] == "release"
        assert by_sprint.addition(two_sprints_locked.root)["criteria"] == ["AC-5", "AC-6"]

    def test_one_still_without_a_test_after_that_ships_as_a_named_cut(self, two_sprints_locked, monkeypatch):
        from app import completion_verdict

        root = two_sprints_locked.root
        self._release(root, monkeypatch)
        suite.lock(root)  # QA wrote nothing for them
        built = junit.Report(found=True, tests=[junit.TestResult(name=f"test_ac{n}_holds") for n in range(1, 5)])
        monkeypatch.setattr(suite, "run", lambda root: suite._judged(
            root, suite.AcceptanceResult(ran=True, exit_code=0, command="pytest", report=built), True))
        monkeypatch.setattr("app.graph.delivery._unit_tests_failing", lambda root: [])
        monkeypatch.setattr("app.stacks.production_build.failure", lambda root: "")

        update = self._release(root, monkeypatch)

        assert suite.deferred(root) == {"AC-5": by_sprint.NEVER_WRITTEN, "AC-6": by_sprint.NEVER_WRITTEN}
        cuts = [gap for gap in update.get("completion_gaps") or [] if completion_verdict.is_a_cut(gap)]
        assert [gap.split(" ", 1)[0] for gap in cuts] == ["AC-5", "AC-6"]


class TestARePlan:
    def test_a_criterion_moved_to_a_later_sprint_takes_its_tests_and_one_moved_earlier_is_written(self, thorough):
        root = thorough.root
        nodes.acceptance_author(_state(root), CONFIG, CTX)
        _write_and_lock(root, 0)
        replanned = _plan([["AC-1", "AC-3"], ["AC-4"], ["AC-2", "AC-5", "AC-6"]])

        started = _start_sprint(root, 0, replanned)

        assert by_sprint.addition(root)["criteria"] == ["AC-3"]
        assert "AC-2" in sprint_scope.not_yet_due(root)
        assert started["stage"] == "acceptance_author"


class TestTheReaders:
    def test_a_criterion_whose_sprint_has_not_started_is_no_gap(self, tmp_path):
        _workspace(tmp_path)
        (tmp_path / PROJECT / "acceptance" / "test_one.py").write_text(_a_test_of("AC-1") + _a_test_of("AC-2"))
        sprint_scope.record(tmp_path, sprint=1, of=3, not_yet_due=["AC-3", "AC-4", "AC-5", "AC-6"], sprints=PLAN)

        assert suite.gaps(tmp_path) == []

    def test_at_release_every_criterion_without_a_test_is_a_gap_again(self, tmp_path):
        _workspace(tmp_path)
        (tmp_path / PROJECT / "acceptance" / "test_one.py").write_text(_a_test_of("AC-1") + _a_test_of("AC-2"))
        sprint_scope.record(tmp_path, sprint=1, of=3, not_yet_due=["AC-3", "AC-4", "AC-5", "AC-6"], sprints=PLAN)
        sprint_scope.record_everything_due(tmp_path)

        assert [gap.split(" ", 1)[0] for gap in suite.gaps(tmp_path)] == ["AC-3", "AC-4", "AC-5", "AC-6"]

    def test_the_foundation_check_reads_an_unwritten_later_criterion_as_no_evidence(self):
        from app.graph import foundation

        sprints = [SimpleNamespace(criteria=["AC-1", "AC-2"], dependencies=[]),
                   SimpleNamespace(criteria=["AC-3", "AC-4"], dependencies=["Sprint 1"])]
        failed = {"outcome": "failed", "message": "assert 429 == 201"}
        saved = {"criteria": {
            "AC-1": {"status": "failed", "tests": [{**failed, "name": "a"}, {**failed, "name": "b"}]},
            "AC-2": {"status": "failed", "tests": [{**failed, "name": "c"}]},
            "AC-3": {"status": "not_yet_due", "tests": []}, "AC-4": {"status": "not_yet_due", "tests": []},
        }}

        reasons = foundation.later_work_needs(sprints, 0, saved, ["AC-1", "AC-2"], ["AC-1", "AC-2"])

        assert reasons == ["the plan has sprint 2 depend on sprint 1, which passes 0 of its 3 acceptance tests"]


class TestFindingsInAnAddition:
    def test_a_finding_about_a_later_sprint_s_criterion_alone_is_not_sprint_one_s(self, thorough):
        nodes.acceptance_author(_state(thorough.root), CONFIG, CTX)
        _start_sprint(thorough.root, 0)
        findings = ["AC-5: no test searches by name", "AC-1 and AC-5 share one weak assertion", "the suite is slow"]

        assert by_sprint.about_the_addition(thorough.root, findings) == findings[1:]

    def test_a_finding_about_an_earlier_sprint_s_locked_test_alone_is_not_the_addition_s(self, thorough):
        root = thorough.root
        nodes.acceptance_author(_state(root), CONFIG, CTX)
        _write_and_lock(root, 0)
        _start_sprint(root, 1)
        (root / PROJECT / "acceptance" / "test_part_2.py").write_text(_a_test_of("AC-3"))
        findings = ["`test_ac1_holds` in items/acceptance/test_part_1.py asserts a status only",
                    "`test_ac3_holds` asserts a status only"]

        assert by_sprint.about_the_addition(root, findings) == findings[1:]


class TestWhatTheModelsAreTold:
    def test_none_of_it_uses_the_banned_words(self):
        group = [SimpleNamespace(id="AC-3"), SimpleNamespace(id="AC-4")]
        texts = [
            by_sprint.note(2, 3, group, ["items/acceptance/test_part_1.py"]),
            by_sprint.note(1, 3, group, []),
            by_sprint.note(3, 3, group, ["a.py"]),
            by_sprint.review_note(["AC-3"], ["items/acceptance/test_part_2.py"], ["items/acceptance/test_part_1.py"]),
            by_sprint.EARLIER_SPRINTS_BUILT, by_sprint.RUN_AN_ADDITION_ONCE,
            __import__("app.acceptance.requests", fromlist=["x"]).LOCKED_WITH_AN_EARLIER_SPRINT,
        ]
        assert not [text for text in texts if BANNED.search(text)]

    def test_the_qa_lead_reviews_only_the_sprint_s_addition(self, thorough, monkeypatch):
        root = thorough.root
        nodes.acceptance_author(_state(root), CONFIG, CTX)
        _write_and_lock(root, 0)
        asked = []

        def recording(state, config, **kwargs):
            if kwargs["output_key"] == "__acceptance_review__":
                asked.append(kwargs["initial_request"]["messages"][-1]["content"])
            return thorough.writers(state, config, **kwargs)

        monkeypatch.setattr("app.graph.workflow._run_gated_agent", recording)

        _write_and_lock(root, 1)

        assert "This review is of one sprint's addition" in asked[-1]
        assert "def test_ac1_holds" not in asked[-1] and "def test_ac3_holds" in asked[-1]
