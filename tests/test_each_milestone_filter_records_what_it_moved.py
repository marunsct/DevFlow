"""Each milestone-review filter records what it dropped or moved to another severity (harness review HR2.G.1).

Nine filters relabel the milestone review's findings, and each only logged: 6 of 21 send-backs over 40 runs were
relabelled accepted with no record, so whether any filter was right could not be measured.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from app.acceptance import check_findings
from app.agents.milestone_reviewer import MilestoneReviewFinding, MilestoneReviewOutput
from app.graph import workflow


def _a_review(*findings: MilestoneReviewFinding, status: str = "changes_required") -> MilestoneReviewOutput:
    return MilestoneReviewOutput(status=status, findings=list(findings), acceptance_evidence="seen",
                                 documentation_reviewed=True, tests_reviewed=True)


def _a_finding(severity: str, files: list[str], description: str) -> MilestoneReviewFinding:
    return MilestoneReviewFinding(severity=severity, category="correctness", description=description,
                                  affected_files=files, required_remediation="change it")


def test_a_blocking_finding_about_the_harness_s_files_leaves_one_recorded_demotion(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(workflow, "_about_the_harness_s_files_only", lambda finding, root: True)
    before = _a_review(_a_finding("blocking", ["src/main.ts"], "The start file has no signal handler."))
    after = check_findings.filtered(tmp_path, 1, "milestone:about_the_harness_s_files", before,
                                    workflow._findings_about_the_harness_s_files_made_minor(before, str(tmp_path)))
    assert after.findings[0].severity == "minor"
    rows = [r for r in check_findings.read(tmp_path) if r.get("kind") == "filtered"]
    assert len(rows) == 1
    assert rows[0]["check"] == "milestone:about_the_harness_s_files"
    assert (rows[0]["severity_before"], rows[0]["severity_after"]) == ("blocking", "minor")


def test_a_dropped_finding_and_a_relabelled_verdict_are_recorded(tmp_path) -> None:
    before = _a_review(_a_finding("major", ["a.py"], "Something later builds."))
    check_findings.filtered(tmp_path, 2, "milestone:a_later_sprint_builds", before, _a_review(status="accepted"))
    rows = check_findings.read(tmp_path)
    assert rows[0]["severity_after"] == "dropped"
    assert (rows[0]["verdict_before"], rows[0]["verdict_after"]) == ("changes_required", "accepted")


def test_a_filter_that_changes_nothing_records_nothing(tmp_path) -> None:
    review = _a_review(_a_finding("minor", ["a.py"], "A name could be clearer."))
    assert check_findings.filtered(tmp_path, 1, "milestone:x", review, review) is review
    assert not (Path(tmp_path) / check_findings.FILE).exists()


def test_every_filter_of_the_milestone_review_is_recorded() -> None:
    source = inspect.getsource(workflow)
    node = source[source.index("def _review_the_milestone"):]
    node = node[:node.index("This round's findings, in the state")]
    for name in ("a_later_sprint_builds", "security_graded_by_its_own_review", "the_dependency_check_contradicts",
                 "about_the_harness_s_files", "a_server_only_the_tests_start", "the_command_record_contradicts",
                 "no_measure_holds", "a_pass_over_its_own_findings", "nothing_in_it_gates"):
        assert f'_through("{name}"' in node, name
