"""A suite that needs several runners lists each with its report, and the harness reads each as it finishes.

Measured on one run: pytest for the service and a browser runner for the page, under one script that had to leave one
report. The browser runner emptied the folder holding the other's report, and five rounds, then three more told exactly
why, did not get past it: the run failed with 26 of its 27 tests passing.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from app.acceptance import junit, requests, suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _junit(name: str, failed: bool = False) -> str:
    failure = '<failure message="no"/>' if failed else ""
    return f'<testsuite name="s" tests="1"><testcase name="{name}" classname="c">{failure}</testcase></testsuite>'


def _a_suite(root: Path, declared: dict) -> Path:
    project = root / "app"
    (project / "acceptance").mkdir(parents=True)
    (project / "acceptance" / "run.json").write_text(json.dumps(declared))
    (root / ".project-directory").write_text("app\n")
    return project


TWO = {"runs": [
    {"command": ["api"], "report": "out/api.xml"},
    {"command": ["page"], "report": "out/page.xml"},
]}


def _runner(project: Path, calls: list):
    def runner(argv, category, where):
        calls.append(argv[0])
        out = project / "out"
        if argv[0] == "page":
            shutil.rmtree(out, ignore_errors=True)  # what a browser runner does to its output folder
        out.mkdir(exist_ok=True)
        (out / f"{argv[0]}.xml").write_text(_junit(f"[AC-{len(calls)}] {argv[0]}", failed=argv[0] == "page"))
        return {"returncode": "1" if argv[0] == "page" else "0", "stdout": f"{argv[0]} said this"}

    return runner


def test_each_runs_and_every_test_counts_though_the_second_empties_the_first_s_folder(tmp_path):
    project, calls = _a_suite(tmp_path, TWO), []

    result = suite.run(tmp_path, runner=_runner(project, calls), save=False)

    assert calls == ["api", "page"]
    assert result.ran and not result.problem
    assert (result.report.passed, result.report.failed) == (1, 1)
    assert result.exit_code == 1, "a run that failed is not hidden by the one before it"
    assert "api said this" in result.output and "page said this" in result.output
    assert result.command == "api && page"


def test_what_the_rest_of_the_harness_reads_holds_every_test(tmp_path):
    project = _a_suite(tmp_path, TWO)

    suite.run(tmp_path, runner=_runner(project, []), save=False)

    assert len(junit.read(project / "out" / "api.xml").tests) == 2
    assert suite._command(tmp_path)[:2] == (["api"], "out/api.xml")


def test_a_run_that_wrote_no_report_is_named(tmp_path):
    project = _a_suite(tmp_path, TWO)

    def runner(argv, category, where):
        if argv[0] == "api":
            (project / "out").mkdir()
            (project / "out" / "api.xml").write_text(_junit("[AC-1] api"))
        return {"returncode": "0", "stdout": ""}

    result = suite.run(tmp_path, runner=runner, save=False)

    assert not result.ran and "`out/page.xml`" in result.problem


def test_the_declaration_is_checked_as_it_is_written():
    assert suite.problems_with_the_declared_command(json.dumps(TWO)) == ""
    for wrong in ({"runs": []}, {"runs": [{"command": ["a"]}]}, {"runs": [{"report": "a.xml"}]}, {"runs": "a"}):
        assert "`runs`" in suite.problems_with_the_declared_command(json.dumps(wrong))


def test_one_command_runs_as_it_always_did(tmp_path):
    project = _a_suite(tmp_path, {"command": ["one"], "report": "r.xml"})

    def runner(argv, category, where):
        (project / "r.xml").write_text(_junit("[AC-1] one"))
        return {"returncode": "0", "stdout": ""}

    result = suite.run(tmp_path, runner=runner, save=False)

    assert result.ran and result.command == "one" and result.report.passed == 1


def test_a_commands_list_and_a_missing_report_point_at_runs(tmp_path):
    told = suite.problems_with_the_declared_command(json.dumps({"commands": [["a"]]}))
    assert "`runs`" in told and not BANNED.search(told)

    project = _a_suite(tmp_path, {"command": ["one"], "report": "r.xml"})
    result = suite.run(tmp_path, runner=lambda *a: {"returncode": "0", "stdout": ""}, save=False)
    assert "`runs`" in result.problem and project.is_dir() and not BANNED.search(result.problem)


def test_the_author_is_told_it_can_list_several():
    text = Path(requests.__file__).read_text()
    assert '"runs"' in text


def test_a_runner_that_ran_its_tests_and_wrote_no_report_is_named_with_how_runners_write_one(tmp_path):
    project = _a_suite(tmp_path, TWO)

    def runner(argv, category, where):
        (project / "out").mkdir(exist_ok=True)
        if argv[0] == "api":
            (project / "out" / "api.xml").write_text(_junit("[AC-1] api"))
            return {"returncode": "0", "stdout": "1 passed"}
        return {"returncode": "1", "stdout": "  5 failed\n  2 passed (53.6s)"}

    result = suite.run(tmp_path, runner=runner, save=False)

    assert "`out/page.xml`" in result.problem and "`page` ran its tests" in result.problem
    assert "outputFile" in result.problem and "--junitxml" in result.problem
    assert not BANNED.search(result.problem.split("ran its tests")[1].split("A JUNIT")[0])


def test_a_runner_that_printed_no_count_is_told_only_where_the_report_was_missing(tmp_path):
    project = _a_suite(tmp_path, TWO)

    def runner(argv, category, where):
        (project / "out").mkdir(exist_ok=True)
        if argv[0] == "api":
            (project / "out" / "api.xml").write_text(_junit("[AC-1] api"))
        return {"returncode": "1", "stdout": "Error: cannot find module"}

    result = suite.run(tmp_path, runner=runner, save=False)

    assert "`out/page.xml`" in result.problem and "ran its tests" not in result.problem
