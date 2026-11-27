"""A setup is proven against a failing test and a raising one, not only against its passing smoke tests (LF.1594).

Measured on one run of a library with no framework: the setup stage wrote its own JUnit wrapper around the language's
test runner. Its smoke tests passed, so the setup was proven, recorded and kept for later runs; the wrapper crashed on
the first failing test it ever saw (`TypeError: can only join an iterable`), every acceptance run before the build
wrote no report, and the run failed after five rounds of the suite's writers. The runner, smoke tests and declaration
here are the ones that run wrote (`tests/captured/a-setup-runner-that-crashes-on-a-failure/`), run for real.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.stacks import custom_setup, runner_check

CAPTURED = Path(__file__).parent / "captured" / "a-setup-runner-that-crashes-on-a-failure"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
STACK = SimpleNamespace(language="Python 3", framework="None - standard library only", frontend_framework="",
                        database="", testing_framework="unittest (stdlib)", product_kind="library")
#: The one line of the captured runner that crashed, and the same line as a runner that reports the failure writes it.
CRASHING = '"".join(payload[1]) if payload else ""'
REPORTING = 'str(payload[1]) if payload else ""'


@pytest.fixture(autouse=True)
def _a_library_of_its_own(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("PROVEN_SETUP_LIBRARY", str(tmp_path_factory.mktemp("library")))


def _the_captured_setup(root: Path, runner_text: str | None = None) -> Path:
    project = root / "text-toolkit-library"
    for relative, source in (("junit_runner.py", "junit_runner.py.txt"),
                             ("tests/test_scaffold_smoke.py", "unit-smoke-test.py.txt"),
                             ("acceptance/test_scaffold_smoke.py", "acceptance-smoke-test.py.txt"),
                             ("stack-setup.json", "stack-setup.json")):
        (project / relative).parent.mkdir(parents=True, exist_ok=True)
        (project / relative).write_text((CAPTURED / source).read_text(encoding="utf-8"), encoding="utf-8")
    if runner_text is not None:
        (project / "junit_runner.py").write_text(runner_text, encoding="utf-8")
    return project


def _runs_here(root: Path):
    """The sandbox's stand-in: the install is skipped, a test command runs for real with this interpreter."""
    def run(argv, category, working_directory):
        if category != "test":
            return {"returncode": "0"}
        argv = [sys.executable if part == ".venv/bin/python" else part for part in argv]
        done = subprocess.run(argv, cwd=root / working_directory, capture_output=True, text=True, timeout=120)
        return {"returncode": str(done.returncode), "stdout": done.stdout, "stderr": done.stderr}
    return run


def _fixed_runner() -> str:
    text = (CAPTURED / "junit_runner.py.txt").read_text(encoding="utf-8")
    assert text.count(CRASHING) == 2
    return text.replace(CRASHING, REPORTING)


def test_the_captured_runner_that_crashes_on_a_failure_is_not_proven(tmp_path):
    project = _the_captured_setup(tmp_path)

    result = custom_setup.prove(tmp_path, project.name, STACK, run=_runs_here(tmp_path))

    assert not result.ok
    assert "cannot report a failing test" in result.problem
    assert "can only join an iterable" in result.problem, "the setup stage is told what the runner raised"
    assert not list(Path(custom_setup.library_directory()).glob("*.json")), "it is not kept for later runs"
    assert not list(project.rglob(f"*{runner_check.STEM}*")), "the failing tests are removed"


def test_the_same_runner_that_reports_the_failure_is_proven_and_kept(tmp_path):
    project = _the_captured_setup(tmp_path, _fixed_runner())

    result = custom_setup.prove(tmp_path, project.name, STACK, run=_runs_here(tmp_path))

    assert result.ok, result.problem
    assert list(Path(custom_setup.library_directory()).glob("*.json"))
    assert not list(project.rglob(f"*{runner_check.STEM}*"))
    assert not (project / "test-results" / "acceptance.xml").exists()


