"""A sprint planned again for its tests keeps the milestone review's revisions.

Both were counted on `milestone_revision_count`. Measured on one run: one
re-plan after three test rounds, then two milestone reviews - the first blocked
on a `require` in an ES module, which was fixed; the second raised four
findings, none of them the first's - and the run ended "after 3 revisions", ten
minutes in, on the first review whose findings nobody had been given a chance
to fix.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from langgraph.checkpoint.memory import MemorySaver

from app.agents.specialists import SpecialistOutput
from app.graph import end_of_attempt, workflow
from app.sprint import RemediationCycle


def _a_round_that_spends_the_last_attempt(tmp_path, **counters) -> dict:
    """The test round's node, its round failing on the attempt that exhausts the sprint's remediation."""
    milestone = SimpleNamespace(selected_sprint_goal="Count words", milestone_scope=[], delegated_tasks=[])
    cycle = RemediationCycle(sprint_goal="Count words", attempt=2, max_attempts=3)
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)), "milestone_plan": milestone, "test_round": 3,
        "specialist_outputs": {}, "review_defects": [], "current_sprint_index": 0, "remediation": cycle,
        "sprint_plan": SimpleNamespace(sprints=["s1", "s2"]), **counters,
    }
    failing = workflow._the_unit_tests_fail(milestone, "AssertionError: 2 != 3")
    with patch("app.graph.acceptance_nodes.acceptance_for_round", return_value=("", [])), \
         patch("app.graph.acceptance_nodes.reopen_the_suite_for", return_value=None), \
         patch("app.graph.acceptance_nodes.beyond_repair", return_value=[]), \
         patch("app.graph.acceptance_nodes._failing_due", return_value=(["AC-1"], "npx playwright test")), \
         patch("app.graph.workflow._run_unit_tests_procedurally", return_value=(False, "AssertionError")), \
         patch("app.graph.acceptance_nodes.suite.is_locked", return_value=True), \
         patch("app.graph.acceptance_nodes.suite.last_result", return_value={"ran": True, "passed": 1, "failed": 1}), \
         patch("app.agents.specialists.what_the_files_already_prove", return_value=[]), \
         patch("app.graph.acceptance_nodes.interface_defects", return_value=[]), \
         patch("app.graph.acceptance_nodes.failing_due_defects", return_value=[]), \
         patch.object(end_of_attempt, "decide", return_value=end_of_attempt.Decision(end_of_attempt.REPLAN)), \
         patch("app.graph.workflow._run_gated_agent",
               return_value={"__test_result__": SpecialistOutput(changed_files=[], defects=[failing])}):
        graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(tmp_path))
        return graph.nodes["test_and_triage"].bound.invoke(state, {"configurable": {"thread_id": "t", "run_id": "r"}})


def test_a_replan_is_counted_on_its_own_counter(tmp_path) -> None:
    update = _a_round_that_spends_the_last_attempt(tmp_path, milestone_revision_count=2, sprint_replan_count=0)

    assert update["stage"] == "technical_lead"
    assert update["sprint_replan_count"] == 1
    # The review's counter is not written on this path at all.
    assert "milestone_revision_count" not in update


def test_the_replan_is_still_bounded(tmp_path) -> None:
    replanned = _a_round_that_spends_the_last_attempt(
        tmp_path, sprint_replan_count=workflow.MAX_MILESTONE_REVISIONS - 1)
    assert replanned["stage"] == "technical_lead"

    update = _a_round_that_spends_the_last_attempt(tmp_path, sprint_replan_count=workflow.MAX_MILESTONE_REVISIONS)
    assert update["stage"] == "escalation" and "re-planned 3 times" in update["escalation"]["error"]


def test_both_counters_start_again_with_the_next_sprint(tmp_path) -> None:
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)), "current_sprint_index": 0,
        "sprint_plan": SimpleNamespace(sprints=["s1", "s2"]), "milestone_revision_count": 2, "sprint_replan_count": 1,
        "milestone_plan": SimpleNamespace(selected_sprint_goal="Count words", milestone_scope=[], delegated_tasks=[]),
    }
    graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(tmp_path))

    update = graph.nodes["sprint_advance"].bound.invoke(state, {"configurable": {"thread_id": "t", "run_id": "r"}})

    assert update["current_sprint_index"] == 1
    assert update["milestone_revision_count"] == 0 and update["sprint_replan_count"] == 0
    assert workflow._REWIND_COUNTER_RESETS["milestone_review"] == {
        "milestone_revision_count": 0, "sprint_replan_count": 0,
    }


def test_the_state_declares_it() -> None:
    assert "sprint_replan_count" in workflow.WorkflowGraphState.__annotations__
