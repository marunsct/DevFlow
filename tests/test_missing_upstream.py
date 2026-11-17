"""A stage that answers in prose must not kill the run downstream.

An agent that writes its answer into the conversation instead of returning it
through the response schema leaves its artifact out of state. Every later stage
that read the key directly died with a bare `KeyError` raised from inside
LangGraph, naming neither the stage that failed nor anything to do about it -
observed as `KeyError: 'product_intake'` on one run.

The rate makes this a design constraint rather than an edge case. Driving the
product manager agent to completion against this deployment's model with
identical input, twice, thinking enabled:

    trial 1: PROSE-ONLY   291.1s   "# Product Intake Complete ..."
    trial 2: STRUCTURED    61.5s

Roughly half. Across ten sequential stages, most runs will land on it at least
once, so it is handled as a retryable stage failure: route back to the producer
on a fresh conversation, bounded by the shared retry budget.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parent.parent / "src/app/graph/workflow.py"

#: Artifacts a later stage reads, and the stage that produces each.
PRODUCERS = {
    "product_intake": "product_manager",
    "tools_models": "tools_models",
    "stack_selection": "stack_selector",
    "technical_specification": "principal_architect",
    "sprint_plan": "scrum_master",
    "milestone_plan": "technical_lead",
}


def test_every_producer_is_mapped():
    from app.graph.workflow import _PRODUCED_BY

    assert _PRODUCED_BY == PRODUCERS


def test_a_missing_artifact_routes_back_to_its_producer():
    from app.graph.workflow import _missing_upstream

    update = _missing_upstream({}, "technical_specification")

    assert update is not None
    assert update["stage"] == "principal_architect"
    assert update["structured_retries"]["principal_architect:technical_specification"] == 1


def test_a_present_artifact_passes_through():
    from app.graph.workflow import _missing_upstream

    assert _missing_upstream({"sprint_plan": object()}, "sprint_plan") is None


def test_the_first_missing_artifact_decides():
    from app.graph.workflow import _missing_upstream

    update = _missing_upstream({"product_intake": object()}, "product_intake", "tools_models")

    assert update["stage"] == "tools_models"


def test_the_retry_budget_is_bounded():
    from app.graph.workflow import _max_structured_retries, _missing_upstream

    spent = _max_structured_retries()
    update = _missing_upstream(
        {"structured_retries": {"scrum_master:sprint_plan": spent}}, "sprint_plan"
    )

    assert update["stage"] == "failed"
    assert "scrum master" in update["error"]
    assert "structured response" in update["error"]
    assert "still in docs/" in update["error"]


def test_an_unmapped_key_fails_rather_than_looping():
    from app.graph.workflow import _missing_upstream

    update = _missing_upstream({}, "something_nobody_makes")

    assert update["stage"] == "failed"
    assert "no stage has produced it" in update["error"]


def test_as_text_handles_every_shape():
    from app.graph.workflow import _as_text

    assert _as_text(None) == ""
    assert "a" in _as_text({"a": 1})

    class _Model:
        def model_dump_json(self, indent=2):
            return '{"x": 1}'

    assert _as_text(_Model()) == '{"x": 1}'


@pytest.mark.parametrize(
    "node, producer",
    [
        ("principal_architect", "product_manager"),
        ("architecture_review", "principal_architect"),
        ("scrum_master", "principal_architect"),
        ("technical_lead", "scrum_master"),
        ("specialist_dispatch", "technical_lead"),
        ("test_and_triage", "technical_lead"),
        ("milestone_review", "technical_lead"),
    ],
)
def test_every_consuming_node_guards_its_input(node, producer, tmp_path):
    """The guard must be the first thing the node does, before any read (once checked on each node's source; now
    each node is run with nothing upstream in state)."""
    from types import SimpleNamespace

    from langgraph.checkpoint.memory import MemorySaver

    from app.graph.workflow import build_workflow_graph

    graph = build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(tmp_path))
    update = graph.nodes[node].bound.invoke(
        {"repository": SimpleNamespace(root_path=str(tmp_path))}, {"configurable": {"thread_id": "t", "run_id": "r"}},
    )

    assert update["stage"] == producer, f"{node} reads upstream state unguarded"
    assert any(key.startswith(f"{producer}:") for key in update["structured_retries"])


def test_no_consuming_node_reads_an_artifact_before_guarding():
    """A direct subscript outside a guarded node is the bug this prevents."""
    lines = WORKFLOW.read_text().split("\n")
    unguarded = []
    for number, line in enumerate(lines, 1):
        for key in re.findall(r'state\["([a-z_]+)"\]', line):
            if key not in PRODUCERS:
                continue
            start = next(
                (i for i in range(number - 1, 0, -1) if re.match(r"    def \w+\(state", lines[i - 1])),
                0,
            )
            window = "\n".join(lines[start : start + 6])
            if "_missing_upstream" not in window:
                unguarded.append((number, key))

    assert not unguarded, f"unguarded reads: {unguarded}"
