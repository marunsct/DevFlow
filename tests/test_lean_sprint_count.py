"""Tests for lean sprint count and capping based on criteria count.

Small scopes must not be over-sliced into 3-6 sprints, which burns hours of
redundant enterprise workflow overhead.
"""

from __future__ import annotations

import re
from app.agents.scrum_master import (
    SprintDefinition,
    SprintPlanOutput,
    max_sprints_for_criteria_count,
    with_capped_sprint_count,
    _the_acceptance_criteria,
)


def _sprint(goal: str, criteria: list[str]) -> SprintDefinition:
    return SprintDefinition(
        goal=goal,
        user_value="delivers value",
        in_scope=["feature implementation"],
        criteria=criteria,
    )


def test_max_sprints_scale_with_criteria_count() -> None:
    assert max_sprints_for_criteria_count(3) == 2
    assert max_sprints_for_criteria_count(5) == 2
    assert max_sprints_for_criteria_count(8) == 2
    assert max_sprints_for_criteria_count(10) == 2
    assert max_sprints_for_criteria_count(14) == 3
    assert max_sprints_for_criteria_count(25) == 4


def test_with_capped_sprint_count_folds_excess_sprints() -> None:
    plan = SprintPlanOutput(
        sprints=[
            _sprint("Sprint 1: Core", ["AC-1"]),
            _sprint("Sprint 2: Features", ["AC-2"]),
            _sprint("Sprint 3: Enhancements", ["AC-3"]),
            _sprint("Sprint 4: Polish", ["AC-4"]),
        ],
        success_measure_coverage=["1: Sprint 1", "2: Sprint 2", "3: Sprint 3", "4: Sprint 4"],
    )
    # For 4 criteria, maximum allowed is 2 sprints (<= 10 criteria)
    capped, folded = with_capped_sprint_count(plan, criteria_count=4)
    assert len(capped.sprints) == 2
    assert len(folded) == 2
    assert "AC-1" in capped.sprints[0].criteria
    assert "AC-4" in capped.sprints[1].criteria
    # Check that coverage line for Sprint 4 was remapped to Sprint 2
    assert "4: Sprint 2" in capped.success_measure_coverage


def test_with_capped_sprint_count_preserves_lean_plans() -> None:
    plan = SprintPlanOutput(
        sprints=[
            _sprint("Sprint 1: Core", ["AC-1", "AC-2"]),
            _sprint("Sprint 2: Remaining", ["AC-3", "AC-4", "AC-5", "AC-6", "AC-7", "AC-8"]),
        ]
    )
    # 8 criteria allows 2 sprints; plan already has 2 sprints
    capped, folded = with_capped_sprint_count(plan, criteria_count=8)
    assert len(capped.sprints) == 2
    assert len(folded) == 0


def test_acceptance_criteria_prompt_instruction_contains_no_forbidden_words() -> None:
    prompt = _the_acceptance_criteria("AC-1: Do something")
    forbidden = {"task", "tasks", "to-do", "todo", "button", "click", "checkbox"}
    words = {w.lower() for w in re.findall(r"\b\w+[\w-]*\b", prompt)}
    assert not (words & forbidden), f"Found forbidden words: {words & forbidden}"

