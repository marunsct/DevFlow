"""Whoever writes or judges the specification is told what the chosen setup has already decided.

Measured on several runs: the review ended on blocking findings about the harness's own files after six revisions each -
a kept start file given signal handlers, a file plan naming a unit runner the setup does not run, a tool added to run
the language. The setup's facts reached the architect's first request and the review, and not the three calls that
write the sections naming those things, nor any revision; and nobody was told the runner, the start or the entry's shape.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver

from app.agents.architecture_reviewer import (
    ArchitectureReviewFinding,
    ArchitectureReviewOutput,
    build_architecture_review_request,
)
from app.agents.principal_architect import TechnicalSpecificationOutput
from app.agents.shared_facts import the_facts_section
from app.agents.stack_selector import StackSelectorOutput, TechnologyStack
from app.graph import workflow
from app.state import RepositoryContext
from app.stacks.packs import ALL_PACKS

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _stack(**fields) -> StackSelectorOutput:
    base = dict(language="TypeScript", framework="Hono", frontend_framework="", database="SQLite",
                testing_framework="node:test, Playwright", product_kind="http_api", additional_tools=[])
    return StackSelectorOutput(technology_stack=TechnologyStack(**{**base, **fields}), rationale="As the brief asks.")


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("HONO_NATIVE_TEST_RUNNER", "on")
    (tmp_path / ".project-directory").write_text("notes-api\n")
    (tmp_path / "notes-api").mkdir()
    return {
        "stack_selection": _stack(),
        "document": SimpleNamespace(text="Notes over HTTP."),
        "repository": RepositoryContext(root_path=str(tmp_path), branch="main", commit="abc", status="clean"),
        "product_intake": {"product_name": "Notes"},
        "tools_models": {"plan": "local"},
    }


def _what_the_setup_decides(told: str) -> None:
    assert "node:test for unit tests" in told and "Playwright" in told, "the runners"
    assert "`npm test`" in told and "`npm run test:acceptance`" in told, "the commands"
    assert "no other runner" in told, "nothing else is chosen"
    assert "`notes-api/src/app.ts`" in told and "`createApp`" in told, "the entry"
    assert "no arguments" in told, "how the entry is called"
    assert "no step, signature or behaviour inside" in told, "what the specification leaves alone"
    assert "exec node src/main.ts" in told, "the start"
    assert "no other way" in told, "the start is the only one"


def test_the_architect_is_told_the_runner_the_start_and_the_entry(state):
    told = workflow._the_scaffold_s_layout(state)
    _what_the_setup_decides(told)
    assert not BANNED.search(told)


def test_the_review_is_told_the_same(state):
    told = workflow._the_setup_for_the_review(state)
    _what_the_setup_decides(told)
    assert not BANNED.search(told)


def test_the_review_does_not_reopen_what_the_setup_decides():
    """Measured: told a file was kept, the review asked which side owned it, and offered to make it the product's."""
    text = build_architecture_review_request("spec", "/", "", environment="- Kept: `main`.")["messages"][0]["content"]
    rule = text.split("--- Technical specification")[0]
    assert "the setup decides" in rule and "minor" in rule and "never a choice between" in rule
    assert not BANNED.search(rule)


@pytest.mark.parametrize("pack", ALL_PACKS, ids=lambda pack: pack.name)
def test_every_pack_says_it_from_its_own_data(pack, tmp_path, monkeypatch):
    """No stack's words in the harness: each pack's line is its own, with its own runner and nothing of another's."""
    from app.agents.shared_facts import layout_facts

    with patch("app.stacks.choose_pack", return_value=pack):
        (tmp_path / ".project-directory").write_text("demo\n")
        told = workflow._the_setup_for_the_review({
            "stack_selection": _stack(), "document": SimpleNamespace(text=""),
            "repository": SimpleNamespace(root_path=str(tmp_path)),
        })
    assert pack.stack["testing_framework"] in told
    assert "{{" not in told
    assert ("`createApp`" in told) == ("createApp" in str(dict(pack.required_exports)))
    assert len(told) - len("\n".join(layout_facts(pack, "demo", "demo"))) < 1_000


