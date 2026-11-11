"""A milestone-review finding whose files are all in the locked acceptance suite is recorded as minor.

Measured on one run: every test passed and the milestone review called a locked test vacuous (major). No sprint may
change the locked suite, and the lead's plan was sent back twice for a work order to change it.
"""
from __future__ import annotations

import inspect
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


def test_the_milestone_review_applies_it():
    source = inspect.getsource(workflow)
    assert 'review = _through("about_the_locked_suite", review, _findings_about_the_locked_suite_made_minor(review, root))' in source
