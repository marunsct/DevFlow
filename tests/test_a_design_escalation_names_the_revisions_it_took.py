"""A design escalation names the number of revisions the run took, not the full limit (harness review D8).

Measured: fast delivery escalates after two revisions, and the escalation said "after 6 revisions" - the full limit -
in every record the owner and the release read.
"""
from __future__ import annotations

from app.agents.architecture_reviewer import ArchitectureReviewOutput
from workflow_nodes import a_design_finding, an_architecture_review


def test_the_escalation_counts_the_revisions_it_stopped_at(tmp_path):
    blocking = ArchitectureReviewOutput(status="changes_required", findings=[a_design_finding("major")])

    update, _ = an_architecture_review(tmp_path, blocking, state={"architecture_revision_count": 1},
                                       patches={"app.graph.workflow._fast_delivery": lambda: True})

    assert update["stage"] == "escalation"
    assert "after 2 revisions" in update["escalation"]["error"]
