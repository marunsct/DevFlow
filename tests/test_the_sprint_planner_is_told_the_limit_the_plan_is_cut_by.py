"""The sprint planner is told the same sprint limit its plan is cut by.

Per-role audit over 30 runs: the request said "at most 3 or 4 sprints", fast delivery then cut 26 plans to one sprint
after 494k output tokens of planning, and stale "(deferred to Sprint 3)" lines stayed in five plans.
"""
from __future__ import annotations

from app.agents import scrum_master

CRITERIA = " ".join(f"AC-{n}" for n in range(1, 19))


def test_fast_delivery_asks_for_the_one_sprint_it_keeps(monkeypatch):
    monkeypatch.setenv("DELIVERY_MODE", "fast")
    from app import delivery

    assert delivery.fast()
    said = scrum_master._how_many_sprints(CRITERIA)
    assert "Plan at most 1 sprint for these 18 criteria" in said
    assert scrum_master.max_sprints_for_criteria_count(18, fast=True) == 1


def test_thorough_delivery_keeps_its_own_limit(monkeypatch):
    monkeypatch.setenv("DELIVERY_MODE", "thorough")
    assert "Plan at most 4 sprints for these 18 criteria" in scrum_master._how_many_sprints(CRITERIA)
