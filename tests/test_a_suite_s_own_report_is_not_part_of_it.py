"""A suite's runner report is not one of the suite's files.

Measured on one run: a suite written for a stack no pack covers declared its
JUnit report beside its tests (`acceptance/junit.xml` in `run.json`). Locked
with them, every run rewrote a locked file, and each run of the suite was
followed by "acceptance suite restored" and the report put back as it was
when the suite was locked.
"""

from __future__ import annotations

import json

from app.acceptance import suite


def _project(tmp_path):
    (tmp_path / ".project-directory").write_text("notes\n")
    acceptance = tmp_path / "notes" / "acceptance"
    acceptance.mkdir(parents=True)
    (acceptance / "notes.test.ts").write_text("test('[AC-1] adds a note', () => {})\n")
    (acceptance / "run.json").write_text(json.dumps(
        {"command": ["npx", "vitest", "run", "--config", "acceptance/vitest.config.ts"], "report": "acceptance/junit.xml"}
    ))
    (acceptance / "junit.xml").write_text("<testsuites tests='1' failures='1'/>")
    return acceptance


def test_a_run_that_rewrites_the_report_is_not_a_change_to_the_suite(tmp_path):
    acceptance = _project(tmp_path)
    suite.lock(tmp_path)

    (acceptance / "junit.xml").write_text("<testsuites tests='1' failures='0'/>")

    assert suite.restore(tmp_path) == []
    assert "failures='0'" in (acceptance / "junit.xml").read_text()
    assert acceptance / "junit.xml" not in suite.suite_files(tmp_path)


def test_the_tests_and_the_declaration_are_still_locked(tmp_path):
    acceptance = _project(tmp_path)
    suite.lock(tmp_path)

    (acceptance / "notes.test.ts").write_text("// weakened\n")
    (acceptance / "run.json").write_text("{}")

    assert len(suite.restore(tmp_path)) == 2
    assert "[AC-1]" in (acceptance / "notes.test.ts").read_text()
