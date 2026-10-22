"""A suite that proved nothing is not a green suite, at any gate.

A runner that collected zero of the suite's tests exits without complaint:
zero tests, exit 0, every count green, every criterion "untested" - which a
dispute can defer and a release then ship. Measured on one run: the
scaffold's own smoke test ran zero tests, exited 0, and the setup was left to
the agents. And the round count used to waive the very problems that say the
suite proved nothing: after the last round the suite was locked with them
still open, and a release only ever asked whether a criterion was failing.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.acceptance import junit, suite
from app.acceptance.criteria import number
from app.graph import acceptance_nodes as nodes
from app.graph import delivery

BRIEF = """# Brief
## Features
- Add a note
- Delete a note
## Acceptance Criteria
- Notes persist between page refreshes
"""

CONFIG = {"configurable": {"thread_id": "t"}}
CTX = nodes.Context(model=None, judgement_model=None, checkpointer=None, repo_root=None)

ALL_THREE = (
    "test('[AC-1] adds', async () => {});\n"
    "test('[AC-2] deletes', async () => {});\n"
    "test('[AC-3] persists', async () => {});\n"
)


def _state(root: Path, **extra: Any) -> dict[str, Any]:
    (root / ".project-directory").write_text("notes\n")
    (root / "notes").mkdir(exist_ok=True)
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "document": SimpleNamespace(text=BRIEF),
        "product_intake": SimpleNamespace(product_name="Notes", success_measures=[]),
        "stack_selection": SimpleNamespace(technology_stack=SimpleNamespace(product_kind="browser_app")),
        **extra,
    }


def _authored(root: Path, spec: str = ALL_THREE) -> None:
    (root / ".project-directory").write_text("notes\n")
    suite.save_criteria(root, number(BRIEF))
    target = root / "notes" / "acceptance" / "notes.spec.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(spec)


def _ran(*tests: junit.TestResult, exit_code: int = 0) -> suite.AcceptanceResult:
    return suite.AcceptanceResult(
        ran=True, exit_code=exit_code, command="npm run test:acceptance",
        report=junit.Report(found=True, tests=list(tests)),
    )


def _plan(*criteria_per_sprint: list[str]) -> Any:
    return SimpleNamespace(sprints=[SimpleNamespace(criteria=list(c)) for c in criteria_per_sprint])


# --- the check itself -------------------------------------------------------------

def test_zero_collected_tests_is_named(tmp_path) -> None:
    _authored(tmp_path)

    problems = suite.vacuous_green(tmp_path, _ran())

    assert len(problems) == 1 and "zero tests" in problems[0]


def test_a_run_whose_tests_check_no_criterion_is_named(tmp_path) -> None:
    _authored(tmp_path, "test('smoke', async () => {});\n")

    problems = suite.vacuous_green(tmp_path, _ran(junit.TestResult(name="smoke")))

    assert len(problems) == 1 and "criterion" in problems[0]


def test_a_declared_test_the_runner_never_collected_is_named(tmp_path) -> None:
    _authored(tmp_path)
    result = _ran(junit.TestResult(name="[AC-1] adds"), junit.TestResult(name="[AC-2] deletes"))

    problems = suite.vacuous_green(tmp_path, result)

    assert len(problems) == 1 and "[AC-3] persists" in problems[0]


def test_a_run_that_collected_every_declared_test_is_not_vacuous(tmp_path) -> None:
    _authored(tmp_path)
    result = _ran(*(junit.TestResult(name=n) for n in
                    ("[AC-1] adds", "[AC-2] deletes", "[AC-3] persists")))

    assert suite.vacuous_green(tmp_path, result) == []


def test_a_suite_that_never_ran_is_the_gate_s_own_problem(tmp_path) -> None:
    _authored(tmp_path)

    assert suite.vacuous_green(tmp_path, suite.AcceptanceResult(ran=False)) == []


def test_the_vacuous_green_messages_name_no_product_word(tmp_path) -> None:
    """The messages reach the QA stage and the release record verbatim."""
    _authored(tmp_path)
    banned = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")
    seen = [
        *suite.vacuous_green(tmp_path, _ran()),
        *suite.vacuous_green(tmp_path, _ran(junit.TestResult(name="smoke"))),
    ]
    assert seen
    for problem in seen:
        for word in banned:
            assert not re.search(rf"\b{re.escape(word)}\b", problem, re.IGNORECASE), word


# --- the lock ------------------------------------------------------------------------

@pytest.fixture
def approved(monkeypatch):
    """The QA lead approves, so only the mechanical gate can hold the lock back."""
    def run(state, config, *, stage_name, agent, initial_request, output_key, next_stage):
        return {output_key: SimpleNamespace(approved=True, findings=[]), "stage": next_stage}

    monkeypatch.setattr("app.graph.workflow._run_gated_agent", run)
    monkeypatch.setattr(
        "app.agents.acceptance_reviewer.create_acceptance_reviewer_agent", lambda *a, **k: object()
    )


def test_a_suite_that_proved_nothing_is_never_locked(tmp_path, approved, monkeypatch) -> None:
    _authored(tmp_path)
    monkeypatch.setattr(suite, "run", lambda root: _ran())

    update = nodes.acceptance_review(
        _state(tmp_path, acceptance_round=nodes.MAX_ACCEPTANCE_ROUNDS), CONFIG, CTX
    )

    assert not suite.is_locked(tmp_path)
    assert update["stage"] == "acceptance_author"
    assert any("zero tests" in str(item) for item in update["acceptance_feedback"])


def test_after_the_last_round_a_suite_that_proves_nothing_fails_the_run(
    tmp_path, approved, monkeypatch
) -> None:
    _authored(tmp_path)
    monkeypatch.setattr(suite, "run", lambda root: _ran())

    update = nodes.acceptance_review(
        _state(tmp_path, acceptance_round=nodes.MAX_ACCEPTANCE_ROUNDS + 2), CONFIG, CTX
    )

    assert not suite.is_locked(tmp_path)
    assert update["stage"] == "failed"
    assert "zero tests" in str(update.get("error") or "")


# --- the test round -------------------------------------------------------------------

def test_a_round_whose_suite_proved_nothing_reopens_the_suite(tmp_path, monkeypatch) -> None:
    """Zero collected tests is the suite's defect, not a product defect per criterion."""
    _authored(tmp_path)
    suite.lock(tmp_path)
    judged = suite._judged(tmp_path, _ran(), False)
    monkeypatch.setattr(suite, "run", lambda root: judged)
    state = _state(
        tmp_path,
        sprint_plan=_plan(["AC-1", "AC-2"], ["AC-3"]),
        current_sprint_index=0,
    )

    _, broken = nodes.acceptance_for_round(state)

    assert any("zero tests" in str(item) for item in broken)


