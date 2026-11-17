"""A milestone-review finding whose files are all in the locked acceptance suite is recorded as minor.

Measured on one run: every test passed and the milestone review called a locked test vacuous (major). No sprint may
change the locked suite, and the lead's plan was sent back twice for a work order to change it.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.acceptance import suite
from app.agents.milestone_reviewer import MilestoneReviewOutput
from app.graph import workflow


def _review(*findings):
    return MilestoneReviewOutput.model_validate({
        "status": "changes_required", "acceptance_evidence": "read", "documentation_reviewed": True,
        "tests_reviewed": True,
        "findings": [{"category": "testing", **finding} for finding in findings],
    })


def _a_suite(root: Path, *, locked: bool = True) -> None:
    suite_dir = root / "app" / "acceptance"
    suite_dir.mkdir(parents=True)
    (suite_dir / "run.json").write_text(json.dumps({"command": ["run"], "report": "r.xml"}))
    (suite_dir / "test_cli.py").write_text("def test_ac13():\n    assert True\n")
    (root / "app" / "tests").mkdir()
    (root / "app" / "tests" / "test_cli.py").write_text("def test_unit():\n    assert True\n")
    (root / ".project-directory").write_text("app\n")
    if locked:
        suite.lock(root)


SUITE = {"severity": "major", "description": "test_ac13 is vacuous: its loop runs zero times.",
         "required_remediation": "Fix the test.", "affected_files": ["app/acceptance/test_cli.py"]}
UNIT = {"severity": "major", "description": "test_unit asserts nothing.",
        "required_remediation": "Fix it.", "affected_files": ["app/tests/test_cli.py"]}
PRODUCT = {"severity": "major", "description": "AC-9: cli.py prints the counts too.",
           "required_remediation": "Print only the top words.", "affected_files": ["app/cli.py"]}


def test_a_finding_about_the_locked_suite_is_made_minor_and_others_stay(tmp_path):
    _a_suite(tmp_path)
    out = workflow._findings_about_the_locked_suite_made_minor(_review(SUITE, UNIT, PRODUCT), str(tmp_path))
    assert [f.severity for f in out.findings] == ["minor", "major", "major"]
    assert "locked acceptance suite" in out.findings[0].description


def test_before_the_lock_it_stays(tmp_path):
    _a_suite(tmp_path, locked=False)
    out = workflow._findings_about_the_locked_suite_made_minor(_review(SUITE), str(tmp_path))
    assert out.findings[0].severity == "major"


def _the_milestone_review_node(root: Path, review: MilestoneReviewOutput) -> dict:
    """The milestone review's node, its reviewer answering `review`."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from langgraph.checkpoint.memory import MemorySaver

    state = {
        "repository": SimpleNamespace(root_path=str(root)),
        "milestone_plan": SimpleNamespace(selected_sprint_goal="Count words", milestone_scope=[], delegated_tasks=[]),
        "specialist_outputs": {}, "current_sprint_index": 0, "milestone_revision_count": 0,
    }
    with patch("app.graph.workflow.create_milestone_reviewer_agent", return_value=MagicMock()), \
         patch("app.graph.workflow.build_milestone_review_request", return_value={"messages": [{"role": "user", "content": ""}]}), \
         patch("app.graph.acceptance_nodes.acceptance_text_for", return_value=""), \
         patch("app.graph.workflow._run_gated_agent", return_value={"__milestone_review__": review}):
        graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(root))
        return graph.nodes["milestone_review"].bound.invoke(state, {"configurable": {"thread_id": "t", "run_id": "r"}})


def test_the_milestone_review_applies_it(tmp_path):
    """The review the workflow acts on carries the locked suite's finding as minor, and the sprint is not sent back."""
    _a_suite(tmp_path)

    result = _the_milestone_review_node(tmp_path, _review(SUITE))

    assert [f.severity for f in result["milestone_review"].findings] == ["minor"]
    assert result.get("stage") != "technical_lead", "no plan is sent back for a work order to change the locked suite"
