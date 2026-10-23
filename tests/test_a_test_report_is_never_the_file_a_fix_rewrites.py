"""A fix is never asked to rewrite the test runner's own report.

Measured on one run: the failure text named `reports/unit.xml`, the project's `.gitignore` did not list
`reports/`, so the rewrite fix took the report as the file to correct - twice, 27,000 tokens, both defects
left open, the sprint planned again. The earlier answer asked git; this one does not depend on the ignore file.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.graph import rewritten_fixes

JUNIT = '<?xml version="1.0"?><testsuite name="unit" tests="2" failures="1"><testcase name="a"/></testsuite>'


def _workspace(root: Path, *, declared: bool) -> None:
    (root / "app" / "reports").mkdir(parents=True)
    (root / "app" / "main.py").write_text("x = 1\n")
    (root / "app" / "reports" / "unit.xml").write_text(JUNIT)
    (root / "app" / "reports" / "other.xml").write_text(JUNIT)
    (root / "app" / "data.xml").write_text("<config><a/></config>")
    if declared:
        (root / ".harness").mkdir()
        (root / ".harness" / "stack-pack.json").write_text(json.dumps({
            "pack": "proven setup", "project": "app", "unit_report": "reports/unit.xml",
            "acceptance_report": "reports/acceptance.xml"}))


def _files(root: Path, *mentioned: str) -> list[str]:
    return rewritten_fixes._the_files(root, [], list(mentioned), False, False, lambda path: True)


def test_a_report_the_setup_declares_is_not_a_file_to_fix(tmp_path):
    _workspace(tmp_path, declared=True)

    assert _files(tmp_path, "app/reports/unit.xml", "app/main.py") == ["app/main.py"]


def test_a_junit_document_is_not_a_file_to_fix_even_when_nothing_declares_it(tmp_path):
    _workspace(tmp_path, declared=False)

    assert _files(tmp_path, "app/reports/other.xml", "app/main.py") == ["app/main.py"]


def test_other_xml_files_are_still_fixable(tmp_path):
    _workspace(tmp_path, declared=False)

    assert _files(tmp_path, "app/data.xml") == ["app/data.xml"]
