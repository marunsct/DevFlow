"""`changed_files` comes from the stage, and a stage under-reports it.

Three stages are told "Files changed in this milestone" from that list - the test
round, the security review and the milestone review - and all three computed it
the same way, from each specialist's structured response.

Measured across the 28 current-generation runs: 82 stages wrote a file and did
not name it. Every role, about three per run.

    One run  test_round_0         wrote 5 files, reported none
    one run  specialist_ui_ux_1   wrote app.js, index.html, package.json,
                                       server.mjs; reported app.js
    one run  specialist_testing_2 wrote 5 files; reported app.test.mjs
    one run  specialist_ui_ux_0   wrote app.js, app.test.mjs,
                                       package.json; reported app.test.mjs

So a test round can be told nothing changed after five files did.

Git is the record that cannot under-report. Checked against one run's live
workspace: the reported list held `task-manager/app.test.mjs` alone, and the
union adds `task-manager/app.js`, which that stage wrote and did not report.

`docs/` is dropped. Those are the workflow's own documents, rendered from
structured responses, and naming `docs/milestone_plan.md` as a file this milestone
changed sends a reviewer to read the plan as if it were product code - git lists
it because the workflow really did write it.
"""

from __future__ import annotations

import subprocess

import pytest

from app.graph.workflow import _the_files_this_milestone_changed


class Output:
    def __init__(self, changed_files) -> None:
        self.changed_files = list(changed_files)


class Repository:
    def __init__(self, root: str) -> None:
        self.root_path = root


def _git(root, *args):
    subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True,
        env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
             "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(root), "PATH": "/usr/bin:/bin"},
    )


