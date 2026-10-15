"""The reading a specification needs is done before the frontier model writes it.

Measured on one run: 70 minutes of a frontier model on the specification,
most of it 5,000-15,000 tokens of reasoning before each documentation read or
registry lookup.
"""

from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

from app.agents import research_brief
from app.agents.tools_models import TechnologyStack
from app.graph import workflow
from app.tools import docs, package_registry, research

STACK = TechnologyStack(
    language="TypeScript", framework="Hono (on @hono/node-server)", frontend_framework="None",
    database="SQLite via better-sqlite3", testing_framework="node:test + Playwright",
    additional_tools=["TypeScript 5"],
)


def test_the_stack_s_libraries_are_named_once_each():
    assert research_brief.libraries_of(STACK) == [
        "Hono", "@hono/node-server", "SQLite", "better-sqlite3", "node:test", "Playwright", "TypeScript",
    ]


def test_a_stack_of_the_platform_s_own_parts_names_only_its_libraries():
    stack = TechnologyStack(
        language="JavaScript", framework="Vanilla HTML/CSS/JavaScript", frontend_framework="None",
        database="localStorage", testing_framework="Vitest for the logic, Playwright for the page",
    )

    assert research_brief.libraries_of(stack) == ["Vitest", "Playwright"]


def test_the_harness_looks_up_and_reads_and_the_build_model_only_names_the_topics(monkeypatch):
    monkeypatch.setattr(docs, "enabled", lambda: True)
    monkeypatch.setattr(package_registry, "enabled", lambda: True)
    monkeypatch.setattr(package_registry, "look_up", lambda eco, name: {"name": name, "latest": "1.0.0"})
    read = []
    monkeypatch.setattr(docs, "read", lambda name, topic, eco="": read.append((name, topic)) or {"excerpt": f"{name} {topic} text"})

    class _Model:
        def __init__(self):
            self.asked = 0

        def invoke(self, messages):
            self.asked += 1
            return SimpleNamespace(content=json.dumps({"topics": [
                {"library": "hono", "topic": "notFound handler"}, {"library": "Unknown", "topic": "x"},
            ]}))

    model = _Model()
    notes = research_brief.research_notes(STACK, "Notes over HTTP.", model)

    assert model.asked == 1
    assert read == [("Hono", "notFound handler")]
    assert "- better-sqlite3: name: better-sqlite3, latest: 1.0.0" in notes
    assert "### Hono: notFound handler\nHono notFound handler text" in notes


def test_a_stage_whose_reading_was_done_is_offered_no_lookups():
    class _Request(SimpleNamespace):
        def override(self, **changes):
            return _Request(**{**self.__dict__, **changes})

    tools = [SimpleNamespace(name="read_docs"), SimpleNamespace(name="look_up_package"), SimpleNamespace(name="read_file")]
    offered = []
    middleware = research.build_research_share_middleware()
    with research.researched():
        middleware.wrap_model_call(_Request(tools=tools), lambda r: offered.append([t.name for t in r.tools]))

    assert offered == [["read_file"]]


def test_the_architect_is_given_the_reading_and_keeps_it_for_a_retry():
    source = inspect.getsource(workflow)
    node = source[source.index("    def principal_architect_node("):]
    node = node[:node.index("\n    def ", 10)]
    assert node.index("research_notes(") < node.index("with researched(bool(research)):") < node.index('stage_name="principal_architect"')
    assert 'state.get("architect_research")' in node and 'update["architect_research"] = research' in node
