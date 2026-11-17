"""The reading a specification needs is done before the frontier model writes it.

Measured on one run: 70 minutes of a frontier model on the specification,
most of it 5,000-15,000 tokens of reasoning before each documentation read or
registry lookup.
"""

from __future__ import annotations

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
        "Hono", "@hono/node-server", "SQLite", "better-sqlite3", "Playwright",
    ]


def test_words_of_a_sentence_runtimes_files_and_built_ins_are_not_looked_up():
    """One run looked up `already`, `build`, `package.json`, `node:test` and `Node.js` in the registry."""
    stack = TechnologyStack(
        language="TypeScript",
        framework="Hono (v4, npm `hono` 4.13.13) mounted with @hono/node-server (2.1.5) on Node.js (this "
                  "environment runs v24.22.0; the adapter needs >=20 and pairs with hono ^4)",
        frontend_framework="not stated", database="None - a JSON file read and written with node:fs.",
        testing_framework="node:test (Node's built-in runner) for both layers",
        additional_tools=["TypeScript compiler (`tsc`, already on the environment's command list) building src/",
                          "package.json with npm scripts (build + run)", "zod"],
    )
    assert sorted(research_brief.libraries_of(stack)) == ["@hono/node-server", "hono", "tsc", "zod"]


def test_no_documentation_is_read_for_a_name_the_registry_does_not_know(monkeypatch):
    monkeypatch.setattr(docs, "enabled", lambda: True)
    monkeypatch.setattr(package_registry, "enabled", lambda: True)
    monkeypatch.setattr(package_registry, "look_up", lambda eco, name: {"error": "404"} if name == "SQLite" else {"latest": "1"})
    read = []
    monkeypatch.setattr(docs, "read", lambda name, topic, eco="": read.append(name) or {"excerpt": "text"})

    research_brief.research_notes(STACK, "Notes.", None)

    assert "SQLite" not in read and "Hono" in read


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


def test_a_stage_whose_reading_was_done_is_offered_no_lookups(monkeypatch):
    # STABLE_TOOLS off: this checks the bound tool list, which that fix keeps whole (it refuses a withheld call).
    monkeypatch.setenv("STABLE_TOOLS", "off")
    class _Request(SimpleNamespace):
        def override(self, **changes):
            return _Request(**{**self.__dict__, **changes})

    tools = [SimpleNamespace(name="read_docs"), SimpleNamespace(name="look_up_package"), SimpleNamespace(name="read_file")]
    offered = []
    middleware = research.build_research_share_middleware()
    with research.researched():
        middleware.wrap_model_call(_Request(tools=tools), lambda r: offered.append([t.name for t in r.tools]))

    assert offered == [["read_file"]]


NOTES = "### Hono: notFound handler\nHono notFound handler text"


def _the_architect_runs(tmp_path, **state):
    """The architect's node with the reading stood in: what it was asked, whether its reading was done, how often the
    reading ran, and its update."""
    from unittest.mock import MagicMock, patch

    from langgraph.checkpoint.memory import MemorySaver

    from app.agents.stack_selector import StackSelectorOutput
    from app.state import RepositoryContext

    read, asked = [], []

    def gated(_state, _config, *, initial_request, output_key, **_kwargs):
        asked.append((initial_request["messages"][-1]["content"], research.spent("documentation")))
        return {output_key: SimpleNamespace(), "stage": "architecture_review"}

    full = {
        "stack_selection": StackSelectorOutput(technology_stack=STACK, rationale="As the brief asks."),
        "document": SimpleNamespace(text="Notes over HTTP."),
        "repository": RepositoryContext(root_path=str(tmp_path), branch="main", commit="abc", status="clean"),
        "product_intake": {"product_name": "Notes"},
        "tools_models": {"plan": "local"},
        **state,
    }
    with patch("app.graph.workflow.create_principal_architect_agent", return_value=MagicMock()), \
         patch("app.agents.research_brief.research_notes", side_effect=lambda *a, **k: read.append(a) or NOTES), \
         patch("app.graph.workflow._fast_delivery", return_value=False), \
         patch("app.graph.workflow._run_gated_agent", side_effect=gated):
        graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(tmp_path))
        update = graph.nodes["principal_architect"].bound.invoke(full, {"configurable": {"thread_id": "t"}})
    return asked, len(read), update


def test_the_architect_is_given_the_reading_and_keeps_it_for_a_retry(tmp_path):
    """The reading is done before the architect writes, handed to it with no lookups offered, and kept for a retry
    so it is not done again (once checked on the node's source)."""
    asked, reads, update = _the_architect_runs(tmp_path)

    assert reads == 1
    ((request, lookups_withheld),) = asked
    assert NOTES in request and lookups_withheld
    assert update["architect_research"] == NOTES

    asked, reads, _ = _the_architect_runs(tmp_path, architect_research=NOTES)

    assert reads == 0, "the retry is given the reading kept, not a second one"
    assert NOTES in asked[0][0] and asked[0][1]