def test_the_builders_requests_do_not_grow(state, monkeypatch):
    """These are for the stages writing the design: a builder has the pack's guide already."""
    from app.stacks import contract

    monkeypatch.setenv("SHARED_FACTS", "on")
    root = state["repository"].root_path
    with patch.object(contract, "read", return_value={"pack": "node-hono-native-api", "project": "notes-api"}):
        section = the_facts_section(root, built=False)
    assert "Kept by the harness" in section and "no other runner" not in section


class _Writer(BaseChatModel):
    """The deployment's own model, as a run with no judgement model named has: answers any section it is asked for."""

    asked: list = []

    @property
    def _llm_type(self) -> str:
        return "stand-in"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        text = str(messages[-1].content)
        self.asked.append(text)
        if '{"sections"' in text:
            answer = {"sections": ["testing"]}
        else:
            names = re.search(r"Its keys are exactly: ([^.]+)\.", text).group(1).split(", ")
            answer = {name: ["written"] for name in names}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=json.dumps(answer)))])


CORE = TechnicalSpecificationOutput(
    product_scope="Notes.", component_boundaries=["c"], api_and_event_contracts=["a"], file_plan=["notes-api/src/app.ts: routes"],
    data_flows=[], decisions=[],
)


def _the_stage_runs(state, *, fast: bool):
    """The architect's node as a run reaches it, with no judgement model named. What each model and agent was asked."""
    writer = _Writer()
    writer.asked = []
    agent_requests: list[str] = []

    def gated(_state, _config, *, initial_request, output_key, **_kwargs):
        agent_requests.append(initial_request["messages"][-1]["content"])
        return {output_key: CORE, "stage": "architecture_review"}

    with patch("app.models.build_default_chat_model", return_value=writer), \
         patch("app.graph.workflow.create_principal_architect_agent", return_value=MagicMock()), \
         patch("app.agents.research_brief.research_notes", return_value=""), \
         patch("app.graph.workflow._fast_delivery", return_value=fast), \
         patch("app.graph.workflow._run_gated_agent", side_effect=gated):
        graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=state["repository"].root_path)
        graph.nodes["principal_architect"].bound.invoke(state, {"configurable": {"thread_id": "t", "run_id": "r"}})
    return writer.asked, agent_requests


def _sent_back(state) -> dict:
    review = ArchitectureReviewOutput(status="changes_required", findings=[ArchitectureReviewFinding(
        severity="major", description="The testing section is thin.", evidence="testing", required_remediation="More.")])
    return {**state, "technical_specification": CORE, "architecture_review": review,
            "architecture_revision_count": 1, "architecture_review_applied": 0}


def test_the_calls_that_write_the_sections_are_told_it(state):
    """The file plan's core is the architect's; the testing, configuration and deployment sections are these calls'."""
    asked, _ = _the_stage_runs(state, fast=True)
    parts = [text for text in asked if text.startswith("These are sections")]
    assert len(parts) == 3
    for part in parts:
        assert "Kept by the harness" in part
        _what_the_setup_decides(part)


def test_a_revision_made_in_place_is_told_it(state):
    asked, _ = _the_stage_runs(_sent_back(state), fast=True)
    rewrites = [text for text in asked if "--- The sections to rewrite" in text]
    assert rewrites, "the revision ran in place"
    for rewrite in rewrites:
        assert "Kept by the harness" in rewrite
        _what_the_setup_decides(rewrite)


def test_a_revision_by_the_architect_itself_is_told_it(state):
    _, requests = _the_stage_runs(_sent_back(state), fast=False)
    assert len(requests) == 1
    assert "Kept by the harness" in requests[0]
    _what_the_setup_decides(requests[0])


def test_the_module_system_the_setup_s_manifest_declares_is_named():
    """Measured on one run: the first design review blocked a specification for not saying how Node loads ES modules,
    while the setup's own `package.json` already declared `"type": "module"`."""
    from app.agents.shared_facts import what_the_setup_decides
    from app.stacks import pack_named

    lines = what_the_setup_decides(pack_named("browser-javascript"), "todo", None)
    said = next(line for line in lines if "package.json" in line and "module" in line)
    assert '"type": "module"' in said and "ES modules" in said
    assert not [line for line in what_the_setup_decides(pack_named("python-http-api"), "notes", "notes")
                if '"type"' in line]
