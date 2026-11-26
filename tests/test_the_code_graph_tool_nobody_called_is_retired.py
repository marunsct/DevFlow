"""The `code_graph` tool, offered about 3,500 times and called none, is retired with its switch (plan KG.10).

`CODE_GRAPH_TOOL` was recorded on in every run's provenance while the tool it added was never called, and with
`LEAN_TOOL_LISTS` off a builder was still sent its schema on every request. What the graph knows reaches a stage
through the requests the harness writes (the neighbourhood, the slice, the map), not through a tool the model asks.
"""
from __future__ import annotations

import pytest

from app.observability import provenance
from workflow_nodes import tool_names


@pytest.fixture
def every_switch_that_offered_it(monkeypatch):
    for name, value in {"CODE_GRAPH_TOOL": "on", "PREMIUM_PROJECT_INTELLIGENCE": "on", "LEAN_TOOL_LISTS": "off",
                        "SWITCH_OVERRIDES_FROM_SETTINGS": "off"}.items():
        monkeypatch.setenv(name, value)


def test_a_builder_is_not_offered_the_code_graph_tool(every_switch_that_offered_it, tmp_path):
    from app.agents import specialists

    agent = specialists.create_specialist_agent("backend", model="gpt-4o-mini", repo_root=str(tmp_path))

    assert "code_graph" not in tool_names(agent)


def test_no_run_records_the_retired_switch_on(every_switch_that_offered_it):
    assert "CODE_GRAPH_TOOL" not in provenance.switches_on()
