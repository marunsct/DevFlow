"""A test file whose tests a runner's report shows ran is not "CommonJS under an ES-module manifest".

Measured on one run: a locked Playwright spec using `require` under `"type": "module"` passed 10 of 10; the check
said the suite could not run, two fixers changed the manifest, broke the start both times and the sprint escalated.
"""
from __future__ import annotations

from app.analysis.integration_checks import _files_that_contradict_the_declared_module_type

REPORT = ('<testsuites><testsuite name="notes.spec.js" tests="1"><testcase classname="notes.spec.js" '
          'name="creates a note"/></testsuite></testsuites>')


def _project(tmp_path):
    project = tmp_path / "notes-api"
    (project / "acceptance").mkdir(parents=True)
    (project / "package.json").write_text('{"type": "module"}')
    (project / "acceptance" / "notes.spec.js").write_text("const { test } = require('@playwright/test');\n")
    (project / "helper.js").write_text("module.exports = { x: 1 };\n")
    return project


def test_a_spec_the_report_shows_ran_is_not_named(tmp_path):
    project = _project(tmp_path)
    (project / "test-results").mkdir()
    (project / "test-results" / "acceptance.xml").write_text(REPORT)
    files = [project / "package.json", project / "acceptance" / "notes.spec.js", project / "helper.js"]
    found = _files_that_contradict_the_declared_module_type(files, tmp_path)
    assert found and "helper.js" in found[0] and "notes.spec.js" not in found[0]


def test_without_a_report_the_spec_is_still_named(tmp_path):
    project = _project(tmp_path)
    files = [project / "package.json", project / "acceptance" / "notes.spec.js"]
    found = _files_that_contradict_the_declared_module_type(files, tmp_path)
    assert found and "notes.spec.js" in found[0]
