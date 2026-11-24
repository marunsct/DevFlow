"""A sprint's run of the locked suite takes only its due tests, earliest sprint's first (LF.1265).

Measured on a medium brief: the whole suite was locked before any code and all of it ran at every measurement of every
sprint, the 53 tests not due until sprint 3 included. Their files sorted first, so they ran first and spent the
product's sign-up allowance before sprint 1's own tests reached it. A sprint answers for its own criteria and every
earlier sprint's: only those tests run, a later sprint's are neither run nor counted, and the whole suite runs at the
last sprint and at release. A product planned as one sprint is run exactly as before.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.acceptance import due_tests, junit, sprint_scope, suite
from app.acceptance.criteria import Criterion
from app.stacks import contract, pack_named
from app.stacks.packs import _javascript, _python, go_programs

PROJECT = "items"
CRITERIA = [Criterion(f"AC-{n}", text, "brief") for n, text in (
    (1, "An item can be added"), (2, "An item can be renamed"), (3, "Items are listed newest first"),
)]
#: A three-sprint plan: one criterion a sprint.
PLAN = [["AC-1"], ["AC-2"], ["AC-3"]]
#: Named so that the last sprint's file sorts first, as on the measured run.
FILES = {
    "test_a_listing.py": "def test_ac3_items_are_listed_newest_first():\n    pass\n",
    "test_b_adding.py": "def test_ac1_an_item_is_added():\n    pass\n",
    "test_c_renaming.py": "def test_ac2_an_item_is_renamed():\n    pass\n",
}


def _workspace(root: Path, pack: str = "python-http-api") -> Path:
    contract.write(root, pack_named(pack), PROJECT, "Items")
    folder = root / PROJECT / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in FILES.items():
        (folder / name).write_text(text)
    suite.save_criteria(root, CRITERIA)
    suite.lock(root)
    return root


def _sprint(root: Path, number: int, of: int = 3, plan=PLAN) -> None:
    later = [item for group in plan[number:] for item in group]
    sprint_scope.record(root, sprint=number, of=of, not_yet_due=later, sprints=plan)


class RealPytest:
    """The sandbox's edge: runs the suite's command with this interpreter, in the project, and records each argv."""

    def __init__(self, root: Path) -> None:
        self.root, self.commands = root, []

    def __call__(self, argv, category, where):
        if category != "test":
            return {"returncode": "0"}
        self.commands.append(list(argv))
        done = subprocess.run(
            [sys.executable, *argv[1:], "-p", "no:cacheprovider"], cwd=self.root / where,
            capture_output=True, text=True, timeout=120, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        return {"returncode": str(done.returncode), "stdout": done.stdout, "stderr": done.stderr}


def _ran(root: Path) -> list[str]:
    report = junit.read(root / PROJECT / "test-results" / "acceptance.xml")
    return [test.name for test in report.tests]


class TestWhatASprintRuns:
    def test_sprint_one_of_three_runs_only_sprint_one_s_tests(self, tmp_path):
        root = _workspace(tmp_path)
        _sprint(root, 1)
        runner = RealPytest(root)

        result = suite.run(root, runner=runner, save=False)

        assert _ran(root) == ["test_ac1_an_item_is_added"]
        assert len(runner.commands) == 1
        assert result.criteria["AC-1"].status == "passed"
        assert {result.criteria[i].status for i in ("AC-2", "AC-3")} == {"not_yet_due"}
        assert result.failing() == []

    def test_sprint_two_runs_its_tests_after_sprint_one_s_and_not_sprint_three_s(self, tmp_path):
        root = _workspace(tmp_path)
        _sprint(root, 2)

        suite.run(root, runner=RealPytest(root), save=False)

        assert _ran(root) == ["test_ac1_an_item_is_added", "test_ac2_an_item_is_renamed"]

    def test_the_last_sprint_runs_every_test_earliest_sprint_s_first(self, tmp_path):
        root = _workspace(tmp_path)
        _sprint(root, 3)

        result = suite.run(root, runner=RealPytest(root), save=False)

        assert _ran(root) == [
            "test_ac1_an_item_is_added", "test_ac2_an_item_is_renamed", "test_ac3_items_are_listed_newest_first"]
        assert {c.status for c in result.criteria.values()} == {"passed"}

    def test_the_release_runs_the_whole_suite_whatever_sprint_the_run_left_from(self, tmp_path):
        root = _workspace(tmp_path)
        _sprint(root, 1)
        sprint_scope.record_everything_due(root)

        result = suite.run(root, runner=RealPytest(root), save=False)

        assert sorted(_ran(root)) == sorted([
            "test_ac1_an_item_is_added", "test_ac2_an_item_is_renamed", "test_ac3_items_are_listed_newest_first"])
        assert "not_yet_due" not in {c.status for c in result.criteria.values()}

    def test_a_product_planned_as_one_sprint_runs_the_pack_s_command_unchanged(self, tmp_path):
        root = _workspace(tmp_path)
        sprint_scope.record(root, sprint=1, of=1, not_yet_due=[], sprints=[["AC-1", "AC-2", "AC-3"]])
        runner = RealPytest(root)

        suite.run(root, runner=runner, save=False)

        assert runner.commands == [list(_python.ACCEPTANCE_TEST)]

    def test_a_run_that_reports_fewer_than_were_due_runs_the_whole_suite(self, tmp_path):
        """A name the runner's filter does not read as the harness does must not leave a due criterion untested."""
        root = _workspace(tmp_path)
        (root / PROJECT / "acceptance" / "test_b_adding.py").write_text("def test_adds_ac1():\n    pass\n")
        suite.lock(root)
        _sprint(root, 1)
        runner = RealPytest(root)

        result = suite.run(root, runner=runner, save=False)

        assert runner.commands[-1] == list(_python.ACCEPTANCE_TEST)
        assert len(runner.commands) == 2
        assert result.criteria["AC-1"].status == "passed"


