"""A retry must reach the graph, not be overwritten by the node that got it.

`_run_gated_agent` already retried a stage that produced no structured
response, on a fresh conversation, and that machinery worked. What defeated it
was the caller.

`product_manager_node` tested only `_is_paused(update["stage"])`. A retry's
stage is `product_manager`, which is not a pause, so the node fell through to:

    next_stage = "user_review_product_intake" if ... else "tools_models"
    update["stage"] = next_stage

overwriting "go back and try again" with "carry on", and handing the next stage
a state with no `product_intake` in it. That is how run-c826ae90 reached
`KeyError: 'product_intake'` even though the retry fired correctly.

Both hand-back shapes look identical from the caller's side - the output key is
absent - so that is what is tested.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parent.parent / "src/app/graph/workflow.py"


def test_an_update_without_its_output_is_handed_back():
    from app.graph.workflow import _hand_back

    assert _hand_back({"stage": "product_manager", "structured_retries": {}}, "product_intake")


def test_a_paused_update_is_handed_back():
    from app.graph.workflow import _hand_back

    assert _hand_back({"stage": "awaiting_approval:product_manager"}, "product_intake")


def test_a_finished_stage_is_not_handed_back():
    from app.graph.workflow import _hand_back

    update = {"stage": "tools_models", "product_intake": object()}

    assert not _hand_back(update, "product_intake")


@pytest.mark.parametrize(
    ("node", "output_key"),
    [
        ("product_manager_node", "product_intake"),
        ("principal_architect_node", "technical_specification"),
        ("architecture_review_node", "architecture_review"),
        ("scrum_master_node", "sprint_plan"),
        ("technical_lead_node", "milestone_plan"),
    ],
)
def test_every_post_processing_node_checks_for_a_hand_back(node, output_key):
    text = WORKFLOW.read_text()
    start = text.index(f"    def {node}(state")
    end = text.index("\n    def ", start + 10)
    body = text[start:end]

    assert f'_hand_back(update, "{output_key}")' in body, (
        f"{node} post-processes a gated agent's result without checking for a "
        "hand-back, so a retry's routing would be overwritten"
    )


def test_no_node_tests_only_for_a_pause():
    """`_is_paused(update[...])` alone is the bug; it misses the retry shape."""
    text = WORKFLOW.read_text()

    assert '_is_paused(update["stage"])' not in text
    assert "_is_paused(update.get" not in text


def test_a_retry_carries_no_output_key():
    """The property `_hand_back` relies on.

    Asserted against the retry update itself rather than a block of source
    text. Both ways a stage can produce no answer - returning empty, and
    spinning to the recursion limit - now build their restart in
    `_restart_on_a_fresh_conversation`, so reading one inline block would have
    checked only the half that happened to remain there.
    """
    import inspect

    from app.graph.workflow import _restart_on_a_fresh_conversation

    update = _restart_on_a_fresh_conversation({}, "specialist_ui_ux_0", "t", "why")

    assert update is not None
    assert update["stage"] == _owning_node_of("specialist_ui_ux_0")
    assert not any("output" in key for key in update), (
        "the retry update must not carry the output key, or callers cannot "
        "distinguish it from a finished stage"
    )
    # Both NO-ANSWER paths build their restart here; `_transient_retry_update`
    # is a separate case (a transient model error, not a missing answer) and
    # keeps its own update. That the two no-answer paths share this one is
    # asserted in tests/test_spin_restart.py.
    assert "_restart_on_a_fresh_conversation" in inspect.getsource(
        __import__("app.graph.workflow", fromlist=["x"])._run_gated_agent
    )


def _owning_node_of(stage_name: str) -> str:
    from app.graph.workflow import _owning_node

    return _owning_node(stage_name)
