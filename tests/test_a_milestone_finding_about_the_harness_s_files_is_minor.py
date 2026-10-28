"""A milestone-review finding whose files are all the harness's own is recorded as minor, not a reason to send back.

Measured on one run: the milestone review asked for signal handlers in the pack's kept start file `src/main.ts`, which
`contract.enforce` puts back before every run; no revision could make the change.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

from app.graph import workflow
from app.agents.milestone_reviewer import MilestoneReviewOutput
from app.stacks import contract, pack_named


def _review(*findings):
    return MilestoneReviewOutput.model_validate({
        "status": "changes_required", "acceptance_evidence": "read", "documentation_reviewed": True,
        "tests_reviewed": True,
        "findings": [{"category": "security", **finding} for finding in findings],
    })


def test_a_finding_about_the_kept_start_file_is_made_minor_and_a_product_finding_stays(tmp_path):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    (tmp_path / "notes" / "src").mkdir(parents=True)
    review = _review(
        {"severity": "major", "description": "SR-6 not implemented: main.ts has no SIGTERM handler.", "required_remediation": "Register SIGTERM in main.ts."},
        {"severity": "major", "description": "SR-5: app.ts handlers have no try/catch.", "required_remediation": "Wrap them."},
    )
    out = workflow._findings_about_the_harness_s_files_made_minor(review, str(tmp_path))
    assert [f.severity for f in out.findings] == ["minor", "major"]
    assert "the harness's own" in out.findings[0].description


def test_the_milestone_review_applies_it():
    source = inspect.getsource(workflow)
    assert "_findings_about_a_server_only_the_tests_start(_findings_about_the_harness_s_files_made_minor(" in source
