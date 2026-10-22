"""A unit runner that has written its final report is ended, not waited on until the timeout.

Measured live: a product's test setup opened an async database engine at
import, whose worker thread kept pytest alive after it printed its summary in
0.26 s. The harness's `npm test` then waited out its 300-second timeout after
every fix stage. The runner the harness keeps now ends each runner once its
report is complete and unchanged, and reads the result from the report.
"""
from __future__ import annotations

import shutil
import subprocess
import time

import pytest

from app.stacks.packs import _fullstack

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")

PAGE_REPORT = '<testsuites><testsuite name="page" tests="1" failures="0" errors="0"><testcase name="a"/></testsuite></testsuites>'


def _project(tmp_path, service_report, linger):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "node_modules" / ".bin").mkdir(parents=True)
    runner = _fullstack.UNIT_TESTS % {"python": "'./fake-python'"}
    (tmp_path / "scripts" / "unit-tests.mjs").write_text(runner)
    vitest = tmp_path / "node_modules" / ".bin" / "vitest"
    vitest.write_text(f"#!/bin/sh\necho '{PAGE_REPORT}' > test-results/unit-page.xml\n")
    python = tmp_path / "fake-python"
    python.write_text(
        f"#!/bin/sh\necho '{service_report}' > test-results/unit-service.xml\n"
        + ("sleep 60\n" if linger else "")
    )
    for script in (vitest, python):
        script.chmod(0o755)
    return tmp_path


def _run(project):
    started = time.monotonic()
    done = subprocess.run(["node", "scripts/unit-tests.mjs"], cwd=project, capture_output=True, text=True, timeout=50)
    return done.returncode, time.monotonic() - started


def test_a_runner_that_lingers_after_a_clean_report_is_ended_and_passes(tmp_path):
    clean = '<testsuites><testsuite name="pytest" tests="2" failures="0" errors="0"><testcase name="b"/></testsuite></testsuites>'
    code, took = _run(_project(tmp_path, clean, linger=True))

    assert code == 0
    assert took < 20
    assert 'name="pytest"' in (tmp_path / "test-results" / "unit.xml").read_text()


def test_a_runner_that_lingers_after_a_failing_report_fails(tmp_path):
    failing = '<testsuites><testsuite name="pytest" tests="7" failures="0" errors="7"><testcase name="b"/></testsuite></testsuites>'
    code, took = _run(_project(tmp_path, failing, linger=True))

    assert code == 1
    assert took < 20


def test_a_runner_that_exits_on_its_own_is_judged_by_its_exit_code(tmp_path):
    clean = '<testsuites><testsuite name="pytest" tests="2" failures="0" errors="0"><testcase name="b"/></testsuite></testsuites>'
    code, _ = _run(_project(tmp_path, clean, linger=False))

    assert code == 0


def test_stopping_the_script_ends_the_runner_it_started(tmp_path):
    """Its runners run in their own process group, so stopping the script must end them too."""
    project = _project(tmp_path, "", linger=True)
    (project / "fake-python").write_text("#!/bin/sh\nsleep 60\n")
    script = subprocess.Popen(["node", "scripts/unit-tests.mjs"], cwd=project)
    time.sleep(2)
    script.terminate()
    script.wait(timeout=10)
    time.sleep(0.5)

    left = subprocess.run(["pgrep", "-f", "sleep 60"], capture_output=True, text=True).stdout.split()
    assert [pid for pid in left if _cwd(pid) == str(project)] == []


def _cwd(pid):
    import os

    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        return ""
