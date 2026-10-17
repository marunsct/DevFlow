"""A completed run that knows what it did not prove says so in every record.

Two runs released at a hidden-test 1/10 read "completed" everywhere: one
after its failing locked tests were reclassified and their criteria deferred,
one whose setup was never proven. The suite was green and the record said
"verified". A release now writes what it knows it did not prove - deferred
criteria, problems the suite was locked with, plan problems noted at
dispatch, an unproven setup, no locked suite at all - into
`completion_gaps`, and the release decision cites them, so no record of the
run can read as a plain success (Initiative J.4/J.5).
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.acceptance import junit, suite
from app.acceptance.criteria import number
from app.graph import delivery

BRIEF = "# Brief\n## Features\n- Add a note\n- Delete a note\n"
CONFIG = {"configurable": {"thread_id": "t"}}


def _state(root: Path, **extra: Any) -> dict[str, Any]:
    (root / ".project-directory").write_text("notes\n")
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "product_intake": SimpleNamespace(product_name="Notes"),
        "sprint_plan": SimpleNamespace(sprints=[SimpleNamespace(goal="Notes", criteria=[])]),
        **extra,
    }


@pytest.fixture(autouse=True)
def _no_cancel(monkeypatch):
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)


def _locked_suite(root: Path) -> None:
    suite.save_criteria(root, number(BRIEF))
    target = root / "notes" / "acceptance" / "notes.spec.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("test('[AC-1] adds', ()=>{});\ntest('[AC-2] deletes', ()=>{});\n")
    suite.lock(root)


def _judged(root: Path, *, ac2: str = "passed") -> suite.AcceptanceResult:
    report = junit.Report(found=True, tests=[
        junit.TestResult(name="[AC-1] adds"),
        junit.TestResult(name="[AC-2] deletes", outcome=ac2, message="no" if ac2 == "failed" else ""),
    ])
    return suite._judged(
        root, suite.AcceptanceResult(ran=True, command="npm run test:acceptance", report=report), False
    )


def _release(tmp_path, monkeypatch, state_extra: dict[str, Any] | None = None) -> dict[str, Any]:
    monkeypatch.setattr(suite, "run", lambda root: _judged(tmp_path))
    return delivery.release(_state(tmp_path, **(state_extra or {})), CONFIG, None)


def test_a_clean_release_records_no_gaps(tmp_path, monkeypatch) -> None:
    _locked_suite(tmp_path)

    update = _release(tmp_path, monkeypatch)

    assert update["stage"] == "complete"
    assert not update.get("completion_gaps")
    assert "gaps" not in update["decisions"][-1]["rationale"]


def test_a_deferred_criterion_is_a_named_gap(tmp_path, monkeypatch) -> None:
    _locked_suite(tmp_path)
    suite.defer(tmp_path, {"AC-2": "no automated check can prove it"})

    update = _release(tmp_path, monkeypatch)

    assert update["stage"] == "complete"
    gaps = update["completion_gaps"]
    assert any(gap.startswith("AC-2 ships deferred") for gap in gaps)
    rationale = update["decisions"][-1]["rationale"]
    assert "Ships with gaps" in rationale and "AC-2" in rationale


def test_problems_the_suite_was_locked_with_are_gaps(tmp_path, monkeypatch) -> None:
    _locked_suite(tmp_path)

    update = _release(
        tmp_path, monkeypatch,
        {"acceptance_open_problems": ["`[AC-1] adds` asserts an order nothing stated"]},
    )

    assert any("locked with this still open" in gap for gap in update["completion_gaps"])


def test_a_plan_dispatched_with_problems_noted_is_a_gap(tmp_path, monkeypatch) -> None:
    _locked_suite(tmp_path)

    update = _release(
        tmp_path, monkeypatch, {"work_order_problems": ["the second sprint names no criterion"]}
    )

    assert any("noted against it" in gap for gap in update["completion_gaps"])


def test_an_unproven_setup_is_a_gap(tmp_path, monkeypatch) -> None:
    _locked_suite(tmp_path)

    update = _release(
        tmp_path, monkeypatch,
        {"scaffold_result": {"ok": False, "pack": None, "problem": "the smoke test did not pass"}},
    )

    assert any("setup was never proven" in gap for gap in update["completion_gaps"])


def test_a_release_without_a_locked_suite_is_a_gap(tmp_path, monkeypatch) -> None:
    (tmp_path / ".project-directory").write_text("notes\n")

    update = _release(tmp_path, monkeypatch)

    assert update["stage"] == "complete"
    assert any("No acceptance suite was locked" in gap for gap in update["completion_gaps"])


def test_the_gap_wording_names_no_product_word(tmp_path, monkeypatch) -> None:
    """The gaps reach the run record, the delivery panel and the decision log."""
    _locked_suite(tmp_path)
    suite.defer(tmp_path, {"AC-2": "no automated check can prove it"})
    banned = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")

    update = _release(
        tmp_path, monkeypatch,
        {
            "acceptance_open_problems": ["an open problem"],
            "work_order_problems": ["a noted problem"],
            "scaffold_result": {"ok": False, "problem": "an unproven setup"},
        },
    )

    for gap in update["completion_gaps"]:
        for word in banned:
            assert not re.search(rf"\b{re.escape(word)}\b", gap, re.IGNORECASE), word

def test_the_release_evidence_page_carries_the_gaps(tmp_path, monkeypatch) -> None:
    _locked_suite(tmp_path)
    suite.defer(tmp_path, {"AC-2": "no automated check can prove it"})

    _release(tmp_path, monkeypatch)

    page = (tmp_path / "docs" / "reviews" / "release-evidence.md").read_text()
    assert "## Completion gaps" in page
    assert "AC-2 ships deferred" in page
