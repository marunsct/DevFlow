"""A stuck sprint that later sprints build on is not deferred past (LF.1264).

Measured on one run: sprint 1 of three (sign-up and sign-in) ended with 5 of its 18 acceptance tests passing; the
escalation decided on its own "defer and continue"; sprint 2's plan said "Dependencies: Sprint 1" and every one of
its tests began by signing up through the suite's helper; fifteen hours and about 60M tokens followed with the pass
count unchanged. The foundation is planned again with the failure named, or the run stops there as not deliverable.
A deferral nothing later needs still goes on to the next sprint.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.acceptance import junit, suite
from app.acceptance.criteria import number
from app.agents.scrum_master import SprintDefinition, SprintPlanOutput
from app.graph import escalation, foundation

BRIEF = (
    "# Brief\n## Features\n- Sign up\n- Sign in\n- Add a note\n- List notes\n- Delete a note\n- Search notes\n"
)
CONFIG = {"configurable": {"thread_id": "t"}}
STUCK = "Sprint 'Accounts' was re-planned 3 times and still could not be accepted"
NOT_FOUND = "assert 404 == 201"


def _plan(*, depends: bool) -> SprintPlanOutput:
    return SprintPlanOutput(sprints=[
        SprintDefinition(goal="Accounts", user_value="v", criteria=["AC-1", "AC-2"]),
        SprintDefinition(goal="Notes", user_value="v", criteria=["AC-3", "AC-4"],
                         dependencies=["Sprint 1"] if depends else []),
        SprintDefinition(goal="Search", user_value="v", criteria=["AC-5", "AC-6"]),
    ])


def _suite(root: Path, outcomes: dict[str, list[str]], *, problem: str = "") -> None:
    """The locked suite with each criterion's tests failing with the messages given ("" passes)."""
    (root / ".project-directory").write_text("notes\n")
    suite.save_criteria(root, number(BRIEF))
    spec = root / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True, exist_ok=True)
    names = [f"[{item}] t{k}" for item, messages in outcomes.items() for k in range(len(messages))]
    spec.write_text("".join(f"test('{name}', ()=>{{}});\n" for name in names))
    suite.lock(root)
    report = junit.Report(found=True, tests=[
        junit.TestResult(name=f"[{item}] t{k}", outcome="failed" if message else "passed", message=message)
        for item, messages in outcomes.items() for k, message in enumerate(messages)
    ])
    suite._judged(root, suite.AcceptanceResult(ran=True, command="npm run test:acceptance", report=report,
                                               problem=problem), True)


def _state(root: Path, plan: SprintPlanOutput, **extra: Any) -> dict[str, Any]:
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "sprint_plan": plan,
        "current_sprint_index": 0,
        "sprint_replan_count": 1,
        "escalation": {"error": STUCK},
        **extra,
    }


#: Sprint 1's sign-in fails; every later test stops at the same refused sign-up the suite's helper throws.
SIGN_UP_REFUSED = "Error: Sign up failed: 429 Too Many Requests"
MEASURED = {
    "AC-1": ["", ""],
    "AC-2": [SIGN_UP_REFUSED, SIGN_UP_REFUSED],
    "AC-3": [SIGN_UP_REFUSED, SIGN_UP_REFUSED],
    "AC-4": [SIGN_UP_REFUSED, SIGN_UP_REFUSED],
    "AC-5": [SIGN_UP_REFUSED, NOT_FOUND],
    "AC-6": [NOT_FOUND, NOT_FOUND],
}


def test_a_sprint_whose_failing_step_later_tests_also_stop_at_is_planned_again(tmp_path) -> None:
    _suite(tmp_path, MEASURED)

    update = escalation.escalation(_state(tmp_path, _plan(depends=False)), CONFIG, None)

    assert update["stage"] == "technical_lead"
    assert suite.deferred(tmp_path) == {}
    assert update["sprint_replan_count"] == 2
    guidance = " ".join(update["revision_comments"])
    assert "AC-2" in guidance and "Sign up failed: 429" in guidance
    decision = update["decisions"][-1]
    assert decision["decided_by"] == "auto" and decision["affects"] == ["AC-2"]
    assert "plan sprint 1 again" in decision["decision"]
    assert "Sign up failed: 429" in decision["rationale"]


def test_a_foundation_already_planned_again_stops_the_run_naming_it(tmp_path) -> None:
    _suite(tmp_path, MEASURED)
    state = _state(tmp_path, _plan(depends=False), foundation_replanned_sprints=[0])

    update = escalation.escalation(state, CONFIG, None)

    assert update["stage"] == "failed"
    assert suite.deferred(tmp_path) == {}
    assert "Not deliverable" in update["error"] and "Accounts" in update["error"]
    assert update["decisions"][-1]["decision"] == "stop the run"


