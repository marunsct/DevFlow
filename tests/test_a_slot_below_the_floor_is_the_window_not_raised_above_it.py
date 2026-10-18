"""A server slot smaller than the floor is the window; the harness does not budget past it (plan item AO.2).

The window was clamped up to a 32,000-token floor even when the server said
each request gets less, so the budget promised room the server then refused
("Context size has been exceeded"). The smaller truth stands, with a warning
once; and a server that reports nothing is noted once, not silently trusted.
"""
from __future__ import annotations

import logging

import pytest

from app.agents import context_budget
from app.agents.context_budget import MIN_VIABLE_WINDOW, ContextBudget, context_window
from app.models import server_profile
from app.models.server_profile import ServerProfile


@pytest.fixture(autouse=True)
def _clean():
    server_profile.forget()
    context_budget._SAID.clear()
    yield
    server_profile.forget()
    context_budget._SAID.clear()


ENV = {"MODEL_CONTEXT_WINDOW": "100000"}


def test_a_slot_below_the_floor_is_the_window(caplog):
    server_profile._RECORDED = ServerProfile(slots=1, slot_context=16_000)

    with caplog.at_level(logging.WARNING):
        window = context_window(ENV)
        context_window(ENV)  # a second time: said once

    assert window == 16_000
    assert sum("below the" in r.message for r in caplog.records) == 1


def test_the_budget_built_from_it_fits_the_slot():
    server_profile._RECORDED = ServerProfile(slots=1, slot_context=16_000)

    budget = ContextBudget.resolve(ENV)

    assert budget.window_tokens == 16_000
    assert budget.max_output_tokens + budget.input_ceiling_tokens < 16_000
    assert budget.input_ceiling_tokens >= 1_024


def test_a_slot_above_the_floor_still_bounds_the_setting():
    server_profile._RECORDED = ServerProfile(slots=1, slot_context=64_000)

    assert context_window(ENV) == 64_000


def test_a_server_that_reports_nothing_is_noted_once_and_the_setting_stands(caplog):
    with caplog.at_level(logging.WARNING):
        assert context_window(ENV) == 100_000
        context_window(ENV)

    assert sum("reports no slot or context facts" in r.message for r in caplog.records) == 1


def test_a_configured_window_below_the_floor_is_still_raised_without_a_server_fact():
    assert context_window({"MODEL_CONTEXT_WINDOW": "8000"}) == MIN_VIABLE_WINDOW
