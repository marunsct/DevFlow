"""A milestone review does not send a sprint back to build a later sprint's work.

One run's sprint 1 - "basic UI skeleton, state management, persistence, and
addTask", with "Editing, deleting or toggling tasks" out of scope and sprint 2
building exactly those - was blocked by its review for not editing or deleting.
"""
from __future__ import annotations

from typing import Any

from app.agents.milestone_reviewer import MilestoneReviewFinding, MilestoneReviewOutput
from app.agents.scrum_master import SprintDefinition, SprintPlanOutput
from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.analysis.integration_checks import later_sprint_work_in
from app.graph.workflow import start_workflow
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    ScriptedAgents,
    _approved_review,
    _document,
    _graph,
    _repository,
    _script_through_architecture,
    _security_review,
    _specialist,
    agents,
    responds_with,
)

NOW = "Create the list and addTask; tasks persist in storage.\nSubmitting the form creates a task."
LATER = "Implement editTask(id, updates) and deleteTask(id).\nDeleting a task removes it."


class TestReadingAFinding:
    def test_a_finding_about_a_later_sprint_s_action_is_named(self) -> None:
        finding = 'The app does not support editing of existing tasks, required by "Users can add, edit, delete tasks".'
        assert later_sprint_work_in(finding, NOW, LATER) == ["edit"]

    def test_a_finding_about_this_sprint_s_work_is_not(self) -> None:
        assert later_sprint_work_in("addTask accepts an empty title.", NOW, LATER) == []

    def test_a_finding_about_no_action_is_not(self) -> None:
        assert later_sprint_work_in("The server resolves paths without validation.", NOW, LATER) == []

    def test_an_action_no_later_sprint_builds_is_not(self) -> None:
        assert later_sprint_work_in("Tasks cannot be archived.", NOW, LATER) == []


def _review(*findings: tuple[str, str], status: str) -> MilestoneReviewOutput:
    return MilestoneReviewOutput(
        status=status,
        findings=[MilestoneReviewFinding(severity=s, category="regression", description=d,
                                         required_remediation="Build it.") for s, d in findings],
        acceptance_evidence="checked", documentation_reviewed=True, tests_reviewed=True,
    )


def test_sprint_one_is_not_sent_back_for_sprint_two_s_work(agents: ScriptedAgents, tmp_path: Any) -> None:
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(SprintPlanOutput(sprints=[
        SprintDefinition(goal="Add tasks and keep them", user_value="v",
                         in_scope=["addTask and storage"], out_of_scope=["Editing or deleting tasks"]),
        SprintDefinition(goal="Edit and delete tasks", user_value="v",
                         in_scope=["editTask(id, updates)", "deleteTask(id)"]),
    ]))])

    def plan(goal: str) -> MilestonePlanOutput:
        return MilestonePlanOutput(selected_sprint_goal=goal, delegated_tasks=[
            SpecialistTask(specialist_role="backend", title=goal, task_description="do it", acceptance_criteria=["works"]),
        ])

    agents.script("technical_lead", [responds_with(plan("Add tasks and keep them")), responds_with(plan("Edit and delete tasks"))])
    agents.script("specialist_backend", [responds_with(_specialist()) for _ in range(2)])
    agents.script("specialist_testing", [responds_with(_specialist()) for _ in range(2)])
    agents.script("security_reviewer", [responds_with(_security_review()) for _ in range(2)])
    agents.script("milestone_reviewer", [
        responds_with(_review(("blocking", "The application does not support editing of existing tasks."),
                              status="changes_required")),
        responds_with(_review(status="accepted")),
    ])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-sprint-scope")

    assert state["stage"] == "complete", state.get("error")
    assert state.get("milestone_revision_count", 0) == 0
    record = (tmp_path / "docs" / "sprint_1_summary.md").read_text(encoding="utf-8")
    assert "Planned for a later sprint (edit)" in record
    first_review = agents.requests["milestone_reviewer"][0]["messages"][-1]["content"]
    assert "Deferred by the plan, not part of this sprint:\n- Editing or deleting tasks" in first_review
    assert "Sprint 2: Edit and delete tasks" in first_review


class TestAFileALaterSprintMakes:
    """One run's sprint 1 built the task store alone; sprint 2's scope read
    "Add index.html in the project root"; sprint 1's third review raised
    "The repository contains no index.html" as blocking and ended the run."""

    NOW = "Build a robust TaskStore module.\nsrc/task-store.js with CRUD and persistence."
    LATER = "Implement the interactive UI.\nAdd index.html in the project root.\nCreate src/ui.js."

    def test_a_missing_file_a_later_sprint_makes_is_named(self) -> None:
        from app.analysis.integration_checks import later_sprint_files_in

        finding = "The repository contains no index.html or other HTML entry point, so the app cannot load."
        assert later_sprint_files_in(finding, self.NOW, self.LATER) == ["index.html"]

    def test_a_finding_that_names_this_sprint_s_file_is_not(self) -> None:
        from app.analysis.integration_checks import later_sprint_files_in

        finding = "src/task-store.js does not dispatch the update event that index.html listens for."
        assert later_sprint_files_in(finding, self.NOW, self.LATER) == []

    def test_a_technology_written_with_a_dot_is_not_a_file(self) -> None:
        """The run's other blocking finding - a Node-only import in browser code -
        began "a Node.js module", and a later sprint may well say Node.js."""
        from app.analysis.integration_checks import later_sprint_files_in

        finding = "TaskStore imports 'node:crypto', a Node.js module not available in browsers."
        assert later_sprint_files_in(finding, self.NOW, self.LATER + "\nRun Node.js tests.") == []

    def test_a_file_no_later_sprint_names_is_not(self) -> None:
        from app.analysis.integration_checks import later_sprint_files_in

        assert later_sprint_files_in("There is no server.js to serve the page.", self.NOW, self.LATER) == []


class TestWhatARevisionIsAskedToChange:
    """On the same run the revisions took on the review's suggestions - encrypt
    stored tasks, remove @playwright/test - and the encryption lost its key on
    every reload, a new major."""

    def test_only_what_gates_is_required_and_the_rest_is_marked_so(self) -> None:
        from app.graph.workflow import _milestone_changes_requested

        text = _milestone_changes_requested(_review(
            ("major", "addTask does not dispatch tasks-updated."),
            ("suggestion", "Consider encrypting stored tasks."),
            ("minor", "The documentation lists an off() method."),
            status="changes_required",
        ))

        required, _, noted = text.partition("NOT required in this revision")
        assert "addTask does not dispatch" in required
        assert "encrypting" not in required and "off() method" not in required
        assert "encrypting" in noted and "off() method" in noted

    def test_with_nothing_gating_every_finding_is_listed_as_before(self) -> None:
        from app.graph.workflow import _milestone_changes_requested

        text = _milestone_changes_requested(_review(("minor", "A typo."), status="changes_required"))

        assert text == "[minor] regression: A typo. -> Build it."
