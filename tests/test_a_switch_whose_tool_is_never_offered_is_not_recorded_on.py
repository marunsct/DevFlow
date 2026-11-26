"""A switch whose only effect is a tool no stage is offered is recorded off, not on (deep review of silent mechanisms).

`ASK_SPECIFICATION` and `CODE_GRAPH_TOOL` were recorded on in 29 of 29 runs while `LEAN_TOOL_LISTS`, also on, left
their tools out of every stage: offered in none of 9,567 requests. Every KPI row and every comparison by the switches
on counted them as active. (`CODE_GRAPH_TOOL` and its tool were removed since, KG.10.)
"""
from __future__ import annotations

import pytest

from app.observability import provenance

SWITCH = "ASK_SPECIFICATION"


@pytest.fixture
def both_on(monkeypatch):
    monkeypatch.setenv(SWITCH, "on")
    monkeypatch.setenv("WEB_TOOLS_OFFERED", "off")


def test_with_lean_tool_lists_on_it_is_not_recorded_on(both_on, monkeypatch):
    monkeypatch.setenv("LEAN_TOOL_LISTS", "on")

    assert SWITCH not in provenance.switches_on()


def test_with_lean_tool_lists_off_it_is_recorded_on(both_on, monkeypatch):
    monkeypatch.setenv("LEAN_TOOL_LISTS", "off")

    assert SWITCH in provenance.switches_on()


def test_the_web_pair_kept_by_the_run_s_lookups_choice_is_not_left_out(monkeypatch):
    from app.agents import stage_tools

    monkeypatch.setenv("LEAN_TOOL_LISTS", "on")
    monkeypatch.setattr("app.tools.web_search.offered", lambda: True)

    assert not stage_tools.leaves_out("search_the_web")
    assert stage_tools.leaves_out("ask_specification")
    assert not stage_tools.leaves_out("use_runtime"), "kept for the setup of a stack no pack covers"
