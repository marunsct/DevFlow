"""A locked test is not reclassified on the QA lead's word alone.

Seven of thirty-three audited runs were falsely accepted, and reclassify-to-
ship was how the worst of them traveled: failing locked tests judged "cannot
pass", the suite reopened, the criterion deferred, the record green. The
dispute stage already runs on the judgement model; this adds the two other
legs (Initiative J.2). Each disputed test is re-measured first - its own file,
run alone against the delivered surface in the project's own runner, no model
in the loop - and a test that passes alone failed its suite run for order or
shared state and stays locked. And a run may reclassify at most two locked
tests through its disputes, a tenth of a bigger suite; past the cap tests
stay as they are, and a release names every reclassification in its gaps.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.acceptance import junit, suite
from app.acceptance.criteria import number
from app.graph import acceptance_nodes, delivery

BRIEF = "# Brief\n## Features\n- Add a note\n- Delete a note\n"
CONFIG = {"configurable": {"thread_id": "t"}}
FLOW = "acceptance/flow.spec.js"


def _state(root: Path, **extra: Any) -> dict[str, Any]:
    return {"repository": SimpleNamespace(root_path=str(root)), "decisions": [], **extra}


@pytest.fixture
def _a_small_suite(monkeypatch):
    monkeypatch.setattr(
        acceptance_nodes.suite, "declared_tests",
        lambda root: [(FLOW, "[AC-1] adds a record"), (FLOW, "[AC-4] deletes a record")],
    )


def _runs(monkeypatch, *outcomes: tuple[str, str]) -> None:
    monkeypatch.setattr("app.stacks.contract.read", lambda root: {})
    monkeypatch.setattr("app.stacks.scaffold.sandbox_runner", lambda root: (lambda *a, **k: {}))
    monkeypatch.setattr(
        "app.acceptance.per_file.each_file",
        lambda root, record, run, *, naming=None: [
            {"file": name, "outcome": outcome} for name, outcome in outcomes
        ],
    )


def test_a_disputed_test_whose_file_passes_alone_stays_locked(tmp_path, monkeypatch, _a_small_suite) -> None:
    _runs(monkeypatch, (FLOW, "finished"))

    still, alone = acceptance_nodes.tests_that_fail_alone(
        tmp_path, ["flow.spec.js › [AC-4] deletes a record"]
    )

    assert still == [] and alone == ["flow.spec.js › [AC-4] deletes a record"]


def test_a_disputed_test_that_fails_alone_goes_on_to_the_reopen(tmp_path, monkeypatch, _a_small_suite) -> None:
    _runs(monkeypatch, (FLOW, "failed"))

    still, alone = acceptance_nodes.tests_that_fail_alone(tmp_path, ["[AC-4] deletes a record"])

    assert still == ["[AC-4] deletes a record"] and alone == []


def test_only_the_files_holding_a_disputed_test_are_run_again(tmp_path, monkeypatch, _a_small_suite) -> None:
    """A service suite runs each file with its own server; the dispute needs only the files of the tests it names."""
    asked = []
    monkeypatch.setattr("app.stacks.contract.read", lambda root: {})
    monkeypatch.setattr("app.stacks.scaffold.sandbox_runner", lambda root: (lambda *a, **k: {}))

    def each_file(root, record, run, *, naming=None):
        asked.append(naming)
        return [{"file": FLOW, "outcome": "failed"}]

    monkeypatch.setattr("app.acceptance.per_file.each_file", each_file)

    acceptance_nodes.tests_that_fail_alone(tmp_path, ["[AC-4] deletes a record"])

    assert asked == [{"AC-4"}]


def test_a_test_that_cannot_be_re_measured_is_left_on_the_list(tmp_path, monkeypatch, _a_small_suite) -> None:
    """No runner, no record, no file: unknown is not passed, and the dispute
    keeps the test it named."""
    _runs(monkeypatch)

    still, alone = acceptance_nodes.tests_that_fail_alone(tmp_path, ["[AC-4] deletes a record"])

    assert still == ["[AC-4] deletes a record"] and alone == []


def test_the_cap_is_two_or_a_tenth_of_a_bigger_suite(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        acceptance_nodes.suite, "declared_tests",
        lambda root: [(FLOW, f"[AC-{i}] holds")] * 10,
    )
    assert acceptance_nodes.most_reclassifications(tmp_path) == 2

    monkeypatch.setattr(
        acceptance_nodes.suite, "declared_tests",
        lambda root: [(FLOW, f"[AC-{i}] holds") for i in range(50)],
    )
    assert acceptance_nodes.most_reclassifications(tmp_path) == 5


def test_room_shrinks_as_tests_are_reclassified(tmp_path, monkeypatch, _a_small_suite) -> None:
    assert acceptance_nodes.reclassification_room(_state(tmp_path)) == 2
    assert acceptance_nodes.reclassification_room(
        _state(tmp_path, suite_reclassified_tests=["[AC-4] deletes a record"])
    ) == 1
    assert acceptance_nodes.reclassification_room(
        _state(tmp_path, suite_reclassified_tests=["a", "b"])
    ) == 0


def test_names_past_the_cap_are_refused(tmp_path, monkeypatch, _a_small_suite) -> None:
    state = _state(tmp_path, suite_reclassified_tests=["a"])

    allowed, refused = acceptance_nodes.within_the_cap(state, ["x", "y", "z"])

    assert allowed == ["x"] and refused == ["y", "z"]


def test_a_reopen_for_a_dispute_records_what_it_reclassified(tmp_path) -> None:
    reopened = acceptance_nodes.reopen_the_suite_for(
        _state(tmp_path), ["`[AC-5] filters` cannot pass"], reclassifying=True,
    )

    assert reopened is not None
    assert reopened["suite_reclassified_tests"] == ["[AC-5] filters"]
    # A repair the harness's own checks sent for is no reclassification.
    harness = acceptance_nodes.reopen_the_suite_for(_state(tmp_path), ["`X` broke itself"])
    assert harness is not None and "suite_reclassified_tests" not in harness


def test_the_tracker_rides_the_graph_state() -> None:
    from app.graph import workflow

    assert "suite_reclassified_tests" in workflow.WorkflowGraphState.__annotations__


def test_the_dispute_node_uses_both_legs() -> None:
    from app.graph import workflow

    source = inspect.getsource(workflow)

    assert "tests_that_fail_alone" in source
    assert "within_the_cap" in source
    assert "reclassifying=True" in source


# --- the release gap: a run that reclassified says so ----------------------


def _release_state(root: Path, **extra: Any) -> dict[str, Any]:
    (root / ".project-directory").write_text("notes\n")
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "product_intake": SimpleNamespace(product_name="Notes"),
        "sprint_plan": SimpleNamespace(sprints=[SimpleNamespace(goal="Notes", criteria=[])]),
        **extra,
    }


def _locked_suite(root: Path) -> None:
    suite.save_criteria(root, number(BRIEF))
    target = root / "notes" / "acceptance" / "notes.spec.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("test('[AC-1] adds', ()=>{});\ntest('[AC-2] deletes', ()=>{});\n")
    suite.lock(root)


def _judged(root: Path) -> suite.AcceptanceResult:
    report = junit.Report(found=True, tests=[
        junit.TestResult(name="[AC-1] adds"),
        junit.TestResult(name="[AC-2] deletes"),
    ])
    return suite._judged(
        root, suite.AcceptanceResult(ran=True, command="npm run test:acceptance", report=report), False
    )


@pytest.fixture(autouse=True)
def _no_cancel(monkeypatch):
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)


def test_a_run_that_reclassified_names_them_in_its_gaps(tmp_path, monkeypatch) -> None:
    _locked_suite(tmp_path)
    monkeypatch.setattr(suite, "run", lambda root: _judged(tmp_path))

    update = delivery.release(
        _release_state(tmp_path, suite_reclassified_tests=["notes.spec.js › [AC-2] deletes"]),
        CONFIG, None,
    )

    gaps = update.get("completion_gaps") or []
    assert any("reclassified" in gap and "[AC-2] deletes" in gap for gap in gaps)


def test_a_run_that_reclassified_nothing_records_no_such_gap(tmp_path, monkeypatch) -> None:
    _locked_suite(tmp_path)
    monkeypatch.setattr(suite, "run", lambda root: _judged(tmp_path))

    update = delivery.release(_release_state(tmp_path), CONFIG, None)

    assert not any("reclassified" in gap for gap in update.get("completion_gaps") or [])


def test_the_reclassification_gap_names_no_product_word(tmp_path, monkeypatch) -> None:
    _locked_suite(tmp_path)
    monkeypatch.setattr(suite, "run", lambda root: _judged(tmp_path))
    banned = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")

    update = delivery.release(
        _release_state(tmp_path, suite_reclassified_tests=["notes.spec.js › [AC-2] deletes"]),
        CONFIG, None,
    )

    for gap in update.get("completion_gaps") or []:
        for word in banned:
            assert not re.search(rf"\b{re.escape(word)}\b", gap, re.IGNORECASE), word
