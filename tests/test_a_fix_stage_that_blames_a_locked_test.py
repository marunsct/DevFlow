"""A fix stage that blames a locked test has the test judged now, not after the attempt fails.

Measured on one run: sprint 4's locked responsive test had a logic error - it
switched to the "Active" view and expected no items, though the item it had
added was active. Every fix stage in two rounds, three of them sent to defects
already fixed, changed nothing and named that test as the reason; each defect
was left open. The QA lead's judgement of failing locked tests waited for the
attempt to fail, which cost the attempt's remaining rounds first.

Once per attempt, and only while the suite may still be repaired, the QA lead
now judges them when a fix stage blames one: a repaired suite goes back to the
round, and nothing to repair goes back to the remediation it interrupted.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.acceptance import suite
from app.acceptance.criteria import Criterion
from app.graph.workflow import (
    _a_dispute_may_be_held_now,
    _blames_a_locked_test,
    start_workflow,
)
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    ScriptedAgents,
    _approved_review,
    _defect,
    _document,
    _graph,
    _milestone,
    _milestone_review,
    _repository,
    _script_through_architecture,
    _security_review,
    _specialist,
    _sprint_plan,
    agents,
    responds_with,
)


@pytest.fixture
def locked(tmp_path: Path) -> Path:
    (tmp_path / ".project-directory").write_text("app\n")
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "stack-pack.json").write_text(json.dumps({
        "pack": "any", "project": "app", "acceptance_dir": "acceptance",
        "unit_report": "r/unit.xml", "acceptance_report": "r/acceptance.xml",
    }))
    (tmp_path / "app" / "acceptance").mkdir(parents=True)
    (tmp_path / "app" / "acceptance" / "views.spec.js").write_text("test('[AC-1] the views', async () => {});\n")
    suite.save_criteria(tmp_path, [Criterion("AC-1", "Views switch", "brief")])
    suite.lock(tmp_path)
    return tmp_path


def _state(root: Path, **extra: Any) -> dict[str, Any]:
    return {"repository": SimpleNamespace(root_path=str(root)), **extra}


class TestBlamed:
    def test_a_blocker_naming_a_locked_file(self, locked):
        blockers = ["The locked test views.spec.js line 43 expects no items after switching views"]

        assert _blames_a_locked_test(_state(locked), blockers)

    def test_a_blocker_naming_no_locked_file(self, locked):
        assert not _blames_a_locked_test(_state(locked), ["The port is taken"])

    def test_nothing_is_blamed_before_the_suite_is_locked(self, tmp_path):
        assert not _blames_a_locked_test(_state(tmp_path), ["views.spec.js is wrong"])


class TestWhenADisputeMayBeHeld:
    @pytest.fixture(autouse=True)
    def failing(self, monkeypatch):
        monkeypatch.setattr(
            "app.graph.workflow._the_locked_tests_still_failing",
            lambda state: [("[AC-1] the views", "AC-1: Views switch", "expected 0")],
        )

    def test_once_per_attempt(self, locked):
        assert _a_dispute_may_be_held_now(_state(locked))
        assert not _a_dispute_may_be_held_now(_state(locked, disputed_sprints=["0:0"]))

    def test_not_once_the_suite_s_repairs_are_spent(self, locked):
        from app.graph.acceptance_nodes import MAX_SUITE_REPAIRS_IN_ALL

        assert not _a_dispute_may_be_held_now(_state(locked, suite_repairs=MAX_SUITE_REPAIRS_IN_ALL))

    def test_not_without_a_failing_locked_test(self, locked, monkeypatch):
        monkeypatch.setattr("app.graph.workflow._the_locked_tests_still_failing", lambda state: [])

        assert not _a_dispute_may_be_held_now(_state(locked))


def test_a_change_that_left_it_open_and_a_decision_naming_the_test(
    agents: ScriptedAgents, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One run's fixer changed the stylesheet, named no regression test, and put
    "the remaining failure is a logic bug in the locked test" among its decisions.
    Left open for want of a regression test, not for a blocker, it is judged too."""
    seen: list[list[str]] = []
    held: list[int] = []
    monkeypatch.setattr(
        "app.graph.workflow._blames_a_locked_test",
        lambda state, said: seen.append(list(said)) or any("views.spec.js" in s for s in said),
    )
    monkeypatch.setattr(
        "app.graph.workflow._a_dispute_may_be_held_now",
        lambda state: not held and (held.append(1) or True),
    )
    monkeypatch.setattr("app.graph.workflow._the_locked_tests_still_failing", lambda state: [])
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    from app.agents.specialists import SpecialistOutput

    agents.script("specialist_backend", [
        responds_with(_specialist()),
        responds_with(SpecialistOutput(
            decisions=["The remaining failure is a logic bug in the locked views.spec.js"],
        )),
        responds_with(_specialist(tests=["tests/test_bookings_regression.py"])),
    ])
    agents.script("specialist_testing", [
        responds_with(_specialist(defects=[_defect(owner="backend")])),
        responds_with(_specialist()),
        responds_with(_specialist()),
    ])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-decided")

    assert state["stage"] == "complete", state.get("error")
    assert held == [1]
    assert any("views.spec.js" in s for said in seen for s in said)


