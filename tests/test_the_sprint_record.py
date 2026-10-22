"""The Sprint Record: every finding kept, its fate stated, and the rest carried on.

The operator's plan: "detailed sprint milestone review document clearly
capturing the sprint backlogs, defects or issues identified and steps took to
resolving it; make sure every sprint is completed before starting the next".
Findings below the gating severity were never written down - the next sprint
began with the review comments cleared - so a minor defect the review saw in one
run survived the next run too.
"""
from __future__ import annotations

from types import SimpleNamespace as NS
from typing import Any

from app.agents.milestone_reviewer import MilestoneReviewFinding, MilestoneReviewOutput
from app.agents.scrum_master import SprintDefinition, SprintPlanOutput
from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.graph.workflow import start_workflow
from app.sprint.record import (
    carried_from,
    defect_log,
    definition_of_done_gaps,
    findings_of,
    lessons_from,
    with_dispositions,
    work_order_outcomes,
)
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


def _review(*findings: tuple[str, str], status: str = "accepted") -> MilestoneReviewOutput:
    return MilestoneReviewOutput(
        status=status,
        findings=[
            MilestoneReviewFinding(severity=sev, category="correctness", description=text,
                                   required_remediation=f"fix {text}")
            for sev, text in findings
        ],
        acceptance_evidence="checked",
        documentation_reviewed=True,
        tests_reviewed=True,
    )


class TestFindings:
    def test_every_round_is_kept_and_its_fate_stated(self):
        history = (
            findings_of(_review(("blocking", "suite fails"), status="changes_required"), "milestone", 1)
            + findings_of(_review(("minor", "stale label")), "milestone", 2)
        )
        rows = with_dispositions(history, completed=True, more_sprints=True)
        assert [r["disposition"] for r in rows] == ["fixed in a revision", "carried to the next sprint"]

    def test_the_last_sprint_lists_them_as_known_issues(self):
        rows = with_dispositions(findings_of(_review(("minor", "x")), "milestone", 1),
                                 completed=True, more_sprints=False)
        assert rows[0]["disposition"] == "known issue at release"

    def test_a_failed_sprint_leaves_them_open(self):
        rows = with_dispositions(findings_of(_review(("major", "x")), "milestone", 1),
                                 completed=False, more_sprints=True)
        assert rows[0]["disposition"].startswith("open")

    def test_only_what_did_not_block_the_last_round_is_carried(self):
        history = (
            findings_of(_review(("major", "old problem"), status="changes_required"), "milestone", 1)
            + findings_of(_review(("minor", "stale label"), ("suggestion", "stale label")), "milestone", 2)
        )
        carried = carried_from(history, sprint_number=1)
        assert carried == ["stale label (sprint 1 milestone review, minor) - suggested: fix stale label"]


class TestWorkAndDefects:
    def test_each_work_order_is_matched_to_its_result(self):
        plan = MilestonePlanOutput(selected_sprint_goal="g", delegated_tasks=[
            SpecialistTask(specialist_role="backend", title="Add an item", task_description="Add.", files=["a/x"]),
            SpecialistTask(specialist_role="testing", task_description="Test it.\nmore"),
        ])
        outputs = {"specialist_backend_0": NS(blockers=[], changed_files=["a/x"],
                                              verification=[NS(command=["npm", "test"], exit_code=0)])}
        rows = work_order_outcomes(plan, outputs)
        assert rows[0]["outcome"] == "delivered" and rows[0]["verification"] == ["npm test (exit 0)"]
        assert rows[1] == {**rows[1], "title": "Test it.", "outcome": "not run"}

    def test_a_defect_log_says_which_fixes_were_proven(self):
        cycle = NS(defects=[
            NS(status="fixed", verified_by="npm test", severity="major", description="a", owner="backend",
               reproduction_steps="r", expected_behavior="e", actual_behavior="x", affected_files=["f"],
               regression_test="t", resolution="trimmed the value before saving; changed a/x"),
            NS(status="fixed", verified_by="", severity="minor", description="b", owner="ui_ux",
               reproduction_steps="", expected_behavior="", actual_behavior="", affected_files=[],
               regression_test=""),
        ])
        log = defect_log(cycle)
        assert [(d["id"], d["state"]) for d in log] == [("D1", "fixed, verified"), ("D2", "fixed, unverified")]
        assert log[0]["resolution"] == "trimmed the value before saving; changed a/x"
        assert log[1]["resolution"] == ""

    def test_not_done_means_a_missing_result_or_an_open_defect(self):
        plan = MilestonePlanOutput(selected_sprint_goal="g", delegated_tasks=[
            SpecialistTask(specialist_role="backend", title="Add", task_description="Add."),
        ])
        open_defect = NS(defects=[NS(status="open", description="broken", severity="major")])
        gaps = definition_of_done_gaps(plan, {}, open_defect)
        assert any("has no result" in g for g in gaps)
        assert any("D1 is still open: broken" in g for g in gaps)
        assert definition_of_done_gaps(
            plan, {"specialist_backend_0": NS(blockers=[], changed_files=[], verification=[])}, NS(defects=[])
        ) == []


