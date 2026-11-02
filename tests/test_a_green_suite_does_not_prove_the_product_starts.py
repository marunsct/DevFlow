"""A locked suite that starts the product its own way passing does not prove the product's own start command works.

Measured on one run: `start.sh` passed the server an option it does not have, the suite's runner started the server
another way and passed 33 of 33, the review accepted it, and not one of the benchmark's hidden tests could run.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest import mock

from app.acceptance import start_output, suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
GREEN = '<testsuite name="s" tests="1"><testcase name="[AC-1] x" classname="c"/></testsuite>'
RED = '<testsuite name="s" tests="1"><testcase name="[AC-1] x" classname="c"><failure message="no"/></testcase></testsuite>'


def _a_locked_suite(root: Path) -> Path:
    project = root / "app"
    (project / "acceptance").mkdir(parents=True)
    (project / "acceptance" / "run.json").write_text(json.dumps({"command": ["run"], "report": "r.xml"}))
    (project / "acceptance" / "a.spec.js").write_text("test('[AC-1] x', () => {});\n")
    (project / "start.sh").write_text("exit 2\n")
    (root / ".project-directory").write_text("app\n")
    return project


def _run(root: Path, project: Path, xml: str, wrote: str):
    def runner(argv, category, where):
        (project / "r.xml").write_text(xml)
        return {"returncode": "0", "stdout": ""}

    with mock.patch.object(suite, "is_locked", return_value=True), \
            mock.patch.object(start_output, "what_it_wrote", return_value=wrote):
        return suite.run(root, runner=runner, save=True)


def test_a_start_that_stops_with_an_error_is_a_product_that_did_not_start(tmp_path):
    project = _a_locked_suite(tmp_path)
    wrote = f"{start_output.START_MARK} (`sh start.sh`): it stopped by itself with exit code 2. It wrote:\nNo such option"

    result = _run(tmp_path, project, GREEN, wrote)

    assert result.problem.startswith(suite.PRODUCT_DID_NOT_START)
    assert "No such option" in result.problem and "start.sh" in result.problem
    assert not BANNED.search(result.problem.replace(wrote, ""))


def test_a_start_still_running_at_the_limit_is_fine(tmp_path):
    project = _a_locked_suite(tmp_path)
    wrote = f"{start_output.START_MARK} (`sh start.sh`): {start_output.STILL_RUNNING} 20 seconds, when it was ended. It wrote:\n"

    assert _run(tmp_path, project, GREEN, wrote).problem == ""


def test_a_start_that_ends_cleanly_or_cannot_run_says_nothing(tmp_path):
    project = _a_locked_suite(tmp_path)
    clean = f"{start_output.START_MARK} (`sh start.sh`): it stopped by itself with exit code 0. It wrote:\n"

    assert _run(tmp_path, project, GREEN, clean).problem == ""
    assert _run(tmp_path, project, GREEN, "").problem == ""


def test_a_red_suite_is_left_to_its_failures(tmp_path):
    project = _a_locked_suite(tmp_path)
    wrote = f"{start_output.START_MARK} (`sh start.sh`): it stopped by itself with exit code 2. It wrote:\n"

    assert not _run(tmp_path, project, RED, wrote).problem.startswith(suite.PRODUCT_DID_NOT_START)


def test_every_runner_s_report_is_not_part_of_the_suite(tmp_path):
    project = _a_locked_suite(tmp_path)
    (project / "acceptance" / "run.json").write_text(json.dumps({"runs": [
        {"command": ["a"], "report": "acceptance/one.xml"}, {"command": ["b"], "report": "acceptance/two.xml"}]}))
    (project / "acceptance" / "one.xml").write_text(GREEN)
    (project / "acceptance" / "two.xml").write_text(GREEN)
    (project / "acceptance" / "e2e").mkdir()
    (project / "acceptance" / "e2e" / "stray.xml").write_text(GREEN)

    assert [p.name for p in suite.suite_files(tmp_path)] == ["a.spec.js", "run.json"]


def _a_library(root: Path) -> Path:
    project = _a_locked_suite(root)
    (project / "start.sh").unlink()
    (root / ".harness").mkdir(exist_ok=True)
    (root / ".harness" / "stack-pack.json").write_text(json.dumps({"pack": "python-library", "project": "app", "package": "app"}))
    return project


def _green_result():
    from app.acceptance import junit

    return suite.AcceptanceResult(ran=True, report=junit.parse(GREEN))


def _judged(root, outcome):
    result = _green_result()
    with mock.patch.object(start_output, "_execute", return_value=outcome) as ran, \
            mock.patch.object(suite, "is_locked", return_value=True):
        suite._the_product_s_own_start(root, result)
    return result, ran


def test_a_library_its_user_cannot_import_is_a_product_that_does_not_work(tmp_path):
    # Measured on one run: the code moved to the project's top, the package folder was left empty, the test runner's
    # path made the suite pass 22 of 23, and all 8 hidden tests found nothing in the import.
    _a_library(tmp_path)

    result, ran = _judged(tmp_path, {"returncode": "3", "stderr": ""})

    assert result.problem.startswith(suite.PRODUCT_DID_NOT_START) and "import" in result.problem
    assert ran.call_args.args[1][:2] == ["python", "-c"] and "'app'" in ran.call_args.args[1][2]
    assert not BANNED.search(result.problem)


def test_a_library_that_imports_is_left_alone_and_one_that_cannot_be_asked_says_nothing(tmp_path):
    _a_library(tmp_path)

    for outcome in ({"returncode": "0"}, {"error": "refused"}):
        assert _judged(tmp_path, outcome)[0].problem == ""