def test_the_round_goes_on_after_a_dispute_that_finds_nothing(
    agents: ScriptedAgents, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Blamed, judged once, nothing to repair: remediation carries on and the run completes."""
    held: list[int] = []
    monkeypatch.setattr("app.graph.workflow._blames_a_locked_test", lambda state, blockers: True)
    monkeypatch.setattr(
        "app.graph.workflow._a_dispute_may_be_held_now",
        lambda state: not held and (held.append(1) or True),
    )
    monkeypatch.setattr("app.graph.workflow._the_locked_tests_still_failing", lambda state: [])
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    agents.script("specialist_backend", [
        responds_with(_specialist()),
        responds_with(_specialist(["views.spec.js cannot pass whatever is built"])),
        responds_with(_specialist(tests=["tests/test_bookings_regression.py"])),
    ])
    agents.script("specialist_testing", [
        responds_with(_specialist(defects=[_defect(owner="backend")])),
        responds_with(_specialist()),
        responds_with(_specialist()),
    ])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-blamed")

    assert state["stage"] == "complete", state.get("error")
    assert held == [1]
    assert state.get("disputed_sprints")
    assert not state.get("dispute_returns_to")


class TestTwoLockedTestsThatAskForOppositeThings:
    """One run's locked delete test wanted new items last and its list test wanted
    them first. Each fix that made one pass broke the other and was reverted,
    twice in one round."""

    REVERTED = "A fix was tried and reverted, because it broke what passed before it: {}."

    def _cycle(self, *broken: str):
        from app.sprint import Defect, RemediationCycle

        return RemediationCycle(sprint_goal="s", defects=[
            Defect(
                description=f"d{n}", severity="major", reproduction_steps="r", expected_behavior="e",
                actual_behavior="It fails.\n" + self.REVERTED.format(names), owner="ui_ux",
            )
            for n, names in enumerate(broken)
        ])

    def test_two_reverts_for_one_locked_test_name_it(self):
        from app.graph.workflow import _a_locked_test_two_fixes_broke

        name = "acceptance: todo.spec.js › [AC-8] items appear in a list"
        cycle = self._cycle(name, f"{name}; acceptance: todo.spec.js › [AC-1] adds")

        assert _a_locked_test_two_fixes_broke(cycle) == name

    def test_one_revert_is_a_bad_fix(self):
        from app.graph.workflow import _a_locked_test_two_fixes_broke

        assert _a_locked_test_two_fixes_broke(self._cycle("acceptance: a › [AC-8] x")) == ""

    def test_a_unit_test_is_not_the_locked_suite(self):
        from app.graph.workflow import _a_locked_test_two_fixes_broke

        assert _a_locked_test_two_fixes_broke(self._cycle("unit: a › b", "unit: a › b")) == ""

    def test_the_qa_lead_is_told_why(self):
        from app.graph.workflow import _with_the_reason

        request = _with_the_reason({"messages": [{"role": "user", "content": "judge these"}]}, "two fixes broke X")

        assert request["messages"][-1]["content"].endswith("--- Why this is judged now ---\ntwo fixes broke X\n")

    def test_no_reason_adds_nothing(self):
        from app.graph.workflow import _with_the_reason

        assert _with_the_reason({"messages": [{"role": "user", "content": "x"}]}, "")["messages"][-1]["content"] == "x"


def test_a_one_word_title_does_not_blame_and_a_leading_tag_title_does(tmp_path, monkeypatch):
    from types import SimpleNamespace as _NS

    from app.acceptance import suite as _suite
    from app.graph import workflow as _workflow

    monkeypatch.setattr(_suite, "is_locked", lambda root: True)
    monkeypatch.setattr(_suite, "suite_files", lambda root: [])
    monkeypatch.setattr(_suite, "declared_tests", lambda root: [("a.spec.ts", "Accounts"), ("a.spec.ts", "[AC-3] a completed item stays done"),
                                                                  ("t.py", "test_ac9_empty[case1]")])
    state = {"repository": _NS(root_path=str(tmp_path))}
    assert not _workflow._blames_a_locked_test(state, ["Accounts are stored in the wrong table"])
    assert _workflow._blames_a_locked_test(state, ["The test [AC-3] a completed item stays done expects the wrong status"])
    assert _workflow._blames_a_locked_test(state, ["test_ac9_empty asserts 400 where 422 is answered"])
