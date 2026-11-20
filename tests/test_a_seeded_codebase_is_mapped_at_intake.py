"""A seeded codebase is mapped from its files for the stages that plan its change (plan WS.7).

A run seeded with an existing product began its intake with the brief and a branch name: nothing told the intake or
the planning stages what the codebase held, so they planned blind or spent their first calls listing folders. The map
is built with no model call, and it costs no more context for a large codebase than for a small one.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.acceptance.regression_contract import mark_seeded
from app.agents import code_map

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _write(root: Path, files: dict[str, str]) -> Path:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _a_small_seeded_codebase(root: Path) -> Path:
    _write(root, {
        "pyproject.toml": "[project]\nname = 'shop'\n",
        "shop/app.py": "from shop.cart import Cart\n\n\ndef main():\n    return Cart()\n",
        "shop/cart.py": "class Cart:\n    pass\n\n\ndef _rounded(x):\n    return x\n\n\ndef total(cart):\n    return 0\n",
        "shop/tests/test_cart.py": "from shop.cart import total\n\n\ndef test_total():\n    assert total(None) == 0\n",
        "web/package.json": "{}\n",
        "web/src/main.js": "export function mountCatalogue() {}\n",
        "web/node_modules/left-pad/index.js": "export function leftPad() {}\n",
        "engine/Cargo.toml": "[package]\nname = 'engine'\n",
        "engine/target/debug/build.rs": "fn generated_by_cargo() {}\n",
    })
    mark_seeded(root, {"type": "git"})
    return root


def test_a_small_codebase_is_mapped_module_by_module(tmp_path):
    text = code_map.for_a_seeded_run(_a_small_seeded_codebase(tmp_path))

    assert "python 3 files" in text and "javascript 1 file " in text
    assert "pyproject.toml" in text and "web/package.json" in text
    assert "shop/app.py" in text.split("Entry points")[1].splitlines()[0]
    assert "shop/tests/ (1 file)" in text
    assert "- shop/cart.py (10 lines): Cart, total" in text
    assert "_rounded" not in text
    assert "node_modules" not in text and "leftPad" not in text
    assert "target/" not in text and "generated_by_cargo" not in text


def test_a_large_codebase_is_summarised_by_directory_within_the_cap(tmp_path):
    files = {f"service{d:03d}/module{m}.py": f"def handler_{d}_{m}():\n    return {m}\n\n\nclass Model{d}x{m}:\n    pass\n"
             for d in range(120) for m in range(9)}
    files.update({f"service{d:03d}/helpers.py": "def shared():\n    return 1\n" for d in range(120)})
    files.update({f"service{d:03d}/module0.py": f"from service{d:03d}.helpers import shared\n\n\ndef handler():\n    return shared()\n"
                  for d in range(120)})
    _write(tmp_path, files)
    mark_seeded(tmp_path, {"type": "archive"})

    text = code_map.for_a_seeded_run(tmp_path)

    assert len(text) <= 6_000
    assert "1,200 source files" in text
    assert "Directories, by size" in text and "Modules, with the public names" not in text
    assert "- service000/ 10 files, python: helpers.py (shared)" in text
    assert "the map stops at 6,000 characters" in text


def test_a_run_that_was_not_seeded_gets_no_map(tmp_path):
    _write(tmp_path, {"app.py": "def main():\n    pass\n"})

    assert code_map.for_a_seeded_run(tmp_path) == ""


def test_the_map_s_own_words_hold_no_product_word(tmp_path):
    text = code_map.for_a_seeded_run(_a_small_seeded_codebase(tmp_path))

    assert text and not BANNED.findall(text)


def _a_planning_state(root: Path) -> dict:
    from types import SimpleNamespace

    from app.agents.principal_architect import TechnicalSpecificationOutput
    from app.agents.scrum_master import SprintDefinition, SprintPlanOutput
    from app.agents.stack_selector import StackSelectorOutput, TechnologyStack
    from app.state import RepositoryContext

    stack = TechnologyStack(language="Python", framework="none", frontend_framework="", database="none",
                            testing_framework="pytest", product_kind="library", additional_tools=[])
    sprint = SprintDefinition(goal="Gift wrap", user_value="v", in_scope=["wrap"], out_of_scope=[],
                              acceptance_criteria=["works"], dependencies=[])
    return {
        "document": SimpleNamespace(text="Add gift wrap to the shop.", source_type="markdown", truncated=False),
        "repository": RepositoryContext(root_path=str(root), branch="main", commit="abc", status="clean"),
        "product_intake": {"product_name": "Shop"},
        "tools_models": {"plan": "local"},
        "stack_selection": StackSelectorOutput(technology_stack=stack, rationale="As the code is written."),
        "technical_specification": TechnicalSpecificationOutput(product_scope="Shop."),
        "sprint_plan": SprintPlanOutput(sprints=[sprint], success_measure_coverage=[]),
        "current_sprint_index": 0,
    }


def _the_request_a_stage_sends(node: str, root: Path) -> str:
    """The first request the stage's agent is given, with the agent itself cut off (the model is the edge)."""
    from unittest.mock import MagicMock, patch

    from langgraph.checkpoint.memory import MemorySaver

    from app.graph import workflow

    sent: list[dict] = []

    def gated(state, config, **kwargs):
        sent.append(kwargs["initial_request"])
        return {"stage": node, "structured_retries": {node: 1}, "pending_inner_thread_id": None}

    creators = [name for name in dir(workflow) if name.startswith("create_") and name.endswith("_agent")]
    with patch.multiple(workflow, **{name: MagicMock() for name in creators}), \
         patch("app.agents.research_brief.research_notes", return_value=""), \
         patch("app.graph.acceptance_nodes.sprint_already_done", return_value=""), \
         patch("app.graph.workflow._fast_delivery", return_value=False), \
         patch("app.graph.workflow._run_gated_agent", side_effect=gated):
        graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(root))
        graph.nodes[node].bound.invoke(_a_planning_state(root), {"configurable": {"thread_id": "t", "run_id": "r"}})
    assert len(sent) == 1
    return str(sent[0]["messages"][-1]["content"])


@pytest.mark.parametrize("node", ["product_manager", "stack_selector", "principal_architect", "technical_lead"])
def test_the_intake_and_planning_stages_are_given_the_map_of_a_seeded_codebase(node, tmp_path):
    request = _the_request_a_stage_sends(node, _a_small_seeded_codebase(tmp_path))

    assert code_map.HEADING in request and "- shop/cart.py (10 lines): Cart, total" in request


def test_an_unseeded_run_s_intake_is_given_no_map(tmp_path):
    _write(tmp_path, {"app.py": "def main():\n    pass\n"})

    assert code_map.HEADING not in _the_request_a_stage_sends("product_manager", tmp_path)
