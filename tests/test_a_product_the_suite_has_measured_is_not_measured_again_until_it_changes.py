"""The suite does not run again on a product it has already measured; it runs when the product changes (behind `MEASURE_ONCE`).

Measured on the fast-delivery path: the suite ran after every fix, again as the round opened and the unit tests a third
time, with nothing changed between - minutes a round on a service suite.
"""
from __future__ import annotations

import subprocess

import pytest

from app.acceptance import suite
from app.stacks import contract, pack_named

REPORT = """<testsuites><testsuite name="a" tests="1" failures="0"><testcase name="[AC-1] creates" classname="a.spec.js"/></testsuite></testsuites>"""


class _Runner:
    def __init__(self, project):
        self.calls = 0
        self.project = project

    def __call__(self, argv, category, working_directory):
        if category == "test":
            self.calls += 1
            out = self.project / "test-results" / "acceptance.xml"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(REPORT)
            return {"stdout": "1 passed", "stderr": "", "returncode": "0"}
        return {"stdout": "", "stderr": "", "returncode": "0"}


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("MEASURE_ONCE", "on")
    pack = pack_named("node-hono-native-api")
    contract.write(tmp_path, pack, "notes", "Notes")
    project = tmp_path / "notes"
    project.mkdir(exist_ok=True)
    rendered = pack.render("notes", "Notes", None)
    for relative in pack.kept_files:
        if relative in rendered:
            target = project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered[relative])
    (project / "src").mkdir(exist_ok=True)
    (project / "src" / "app.ts").write_text("export const app = 1;\n")
    for args in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"]):
        subprocess.run(args, cwd=tmp_path, check=True, capture_output=True)
    contract.installed(tmp_path, lambda *a: {"returncode": "0"})
    return tmp_path


def test_an_unchanged_product_is_not_measured_twice(workspace):
    runner = _Runner(workspace / "notes")
    first = suite.run(workspace, runner=runner)
    second = suite.run(workspace, runner=runner)

    assert first.ran and second.ran and runner.calls == 1
    assert second.report.passed == first.report.passed == 1


def test_a_changed_product_is_measured_again(workspace):
    runner = _Runner(workspace / "notes")
    suite.run(workspace, runner=runner)
    (workspace / "notes" / "src" / "app.ts").write_text("export const app = 2;\n")
    suite.run(workspace, runner=runner)
    assert runner.calls == 2


def test_a_changed_suite_is_measured_again(workspace):
    runner = _Runner(workspace / "notes")
    suite.run(workspace, runner=runner)
    (workspace / "notes" / "acceptance").mkdir(exist_ok=True)
    (workspace / "notes" / "acceptance" / "b.spec.js").write_text("// a new test\n")
    suite.run(workspace, runner=runner)
    assert runner.calls == 2


def test_off_the_suite_runs_every_time(workspace, monkeypatch):
    monkeypatch.setenv("MEASURE_ONCE", "off")
    runner = _Runner(workspace / "notes")
    suite.run(workspace, runner=runner)
    suite.run(workspace, runner=runner)
    assert runner.calls == 2
