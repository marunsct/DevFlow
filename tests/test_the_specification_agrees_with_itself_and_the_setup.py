"""The specification gives every library call as documented, agrees with itself, and the setup follows it.

Read against one run's specification, built for a faster local model to work
from:
- its files imported each other with file extensions its own compiler
  configuration did not allow, so a build copied word for word would fail its
  type check;
- the setup stage, run after the specification was approved, was never shown
  it, and created two test runner configuration files under names of its own
  where the specification planned one;
- library calls were scattered through function contracts, where a builder
  looking for the exact import of one framework call had to find it.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from app.agents import principal_architect
from app.agents.principal_architect import TechnicalSpecificationOutput
from app.agents.specialists import specification_for_the_work_order
from app.stacks import custom_setup

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

SPEC = TechnicalSpecificationOutput(
    product_scope="Notes.",
    file_plan=["notes/src/app.ts - builds the service; exports buildApp(store): App", "notes/runner.config.ts - the one test runner configuration"],
    testing=["One runner for unit and acceptance tests, configured in notes/runner.config.ts"],
    configuration=["npm scripts: test runs the runner once"],
    library_usage=["web framework 4: import { App } from 'framework'; new App().get(path, handler) -> App"],
)


def test_the_specification_has_a_section_of_library_calls():
    from app.agents.specification_document import _SECTIONS
    from app.agents.technical_lead import _CONTRACT_SECTIONS

    field = TechnicalSpecificationOutput.model_fields["library_usage"]
    assert "import statement" in field.description and "`read_docs`" in field.description
    assert "library_usage" in dict(_SECTIONS) and "library_usage" in dict(_CONTRACT_SECTIONS)
    assert not BANNED.search(field.description)


def test_the_architect_is_asked_for_documented_calls_and_a_configuration_that_allows_the_files():
    prompt = principal_architect._SYSTEM_PROMPT
    calls = prompt[prompt.index("- Give every call into a library"):prompt.index("- Make the configuration allow")]
    start = prompt.index("- Make the configuration allow")
    agree = prompt[start:prompt.index("\n\n", start)]

    assert "`read_docs`" in calls and "word for word" in calls
    assert "import paths (with or without file extensions)" in agree
    assert "configuration files" in agree and "agree everywhere" in agree
    assert "`library_usage`" in prompt
    assert not BANNED.search(calls + agree)


def test_every_work_order_is_handed_the_library_calls():
    order = SimpleNamespace(files=["notes/src/app.ts"], interfaces=["buildApp(store): App"])

    detail = specification_for_the_work_order(SPEC, order)

    assert "import { App } from 'framework'" in detail
    assert "Library calls, as their documentation gives them:" in detail


def test_the_setup_stage_is_shown_what_the_specification_decided():
    request = custom_setup.build_setup_request(
        "notes", SimpleNamespace(language="TypeScript", framework="framework"), "http_api", specification=SPEC,
    )["messages"][0]["content"]

    assert "What the specification already decided" in request
    assert "notes/runner.config.ts - the one test runner configuration" in request
    assert "One runner for unit and acceptance tests" in request
    assert "import { App } from 'framework'" in request
    lead = request[request.index("--- What the specification already decided"):request.index("Files:")]
    assert not BANNED.search(lead)


def test_without_a_specification_the_setup_request_is_as_it_was():
    request = custom_setup.build_setup_request("notes", SimpleNamespace(language="Go"), "cli")["messages"][0]["content"]

    assert "What the specification already decided" not in request


def test_the_scaffold_hands_the_setup_stage_the_specification(monkeypatch, tmp_path):
    from app.graph import acceptance_nodes, workflow

    seen = {}
    monkeypatch.setattr("app.tools.repository.pinned_project_directory", lambda root: "notes")
    monkeypatch.setattr("app.agents.specialists.create_specialist_agent", lambda *a, **k: object())
    monkeypatch.setattr(workflow, "_stop_if_cancelled", lambda run_id: None)

    def run_gated(state, config, *, stage_name, agent, initial_request, output_key, next_stage):
        seen["request"] = initial_request["messages"][0]["content"]
        return {"stage": "awaiting_approval:" + stage_name}

    monkeypatch.setattr(workflow, "_run_gated_agent", run_gated)
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "stack_selection": SimpleNamespace(technology_stack=SimpleNamespace(
            language="TypeScript", framework="framework", frontend_framework="", testing_framework="", product_kind="http_api",
        )),
        "product_intake": SimpleNamespace(product_name="notes"),
        "document": SimpleNamespace(text="A notes service."),
        "stack_pack": None,
        "technical_specification": SPEC,
    }
    ctx = acceptance_nodes.Context(model=None, judgement_model=None, checkpointer=None, repo_root=str(tmp_path))

    acceptance_nodes.scaffold(state, {"configurable": {"thread_id": "t"}}, ctx)

    assert "notes/runner.config.ts" in seen["request"]