@pytest.fixture
def a_tagged_sprint(tmp_path):
    """A workspace with sprint 1 tagged and work done since."""
    project = tmp_path / "task-manager"
    project.mkdir()
    (project / "app.js").write_text("export const a = 1;\n")
    (project / "app.test.mjs").write_text("test('a', () => {});\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "milestone_plan.md").write_text("# plan\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "sprint 1")
    _git(tmp_path, "tag", "sprint-1")
    # What the sprint did after the tag, including a workflow document.
    (project / "app.js").write_text("export const a = 2;\nexport const b = 3;\n")
    (project / "index.html").write_text("<html></html>")
    (tmp_path / "docs" / "milestone_plan.md").write_text("# plan\n\nsprint 2\n")
    return tmp_path


class TestTheFilesAStageDidNotName:
    def test_a_file_written_and_not_reported_is_added(self, a_tagged_sprint):
        state = {"current_sprint_index": 1, "repository": Repository(str(a_tagged_sprint))}

        changed = _the_files_this_milestone_changed(
            state, {"a": Output(["task-manager/app.test.mjs"])}
        )

        assert "task-manager/app.js" in changed
        assert "task-manager/index.html" in changed

    def test_what_the_stage_did_report_is_kept(self, a_tagged_sprint):
        """A stage may name a file git cannot see - a union, not a replacement."""
        state = {"current_sprint_index": 1, "repository": Repository(str(a_tagged_sprint))}

        changed = _the_files_this_milestone_changed(
            state, {"a": Output(["task-manager/app.test.mjs"])}
        )

        assert "task-manager/app.test.mjs" in changed

    def test_a_stage_reporting_nothing_still_gets_the_list(self, a_tagged_sprint):
        """One run's `test_round_0` wrote five files and reported none."""
        state = {"current_sprint_index": 1, "repository": Repository(str(a_tagged_sprint))}

        changed = _the_files_this_milestone_changed(state, {"a": Output([])})

        assert "task-manager/app.js" in changed

    def test_the_workflow_documents_are_left_out(self, a_tagged_sprint):
        """Git lists `docs/milestone_plan.md` because the workflow wrote it."""
        state = {"current_sprint_index": 1, "repository": Repository(str(a_tagged_sprint))}

        changed = _the_files_this_milestone_changed(state, {"a": Output([])})

        assert not any(name.startswith("docs/") for name in changed), changed

    def test_the_list_is_sorted_and_unique(self, a_tagged_sprint):
        state = {"current_sprint_index": 1, "repository": Repository(str(a_tagged_sprint))}

        changed = _the_files_this_milestone_changed(
            state, {"a": Output(["task-manager/app.js"]), "b": Output(["task-manager/app.js"])}
        )

        assert changed == sorted(set(changed))


class TestWhenGitCannotAnswer:
    def test_the_first_sprint_uses_the_reported_list(self, a_tagged_sprint):
        """There is no earlier tag, and everything in it is new anyway."""
        state = {"current_sprint_index": 0, "repository": Repository(str(a_tagged_sprint))}

        assert _the_files_this_milestone_changed(
            state, {"a": Output(["only-this.js"])}
        ) == ["only-this.js"]

    def test_a_workspace_that_is_not_a_repository(self, tmp_path):
        state = {"current_sprint_index": 2, "repository": Repository(str(tmp_path))}

        assert _the_files_this_milestone_changed(
            state, {"a": Output(["reported.js"])}
        ) == ["reported.js"]

    def test_a_missing_tag_does_not_lose_the_reported_list(self, tmp_path):
        _git(tmp_path, "init", "-q")
        (tmp_path / "a.js").write_text("x")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-qm", "one")
        state = {"current_sprint_index": 5, "repository": Repository(str(tmp_path))}

        assert _the_files_this_milestone_changed(
            state, {"a": Output(["reported.js"])}
        ) == ["reported.js"]

    def test_no_repository_key_does_not_raise(self):
        assert _the_files_this_milestone_changed(
            {"current_sprint_index": 2}, {"a": Output(["reported.js"])}
        ) == ["reported.js"]

    def test_no_outputs_and_no_git_is_empty(self):
        assert _the_files_this_milestone_changed({}, {}) == []


def _what_the_stage_is_told_changed(root, node: str) -> list[str]:
    """The files `node` is told this milestone changed, when its one specialist reported only `app.test.mjs`."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from langgraph.checkpoint.memory import MemorySaver

    from app.agents.specialists import SpecialistOutput
    from app.graph.workflow import build_workflow_graph
    from app.state import RepositoryContext

    told: list[list[str]] = []

    def builder(position: int):
        def build(*args, **kwargs):
            told.append(list(args[position]))
            return {"messages": [{"role": "user", "content": ""}]}
        return build

    state = {
        "repository": RepositoryContext(root_path=str(root), branch="main", commit="HEAD", status="clean"),
        "specialist_outputs": {"specialist_testing_0": SpecialistOutput(changed_files=["task-manager/app.test.mjs"])},
        "current_sprint_index": 1,
        "milestone_plan": SimpleNamespace(selected_sprint_goal="Tasks", milestone_scope=[], delegated_tasks=[]),
        "test_round": 1, "review_defects": [], "milestone_revision_count": 0, "decisions": [],
    }
    with patch("app.graph.workflow.build_test_run_request", side_effect=builder(1)), \
         patch("app.graph.workflow.build_security_review_request", side_effect=builder(0)), \
         patch("app.graph.workflow.build_milestone_review_request", side_effect=builder(1)), \
         patch("app.graph.workflow.create_specialist_agent", return_value=MagicMock()), \
         patch("app.graph.workflow.create_security_reviewer_agent", return_value=MagicMock()), \
         patch("app.graph.workflow.create_milestone_reviewer_agent", return_value=MagicMock()), \
         patch("app.graph.acceptance_nodes.acceptance_for_round", return_value=("Failing", [])), \
         patch("app.graph.acceptance_nodes.reopen_the_suite_for", return_value=None), \
         patch("app.graph.acceptance_nodes.beyond_repair", return_value=[]), \
         patch("app.graph.acceptance_nodes._failing_due", return_value=(["criterion-1"], "npm test")), \
         patch("app.graph.workflow._run_unit_tests_procedurally", return_value=(False, "error")), \
         patch("app.graph.acceptance_nodes.interface_defects", return_value=[]), \
         patch("app.graph.acceptance_nodes.failing_due_defects", return_value=[]), \
         patch("app.graph.acceptance_nodes.acceptance_text_for", return_value=""), \
         patch("app.graph.workflow._run_gated_agent", return_value={"stage": "paused"}):
        graph = build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(root))
        try:
            graph.nodes[node].bound.invoke(state, {"configurable": {"thread_id": "t", "run_id": "r"}})
        except Exception:  # noqa: BLE001 - only what the stage was told matters here
            pass
    assert told, f"{node} built no request"
    return told[0]


class TestAllThreeReadersUseIt:
    @pytest.mark.parametrize("node", ["test_and_triage", "security_review", "milestone_review"])
    def test_no_site_computes_the_list_for_itself(self, a_tagged_sprint, node):
        """The test round, the security review and the milestone review all read
        this. Three copies is how they start disagreeing about what changed (once
        checked on the source; now each stage is run)."""
        changed = _what_the_stage_is_told_changed(a_tagged_sprint, node)

        assert "task-manager/index.html" in changed, (
            "a site is still building changed_files from the responses alone"
        )
        assert "task-manager/app.test.mjs" in changed
        assert not [name for name in changed if name.startswith("docs/")]
