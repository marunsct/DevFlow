"""A measurement kept because the product did not change keeps everything the page check found.

Measured on one run: at a phone's width the page scrolled 10px sideways, a defect was raised, and when the suite's
last run was kept as it stood ("the product is as the suite last measured it") the rebuilt result dropped the
page's layout - the overflow read 0, the defect closed as "the page check no longer finds it", and the run was
released with the page still scrolling sideways (a hidden test failed: a false acceptance).
"""
import json
import subprocess

from app.acceptance import measured_once, suite, unstable

REPORT = '<testsuites><testsuite name="all" tests="1"><testcase name="[AC-1] a"/></testsuite></testsuites>'
PAGE = {"runtime_problems": ["TypeError at load"], "shows": "an empty list", "phone_overflow": 10,
        "overlaps": ["header over list"], "small_targets": ["#save"], "accessibility": [{"id": "list"}]}


def test_each_field_the_page_check_saved_comes_back_with_the_kept_run(tmp_path, monkeypatch):
    monkeypatch.setenv("MEASURE_ONCE", "on")
    report = tmp_path / "app" / "test-results" / "acceptance.xml"
    report.parent.mkdir(parents=True)
    report.write_text(REPORT)
    git = ["git", "-C", str(tmp_path), "-c", "user.email=h@e", "-c", "user.name=h"]
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "x"], check=True)
    saved = tmp_path / suite.RESULT_FILE
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_text(json.dumps({"ran": True, "command": "c", "passed": 1, "failed": 0, "skipped": 0,
                                 "fingerprint": unstable.fingerprint(tmp_path), **PAGE}))

    kept = measured_once.saved_run_if_unchanged(tmp_path, "c", report)

    assert {name: getattr(kept, name) for name in PAGE} == PAGE
