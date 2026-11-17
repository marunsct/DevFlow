"""A retry must reach the graph, not be overwritten by the node that got it.

`_run_gated_agent` already retried a stage that produced no structured
response, on a fresh conversation, and that machinery worked. What defeated it
was the caller.

`product_manager_node` tested only `_is_paused(update["stage"])`. A retry's
stage is `product_manager`, which is not a pause, so the node fell through to:

    next_stage = "user_review_product_intake" if ... else "tools_models"
    update["stage"] = next_stage

overwriting "go back and try again" with "carry on", and handing the next stage
a state with no `product_intake` in it. That is how one run reached
`KeyError: 'product_intake'` even though the retry fired correctly.

Both hand-back shapes look identical from the caller's side - the output key is
absent - so that is what is tested.
"""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(("update", "handed_back"), [
    ({"stage": "product_manager", "structured_retries": {}}, True),
    ({"stage": "awaiting_approval:product_manager"}, True),
    ({"stage": "tools_models", "product_intake": "the intake"}, False),
], ids=["a retry", "a pause", "a finished stage"])
def test_only_an_update_without_its_output_is_handed_back(update, handed_back):
    from app.graph.workflow import _hand_back

    assert bool(_hand_back(update, "product_intake")) is handed_back


def _a_state_every_planning_stage_can_read(root) -> dict:
    from types import SimpleNamespace

    from app.agents.principal_architect import TechnicalSpecificationOutput
    from app.agents.scrum_master import SprintDefinition, SprintPlanOutput
    from app.agents.stack_selector import StackSelectorOutput, TechnologyStack
    from app.state import RepositoryContext

    stack = TechnologyStack(language="TypeScript", framework="Hono", frontend_framework="", database="SQLite",
                            testing_framework="node:test", product_kind="http_api", additional_tools=[])
    sprint = SprintDefinition(goal="Notes", user_value="v", in_scope=["notes"], out_of_scope=[],
                              acceptance_criteria=["works"], dependencies=[])
    return {
        "document": SimpleNamespace(text="Notes over HTTP."),
        "repository": RepositoryContext(root_path=str(root), branch="main", commit="abc", status="clean"),
        "product_intake": {"product_name": "Notes"},
        "tools_models": {"plan": "local"},
        "stack_selection": StackSelectorOutput(technology_stack=stack, rationale="As the brief asks."),
        "technical_specification": TechnicalSpecificationOutput(product_scope="Notes."),
        "sprint_plan": SprintPlanOutput(sprints=[sprint], success_measure_coverage=[]),
        "current_sprint_index": 0,
    }


@pytest.mark.parametrize(
    ("node", "output_key"),
    [
        ("product_manager", "product_intake"),
        ("principal_architect", "technical_specification"),
        ("architecture_review", "architecture_review"),
        ("scrum_master", "sprint_plan"),
        ("technical_lead", "milestone_plan"),
        ("tools_models", "tools_models"),
        ("stack_selector", "stack_selection"),
        ("specialist_consultation", "__advice__"),
        ("acceptance_dispute", "__suite_dispute__"),
        ("advice_review", "__advice_review__"),
    ],
)
def test_every_post_processing_node_checks_for_a_hand_back(node, output_key, tmp_path):
    """Each node that post-processes a gated agent's result hands a retry back as it came (once checked on each
    node's source; now each node is run with its stage asking for a retry).

    Every node that checks for a hand-back is here, so testing for a pause alone - `_is_paused(update["stage"])`,
    the bug, which misses the retry shape - fails in whichever node it comes back to.
    """
    from unittest.mock import MagicMock, patch

    from langgraph.checkpoint.memory import MemorySaver

    from app.graph import workflow

    retry = {"stage": node, "structured_retries": {node: 1}, "pending_inner_thread_id": None}
    creators = [name for name in dir(workflow) if name.startswith("create_") and name.endswith("_agent")]
    with patch.multiple(workflow, **{name: MagicMock() for name in creators}), \
         patch("app.agents.research_brief.research_notes", return_value=""), \
         patch("app.graph.acceptance_nodes.sprint_already_done", return_value=""), \
         patch("app.graph.workflow.build_intake_request", return_value={"messages": [{"role": "user", "content": ""}]}), \
         patch("app.graph.workflow._fast_delivery", return_value=False), \
         patch("app.graph.workflow._the_locked_tests_still_failing",
               return_value=[("[AC-1] a note is kept", "AC-1", "expected 201, got 500")]), \
         patch("app.agents.advice_review.roles_to_review", return_value=["backend"]), \
         patch("app.agents.specialist_advice.adopted", return_value=["Write each change before answering"]), \
         patch("app.graph.workflow._run_gated_agent", return_value=dict(retry)):
        graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(tmp_path))
        update = graph.nodes[node].bound.invoke(
            _a_state_every_planning_stage_can_read(tmp_path), {"configurable": {"thread_id": "t", "run_id": "r"}},
        )

    assert update["stage"] == node, (
        f"{node} post-processes a gated agent's result without checking for a "
        "hand-back, so a retry's routing would be overwritten"
    )
    assert output_key not in update


def test_a_retry_carries_no_output_key():
    """The property `_hand_back` relies on.

    Asserted against the retry update itself rather than a block of source
    text. Both ways a stage can produce no answer - returning empty, and
    spinning to the recursion limit - now build their restart in
    `_restart_on_a_fresh_conversation`, so reading one inline block would have
    checked only the half that happened to remain there.
    """
    from app.graph.workflow import _restart_on_a_fresh_conversation

    update = _restart_on_a_fresh_conversation({}, "specialist_ui_ux_0", "t", "why")

    assert update is not None
    assert update["stage"] == _owning_node_of("specialist_ui_ux_0")
    assert not any("output" in key for key in update), (
        "the retry update must not carry the output key, or callers cannot "
        "distinguish it from a finished stage"
    )


def _owning_node_of(stage_name: str) -> str:
    from app.graph.workflow import _owning_node

    return _owning_node(stage_name)
