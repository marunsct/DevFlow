"""Tests for automated procedural test round execution (Change 2).

When all acceptance criteria due and unit tests pass cleanly with zero proven
problems or review findings, the test round must complete procedurally without
invoking an LLM agent for 15 turns.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from langgraph.checkpoint.memory import MemorySaver

from app.graph.workflow import build_workflow_graph


def test_procedural_test_round_skips_gated_agent_when_all_green(tmp_path) -> None:
    # Set up mock state where all criteria due pass, unit tests pass, and 0 defects exist
    repo_root = str(tmp_path)
    state = {
        "repository": SimpleNamespace(root_path=repo_root),
        "milestone_plan": SimpleNamespace(selected_sprint_goal="Build features", milestone_scope=[], delegated_tasks=[]),
        "test_round": 1,
        "specialist_outputs": {},
        "review_defects": [],
        "current_sprint_index": 0,
    }
    config = {"configurable": {"thread_id": "test", "run_id": "test-run"}}

    # Mock acceptance_nodes
    with patch("app.graph.acceptance_nodes.acceptance_for_round", return_value=("All passed", [])), \
         patch("app.graph.acceptance_nodes.reopen_the_suite_for", return_value=None), \
         patch("app.graph.acceptance_nodes.beyond_repair", return_value=[]), \
         patch("app.graph.acceptance_nodes._failing_due", return_value=([], "npm test")), \
         patch("app.graph.workflow._run_unit_tests_procedurally", return_value=(True, "")), \
         patch("app.agents.specialists.what_the_files_already_prove", return_value=[]), \
         patch("app.graph.acceptance_nodes.interface_defects", return_value=[]), \
         patch("app.graph.acceptance_nodes.failing_due_defects", return_value=[]), \
         patch("app.graph.workflow._run_gated_agent") as mock_gated_agent:

        graph = build_workflow_graph(checkpointer=MemorySaver(), repo_root=repo_root)
        node = graph.nodes["test_and_triage"]

        res = node.bound.invoke(state, config)
        # Should not have called the LLM agent
        assert not mock_gated_agent.called, "_run_gated_agent should NOT be called when all tests pass procedurally"
        assert res.get("stage") in ("security_review", "is_sprint_acceptable")


def test_procedural_test_round_invokes_gated_agent_when_tests_fail(tmp_path) -> None:
    repo_root = str(tmp_path)
    state = {
        "repository": SimpleNamespace(root_path=repo_root),
        "milestone_plan": SimpleNamespace(selected_sprint_goal="Build features", milestone_scope=[], delegated_tasks=[]),
        "test_round": 1,
        "specialist_outputs": {},
        "review_defects": [],
        "current_sprint_index": 0,
    }
    config = {"configurable": {"thread_id": "test", "run_id": "test-run"}}

    from app.agents.specialists import SpecialistOutput

    with patch("app.graph.acceptance_nodes.acceptance_for_round", return_value=("Failing", [])), \
         patch("app.graph.acceptance_nodes.reopen_the_suite_for", return_value=None), \
         patch("app.graph.acceptance_nodes.beyond_repair", return_value=[]), \
         patch("app.graph.acceptance_nodes._failing_due", return_value=(["criterion-1"], "npm test")), \
         patch("app.graph.workflow._run_unit_tests_procedurally", return_value=(False, "error")), \
         patch("app.agents.specialists.what_the_files_already_prove", return_value=[]), \
         patch("app.graph.acceptance_nodes.interface_defects", return_value=[]), \
         patch("app.graph.acceptance_nodes.failing_due_defects", return_value=[]), \
         patch("app.graph.workflow._run_gated_agent", return_value={"__test_result__": SpecialistOutput(changed_files=[], defects=[])}) as mock_gated_agent:

        graph = build_workflow_graph(checkpointer=MemorySaver(), repo_root=repo_root)
        node = graph.nodes["test_and_triage"]

        node.bound.invoke(state, config)
        assert mock_gated_agent.called, "_run_gated_agent should be called when tests fail"