# --- the release -------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_cancel(monkeypatch):
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)


def test_a_release_is_held_when_the_suite_proved_nothing(tmp_path, monkeypatch) -> None:
    """Even with every criterion deferred: "deferred" means no test can check it,
    not "the tests that check it never ran"."""
    _authored(tmp_path)
    suite.lock(tmp_path)
    suite.defer(tmp_path, {
        "AC-1": "no automated check", "AC-2": "no automated check", "AC-3": "no automated check",
    })
    judged = suite._judged(tmp_path, _ran(), False)
    monkeypatch.setattr(suite, "run", lambda root: judged)

    update = delivery.release(_state(tmp_path), CONFIG, None)

    assert update["stage"] == "technical_lead"
    assert update["decisions"][-1]["decision"] == "fix the failing criteria first"
    assert any("zero tests" in str(item) for item in update["revision_comments"])


def test_a_release_with_every_test_collected_still_completes(tmp_path, monkeypatch) -> None:
    _authored(tmp_path)
    suite.lock(tmp_path)
    result = _ran(*(junit.TestResult(name=n) for n in
                    ("[AC-1] adds", "[AC-2] deletes", "[AC-3] persists")))
    judged = suite._judged(tmp_path, result, False)
    monkeypatch.setattr(suite, "run", lambda root: judged)

    update = delivery.release(_state(tmp_path), CONFIG, None)

    assert update["stage"] == "complete"
    assert update["decisions"][-1]["decision"] == "release"
