"""Tests that security_review_node handles changed files without NameError on Path."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from app.agents.specialists import SpecialistOutput
from app.graph.workflow import build_workflow_graph
from app.state import RepositoryContext


def test_security_review_node_with_non_code_changed_files_defines_path(tmp_path):
    graph = build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(tmp_path))
    node = graph.nodes["security_review"]
    state = {
        "repository": RepositoryContext(root_path=str(tmp_path), branch="main", commit="HEAD", status="clean"),
        "specialist_outputs": {
            "specialist_backend_0": SpecialistOutput(
                changed_files=["docs/architecture.md"],
            )
        },
    }
    # Fails with NameError: name 'Path' is not defined on unfixed code
    update = node.bound.invoke(state)
    assert update["stage"] == "advice_review"
    assert update["security_review"].status == "passed"