class TestLessons:
    def test_a_repeated_failure_is_a_lesson_and_a_single_one_is_not(self):
        entries = []
        for n, path in enumerate(["a.js", "b.js", "c.js"]):
            entries += [
                {"kind": "tool_call", "call_id": f"c{n}", "tool": "run_terminal_command", "at": "2"},
                {"kind": "tool_result", "call_id": f"c{n}", "at": "2",
                 "content": '{"error": "\'node -e\' is not permitted: it can execute arbitrary code. Put it in a file."}'},
            ]
        entries += [
            {"kind": "tool_call", "call_id": "x", "tool": "read_file", "at": "2"},
            {"kind": "tool_result", "call_id": "x", "at": "2", "content": "Error: File '/z' not found"},
            {"kind": "tool_call", "call_id": "old", "tool": "ls", "at": "0"},
            {"kind": "tool_result", "call_id": "old", "at": "0", "content": "Error: before this sprint"},
            {"kind": "tool_result", "call_id": "old", "at": "0", "content": "Error: before this sprint"},
        ]
        lessons = lessons_from(entries, since="1")
        assert lessons == ["`run_terminal_command` failed 3 times: '…' is not permitted: it can execute arbitrary code."]


def test_a_minor_finding_reaches_the_next_sprint_s_lead_and_its_record(
    agents: ScriptedAgents, tmp_path: Any
) -> None:
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(SprintPlanOutput(sprints=[
        SprintDefinition(goal="Sprint 1", user_value="v"), SprintDefinition(goal="Sprint 2", user_value="v"),
    ]))])

    def plan(goal: str, decisions: list[str]) -> MilestonePlanOutput:
        return MilestonePlanOutput(
            selected_sprint_goal=goal,
            delegated_tasks=[SpecialistTask(specialist_role="backend", title=f"{goal} work",
                                            task_description="do it", acceptance_criteria=["works"])],
            carried_forward_decisions=decisions,
        )

    agents.script("technical_lead", [
        responds_with(plan("Sprint 1", [])),
        responds_with(plan("Sprint 2", ["An empty note cannot be edited -> task 1"])),
    ])
    agents.script("specialist_backend", [responds_with(_specialist()), responds_with(_specialist())])
    agents.script("specialist_testing", [responds_with(_specialist()), responds_with(_specialist())])
    agents.script("security_reviewer", [responds_with(_security_review()), responds_with(_security_review())])
    agents.script("milestone_reviewer", [
        responds_with(_review(("minor", "An empty note cannot be edited"))),
        responds_with(_review()),
    ])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-sprint-record")

    assert state["stage"] == "complete", state.get("error")
    assert "An empty note cannot be edited (sprint 1 milestone review, minor)" in agents.last_request_text(
        "technical_lead"
    )
    record = (tmp_path / "docs" / "sprint_1_summary.md").read_text(encoding="utf-8")
    assert "carried to the next sprint" in record
    assert "## Carried Forward\n- An empty note cannot be edited" in record
    assert "- Sprint 1 work" in record.split("## Features Implemented", 1)[1]