class TestARunnerThatCannotBeAsked:
    def test_a_later_sprint_s_tests_it_ran_are_not_counted(self, tmp_path):
        """A Node program's runner has no selection: the whole suite runs, and the later tests are set aside."""
        root = tmp_path
        contract.write(root, pack_named("node-cli"), PROJECT, "Items")
        suite.save_criteria(root, CRITERIA)
        _sprint(root, 1)
        names = ["[AC-1] an item is added", "[AC-3] items are listed newest first"]

        def the_runner(argv, category, where):
            if category == "test":
                cases = "".join(f'<testcase name="{n}"><failure message="no">no</failure></testcase>' for n in names)
                (root / where / "test-results").mkdir(parents=True, exist_ok=True)
                (root / where / "test-results" / "acceptance.xml").write_text(
                    f"<testsuites><testsuite name='s'>{cases}</testsuite></testsuites>")
            return {"returncode": "1"}

        result = suite.run(root, runner=the_runner, save=False)

        assert [t.name for t in result.report.tests] == ["[AC-1] an item is added"]
        assert result.criteria["AC-3"].status == "not_yet_due"
        assert [c.id for c in result.failing()] == ["AC-1"]


class TestTheChoice:
    TESTS = [("acceptance/a.py", ("AC-3",)), ("acceptance/b.py", ("AC-1",)), ("acceptance/c.py", ("AC-2",))]

    def test_while_anything_is_not_yet_due_only_files_with_a_due_test_are_taken(self):
        chosen = due_tests.choose(not_yet_due=["AC-3"], sprints=PLAN, tests=self.TESTS)

        assert chosen.files == ("acceptance/b.py", "acceptance/c.py")
        assert chosen.due == ("AC-1", "AC-2")

    def test_a_test_carrying_a_due_and_a_later_criterion_is_taken(self):
        chosen = due_tests.choose(not_yet_due=["AC-3"], sprints=PLAN, tests=[("x.py", ("AC-1", "AC-3"))])

        assert chosen.files == ("x.py",)

    def test_a_sprint_whose_due_criteria_have_no_test_runs_the_whole_suite(self):
        assert due_tests.choose(not_yet_due=["AC-2", "AC-3"], sprints=PLAN, tests=[("a.py", ("AC-3",))]) is None

    def test_one_sprint_runs_as_it_always_did(self):
        assert due_tests.choose(not_yet_due=[], sprints=[["AC-1", "AC-2", "AC-3"]], tests=self.TESTS) is None

    def test_everything_due_in_sprint_order_that_is_already_the_runner_s_is_left_alone(self):
        tests = [("a.py", ("AC-1",)), ("b.py", ("AC-2",))]

        assert due_tests.choose(not_yet_due=[], sprints=PLAN, tests=tests) is None


class TestEachPackAsksItsRunner:
    def test_playwright_is_asked_for_the_due_titles_ignoring_case(self):
        argv = _javascript.playwright_selection(_javascript.ACCEPTANCE_TEST, ["AC-1", "CR-2"], ["a.spec.ts"])

        assert argv[:5] == ("npm", "run", "test:acceptance", "--", "--grep")
        assert argv[5].startswith("/") and argv[5].endswith("/i")

    @pytest.mark.skipif(shutil.which("node") is None, reason="needs Node to compile the pattern as Playwright does")
    def test_the_playwright_pattern_matches_a_due_title_and_no_other(self):
        pattern = _javascript.playwright_selection(_javascript.ACCEPTANCE_TEST, ["AC-1"], [])[5]
        titles = ["[AC-1] adds", "notes.spec.ts › [ac‑1] adds", "[AC-10] lists", "[AC-11] x", "[AC-2] y"]
        script = ("const [, s, f] = process.argv[1].match(/^\\/(.*)\\/(\\w*)$/); const r = new RegExp(s, f);"
                  "console.log(JSON.stringify(JSON.parse(process.argv[2]).map(t => r.test(t))))")

        done = subprocess.run(["node", "-e", script, pattern, __import__("json").dumps(titles)],
                              capture_output=True, text=True, timeout=30)

        assert done.stdout.strip() == "[true,true,false,false,false]"

    def test_a_command_other_than_the_pack_s_own_is_left_to_run_whole(self):
        assert _javascript.playwright_selection(("npx", "playwright", "test"), ["AC-1"], []) is None

    @pytest.mark.skipif(shutil.which("go") is None, reason="needs Go to run go test")
    def test_go_test_runs_only_the_functions_named_after_the_due_criteria(self, tmp_path):
        (tmp_path / "go.mod").write_text("module items\n\ngo 1.22\n")
        (tmp_path / "acceptance").mkdir()
        (tmp_path / "acceptance" / "a_test.go").write_text(
            'package acceptance\n\nimport "testing"\n\n'
            "func Test_AC1_Adds(t *testing.T) {}\nfunc Test_AC10_Lists(t *testing.T) {}\n"
            "func Test_AC3_AC1_Both(t *testing.T) {}\nfunc Test_AC4_Renames(t *testing.T) {}\n")
        argv = go_programs.go_selection(go_programs.ACCEPTANCE_TEST, ["AC-1", "AC-2"], [])
        go_test = ["go", "test", "-v", *argv[argv.index("--") + 1:]]

        done = subprocess.run(go_test, cwd=tmp_path, capture_output=True, text=True, timeout=300)

        ran = [line.split()[2] for line in done.stdout.splitlines() if line.startswith("--- PASS")]
        assert ran == ["Test_AC1_Adds", "Test_AC3_AC1_Both"]