def test_a_kept_setup_whose_runner_crashes_on_a_failure_is_set_aside_at_its_next_check(tmp_path):
    """The entry the run above left in the library: found by the library's check, and not replayed again."""
    library = Path(custom_setup.library_directory())
    library.mkdir(parents=True, exist_ok=True)
    files = {"junit_runner.py": (CAPTURED / "junit_runner.py.txt").read_text(encoding="utf-8"),
             "tests/test_scaffold_smoke.py": (CAPTURED / "unit-smoke-test.py.txt").read_text(encoding="utf-8"),
             "acceptance/test_scaffold_smoke.py": (CAPTURED / "acceptance-smoke-test.py.txt").read_text(encoding="utf-8")}
    entry = library / "language-python-3-framework-none-testing-unittest.json"
    entry.write_text(json.dumps({"declaration": (CAPTURED / "stack-setup.json").read_text(encoding="utf-8"),
                                 "files": files}))

    results = custom_setup.check_the_library(tmp_path / "scratch", run_for=lambda workspace: _runs_here(workspace))

    assert [(name, ok) for name, ok, _ in results] == [(entry.name, False)]
    assert "cannot report a failing test" in results[0][2]
    assert not entry.exists() and (library / "failed" / entry.name).exists()


def test_what_the_setup_stage_is_told_avoids_the_banned_words(tmp_path):
    project = _the_captured_setup(tmp_path)
    result = custom_setup.prove(tmp_path, project.name, STACK, run=_runs_here(tmp_path))
    told = result.problem.split("Its output ended:")[0]
    assert told and not BANNED.search(told)


@pytest.mark.parametrize(("pattern", "folder", "words", "file", "says"), [
    ("test_*.py", "tests", [], "tests/test_harness_failure_report_check.py", "class FailureReportCheck(unittest.TestCase)"),
    ("*.test.ts", "tests", ["npx", "vitest", "run"], "tests/harness_failure_report_check.test.ts", "from 'vitest'"),
    ("*.spec.ts", "e2e", ["npx", "playwright", "test"], "e2e/harness_failure_report_check.spec.ts",
     "from '@playwright/test'"),
    ("*_spec.rb", "spec", ["bundle", "exec", "rspec"], "spec/harness_failure_report_check_spec.rb", "RSpec.describe"),
    ("*_test.rb", "test", ["ruby", "-Itest"], "test/harness_failure_report_check_test.rb", "Minitest::Test"),
    ("**/*.{test,spec}.js", "src", ["npx", "jest"], "src/harness_failure_report_check.test.js", "test('fails_on_purpose'"),
])
def test_the_failing_tests_are_written_in_the_language_and_runner_of_the_setup(tmp_path, pattern, folder, words, file, says):
    written = runner_check.failure_tests(tmp_path, words, folder, pattern)
    assert list(written) == [file]
    assert says in written[file]
    assert "fails_on_purpose" in written[file] and "raises_on_purpose" in written[file]


def test_a_language_with_no_failing_test_in_the_table_is_not_checked(tmp_path):
    checked = runner_check.reports_failures(tmp_path, ["go", "test", "./..."], "report.xml", ".", "*_test.go",
                                            run=lambda *a: pytest.fail("nothing is run"), project="p")
    assert checked.ok and not checked.checked


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_node_s_own_runner_reports_both_failing_tests(tmp_path):
    """The JavaScript tests the check writes do fail, and Node's own runner names both in its JUnit report."""
    project = tmp_path / "p"
    (project / "test").mkdir(parents=True)
    (project / "package.json").write_text(json.dumps({"type": "module"}))
    argv = ["node", "--test", "--test-reporter=junit", "--test-reporter-destination=report.xml"]

    def run(argv, category, working_directory):
        done = subprocess.run(argv, cwd=tmp_path / working_directory, capture_output=True, text=True, timeout=120)
        return {"returncode": str(done.returncode), "stdout": done.stdout, "stderr": done.stderr}

    checked = runner_check.reports_failures(project, argv, "report.xml", "test", "*.test.js", run, "p")
    assert checked.ok, checked.problem