def test_a_foundation_with_no_re_plans_left_stops_the_run(tmp_path) -> None:
    from app.graph.workflow import MAX_MILESTONE_REVISIONS

    _suite(tmp_path, MEASURED)
    state = _state(tmp_path, _plan(depends=False), sprint_replan_count=MAX_MILESTONE_REVISIONS)

    assert escalation.escalation(state, CONFIG, None)["stage"] == "failed"


def test_a_plan_dependency_on_a_mostly_failing_sprint_is_not_deferred_past(tmp_path) -> None:
    """The later tests give no shared step (their work is not built: "not found"), but the plan says sprint 2 depends
    on sprint 1, and sprint 1 passes one of its four tests."""
    _suite(tmp_path, {
        "AC-1": ["", "assert 500 == 200"], "AC-2": ["assert 500 == 201", "assert 500 == 201"],
        "AC-3": [NOT_FOUND], "AC-4": [NOT_FOUND], "AC-5": [NOT_FOUND], "AC-6": [NOT_FOUND],
    })

    update = escalation.escalation(_state(tmp_path, _plan(depends=True)), CONFIG, None)

    assert update["stage"] == "technical_lead"
    assert "sprint 2" in update["decisions"][-1]["rationale"]


def test_a_product_that_does_not_start_is_not_built_on(tmp_path) -> None:
    _suite(tmp_path, {item: [""] for item in ("AC-1", "AC-3", "AC-4", "AC-5", "AC-6")} | {"AC-2": ["boom"]},
           problem=f"{suite.PRODUCT_DID_NOT_START}: ModuleNotFoundError: No module named 'jose'")

    update = escalation.escalation(_state(tmp_path, _plan(depends=False)), CONFIG, None)

    assert update["stage"] == "technical_lead"
    assert "does not start" in update["decisions"][-1]["rationale"]


def test_a_person_asked_sees_that_later_sprints_build_on_the_sprint(tmp_path) -> None:
    _suite(tmp_path, MEASURED)
    state = _state(tmp_path, _plan(depends=False), review_policy={escalation.ESCALATION_REVIEW: True})

    assert escalation.escalation(state, CONFIG, None)["stage"] == "user_review_escalation"

    page = (tmp_path / "docs" / "reviews" / "escalation.md").read_text()
    assert "Later sprints build on this" in page and "Sign up failed: 429" in page


def test_a_deferral_nothing_later_needs_still_goes_on(tmp_path) -> None:
    """Sprint 2 depends on sprint 1, but sprint 1 passes most of its tests and the later tests fail only on work
    not built yet."""
    _suite(tmp_path, {
        "AC-1": ["", ""], "AC-2": ["", "assert 400 == 422"],
        "AC-3": [NOT_FOUND, NOT_FOUND], "AC-4": [NOT_FOUND], "AC-5": [NOT_FOUND], "AC-6": [NOT_FOUND],
    })

    update = escalation.escalation(_state(tmp_path, _plan(depends=True)), CONFIG, None)

    assert update["stage"] == "sprint_advance"
    assert "AC-2" in suite.deferred(tmp_path)


def test_no_plan_dependency_and_no_shared_step_keeps_the_deferral(tmp_path) -> None:
    _suite(tmp_path, {
        "AC-1": ["", "assert 500 == 200"], "AC-2": ["assert 500 == 201", "assert 500 == 201"],
        "AC-3": ["", ""], "AC-4": ["", ""], "AC-5": [NOT_FOUND], "AC-6": [NOT_FOUND],
    })

    update = escalation.escalation(_state(tmp_path, _plan(depends=False)), CONFIG, None)

    assert update["stage"] == "sprint_advance"
    assert set(suite.deferred(tmp_path)) == {"AC-1", "AC-2"}


def test_the_failing_step_reads_a_wrong_answer_or_a_helper_s_message_but_not_unbuilt_work() -> None:
    assert foundation.failure_step("assert 429 == 201") == "answered 429"
    assert foundation.failure_step("Error: Login rate limited\n  at login (helpers.js:12)") == "Error: Login rate limited"
    assert foundation.failure_step("assert 404 == 201") == ""
    assert foundation.failure_step("TimeoutError: locator('#search') timed out") == ""


def test_the_re_plan_guidance_avoids_the_banned_words() -> None:
    text = foundation.replan_guidance(1, "Accounts", ["AC-2"], ["the product does not start"])
    assert "AC-2" in text and "sprint 1" in text
    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", text, re.I)
