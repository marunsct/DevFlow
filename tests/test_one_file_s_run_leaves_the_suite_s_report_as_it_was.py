"""One acceptance file's own run leaves the whole suite's report as it was, and a reused measurement checks its report.

Measured on one run: a defect's re-measure at dispatch ran the one suite file naming its criteria, and its report
replaced the suite's. The round then reused the saved measurement (MEASURE_ONCE) with that report - ten tests where
the suite had run thirteen, all passing - read the other three as "written but never run", and reopened a green
suite for repair.
"""
from __future__ import annotations

import json
import subprocess

from app.acceptance import measured_once, per_file, suite, unstable

SUITE = ('<testsuites><testsuite name="all" tests="3">'
         '<testcase name="[AC-1] a"/><testcase name="[AC-2] b"/><testcase name="[AC-3] c"/></testsuite></testsuites>')
ONE = '<testsuites><testsuite name="one" tests="1"><testcase name="[AC-1] a"/></testsuite></testsuites>'


def _project(tmp_path):
    folder = tmp_path / "app" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "a.spec.js").write_text("test('[AC-1] a', () => {});\n")
    (folder / "b.spec.js").write_text("test('[AC-2] b', () => {});\n")
    report = tmp_path / "app" / "test-results" / "acceptance.xml"
    report.parent.mkdir()
    report.write_text(SUITE)
    record = {"project": "app", "acceptance_dir": "acceptance", "acceptance_pattern": "*.spec.js",
              "acceptance_test": ["npx", "playwright", "test"], "acceptance_report": "test-results/acceptance.xml"}
    return record, report


def _writes_its_own(report):
    def run(argv, kind, project):
        report.write_text(ONE)
        return {"returncode": 0, "stdout": "1 passed"}
    return run


def test_a_file_s_run_puts_the_suite_s_report_back(tmp_path):
    record, report = _project(tmp_path)
    runs = per_file.each_file(tmp_path, record, _writes_its_own(report), naming={"AC-1"})
    assert [run["outcome"] for run in runs] == ["finished"]
    assert report.read_text() == SUITE


def test_every_file_s_run_puts_it_back_too(tmp_path):
    record, report = _project(tmp_path)
    per_file.each_file(tmp_path, record, _writes_its_own(report))
    assert report.read_text() == SUITE


def test_a_report_that_was_not_there_is_not_left_there(tmp_path):
    record, report = _project(tmp_path)
    report.unlink()
    per_file.each_file(tmp_path, record, _writes_its_own(report), naming={"AC-1"})
    assert not report.exists()


def test_a_reused_measurement_whose_report_is_not_the_saved_run_measures_again(tmp_path, monkeypatch):
    monkeypatch.setenv("MEASURE_ONCE", "on")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _, report = _project(tmp_path)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=h@e", "-c", "user.name=h", "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=h@e", "-c", "user.name=h", "commit", "-qm", "x"], check=True)
    saved = tmp_path / suite.RESULT_FILE
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_text(json.dumps({"ran": True, "command": "c", "passed": 3, "failed": 0, "skipped": 0,
                                 "fingerprint": unstable.fingerprint(tmp_path)}))
    assert measured_once.saved_run_if_unchanged(tmp_path, "c", report) is not None
    report.write_text(ONE)
    assert measured_once.saved_run_if_unchanged(tmp_path, "c", report) is None
