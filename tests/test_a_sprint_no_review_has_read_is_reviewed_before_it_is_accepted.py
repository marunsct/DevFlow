"""A sprint whose criteria already pass is reviewed first when no review has read its code (measured live).

One run's setup stage wrote the whole product. Sprint 1's criteria then passed,
it was accepted without new work, and no code, milestone or security review
ever read the code. Passing the suite is evidence, not a review: such a sprint
now goes through the reviews with a plan of no work orders.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.graph import delivery, engineering
from app.graph import workflow


def _state(root: Path, **extra: Any) -> dict[str, Any]:
    plan = SimpleNamespace(sprints=[SimpleNamespace(goal="One", criteria=["AC-1"]), SimpleNamespace(goal="Two", criteria=["AC-2"])])
    return {"repository": SimpleNamespace(root_path=str(root)), "sprint_plan": plan,
            "current_sprint_index": 0, "decisions": [], **extra}


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(delivery, "write_evidence", lambda *a, **k: None)
    monkeypatch.setattr(engineering, "accepted_state", lambda root: None)


def _a_product(root: Path) -> None:
    (root / "app" / "src").mkdir(parents=True)
    (root / "app" / "src" / "routes.ts").write_text("export const routes = 1;\n")
    (root / "docs").mkdir()
    (root / "docs" / "technical_specification.md").write_text("# Spec\n")


def test_code_no_review_has_read_goes_to_the_reviews_first(tmp_path):
    _a_product(tmp_path)

    update = workflow._close_a_sprint_with_nothing_to_build(_state(tmp_path), "Every criterion due by sprint 1 already passes")

    assert update["stage"] == "security_review"
    assert update["milestone_plan"].delegated_tasks == []
    assert update["milestone_plan"].selected_sprint_goal == "One"
    (decision,) = update["decisions"]
    assert decision["decision"] == "review it before accepting"


def test_a_sprint_after_a_review_has_run_is_closed_as_before(tmp_path):
    _a_product(tmp_path)

    update = workflow._close_a_sprint_with_nothing_to_build(
        _state(tmp_path, milestone_review=SimpleNamespace(status="accepted")), "x"
    )

    assert update["stage"] == "sprint_advance"


def test_the_review_is_shown_the_whole_product_in_the_first_sprint(tmp_path):
    _a_product(tmp_path)

    files = workflow._the_files_this_milestone_changed(_state(tmp_path), {})

    assert files == ["app/src/routes.ts"]
