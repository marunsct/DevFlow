"""A sprint is reviewed for security, and for how it keeps data, whenever it changed code - in any language.

The reviews were skipped unless a JavaScript, Python, HTML or JSON file had
changed, so a product in any other language - or a sprint that changed only a
container definition, a shell script or a CI pipeline - was never reviewed at
all; and the review of how data is kept ran only when a file's name happened
to contain "db", "store", "model" or the like. Only a sprint that changed
nothing but prose, styles and images skips them now.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.agents.specialists import SpecialistOutput
from app.graph.workflow import _changes_any_code, build_workflow_graph
from app.state import RepositoryContext


@pytest.mark.parametrize("files", [
    ["api/handlers.go"], ["src/main/java/app/Store.java"], ["app/models.rb"], ["src/lib.rs"],
    ["public/index.php"], ["Dockerfile"], [".github/workflows/ci.yml"], ["scripts/deploy.sh"],
    ["app/src/app.js"], ["db/migrations/001.sql"], ["docs/notes.md", "app/server.py"],
])
def test_code_in_any_language_is_reviewed(files):
    assert _changes_any_code(files)


@pytest.mark.parametrize("files", [[], ["README.md"], ["app/styles.css", "docs/guide.md", "img/logo.png"]])
def test_prose_styles_and_images_are_not(files):
    assert not _changes_any_code(files)


def _state(tmp_path, changed):
    return {
        "repository": RepositoryContext(root_path=str(tmp_path), branch="main", commit="HEAD", status="clean"),
        "specialist_outputs": {"specialist_backend_0": SpecialistOutput(changed_files=changed)},
    }


class TestTheSecurityReview:
    def _run(self, tmp_path, changed):
        with patch("app.graph.workflow.create_security_reviewer_agent", return_value=MagicMock()) as created, \
             patch("app.graph.workflow._run_gated_agent", return_value={"__security_review__": None, "stage": "x"}):
            graph = build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(tmp_path))
            try:
                graph.nodes["security_review"].bound.invoke(_state(tmp_path, changed))
            except Exception:  # noqa: BLE001 - only whether a reviewer was made matters here
                pass
        return created.called

    def test_runs_on_a_service_in_go(self, tmp_path):
        assert self._run(tmp_path, ["api/handlers.go"])

    def test_is_skipped_for_a_restyle(self, tmp_path):
        assert not self._run(tmp_path, ["app/styles.css"])


class TestTheReviewOfHowDataIsKept:
    def _run(self, tmp_path, changed):
        state = {**_state(tmp_path, changed), "current_sprint_index": 0, "milestone_revision_count": 0}
        with patch("app.agents.advice_review.roles_to_review", return_value=["database"]), \
             patch("app.agents.specialist_advice.adopted", return_value=["Write each change before answering"]), \
             patch("app.graph.workflow._run_gated_agent", return_value={"stage": "advice_review"}) as gated:
            graph = build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(tmp_path))
            try:
                graph.nodes["advice_review"].bound.invoke(state, {"configurable": {"thread_id": "t"}})
            except Exception:  # noqa: BLE001 - only whether the review ran matters here
                pass
        return gated.called

    def test_runs_when_data_is_kept_in_a_file_named_for_nothing(self, tmp_path):
        assert self._run(tmp_path, ["app/src/app.js"])

    def test_is_skipped_for_prose_only(self, tmp_path):
        assert not self._run(tmp_path, ["docs/guide.md"])
