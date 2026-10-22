"""A run's events have a published schema, and the page's type of them is generated (plan UI-S4).

The log route returned a plain dictionary, so the OpenAPI schema said nothing
of an event and the page kept its own hand-written type: an event type added
on the server reached the page as a row it did not know, with nothing to make
the page's build say so.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_log_route_publishes_the_event_and_its_types():
    schema = json.loads((ROOT / "langchain-ui" / "openapi.json").read_text())
    event = schema["components"]["schemas"]["RunEvent"]
    kinds = set(event["properties"]["event_type"]["enum"])
    assert {"stage_change", "agent_message", "tool_call", "tool_result", "review_decision"} <= kinds
    page = schema["paths"]["/api/runs/{run_id}/logs"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert page["$ref"].endswith("/EventPage")


def test_the_page_s_event_type_is_the_generated_one():
    types = (ROOT / "langchain-ui" / "src" / "types" / "index.ts").read_text()
    assert "export interface LogEntry" not in types
    assert "RunEvent as LogEntry" in types
