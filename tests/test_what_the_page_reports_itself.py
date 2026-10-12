"""What a product reports by itself while it loads reaches every run of its suite.

Measured on one run: the page threw `loadTasks(...).then is not a function` while
its scripts loaded, so nothing rendered and every acceptance test failed with
"element not found". The stages after it edited labels and markup, because
nothing they could run showed the error - an engineer would have read it in the
browser console at once.

So a pack whose product is a page keeps a global setup that loads the page once,
with nothing driving it, before any test runs, prints what the page reported,
and leaves it in a report the harness reads: in the agents' runs of the suite and
the harness's alike, in the summary every test round and fix is given, and as a
defect of its own ahead of the per-criterion ones.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.acceptance import junit, suite
from app.acceptance.criteria import number
from app.graph import acceptance_nodes as nodes
from app.stacks import pack_named
from app.stacks.packs import ALL_PACKS
from app.stacks.scaffold import scaffold

#: Every pack whose product has a page.
PAGES = {p.name for p in ALL_PACKS if p.kind in {"browser_app", "fullstack"}}

BRIEF = """# Notes
## Features
- Add a note
- Delete a note
"""


def test_every_pack_with_a_page_checks_it_before_the_tests() -> None:
    for pack in ALL_PACKS:
        files = pack.render("notes", "Notes")
        if pack.name in PAGES:
            assert "globalSetup: './playwright.setup.mjs'" in files["playwright.config.js"], pack.name
            setup = files["playwright.setup.mjs"]
            assert "pageerror" in setup and "console" in setup and "requestfailed" in setup
            assert "ariaSnapshot" in setup, "what the page shows tells an absent control from a misnamed one"
            assert pack.runtime_report in setup
            assert "playwright.setup.mjs" in pack.kept_files, "agents must not be able to silence it"
        else:
            assert "playwright.setup.mjs" not in files and not pack.runtime_report, pack.name


def test_a_browser_that_will_not_start_is_not_blamed_on_the_product() -> None:
    setup = pack_named("browser-javascript").render("notes", "Notes")["playwright.setup.mjs"]
    launch = setup.index("chromium.launch()")
    assert setup.index("return;", launch) < setup.index("writeFileSync", launch)


def _runner(root: Path, pack, problems: list[str]):
    def run(argv, category, working_directory):
        project = root / working_directory
        unit = list(argv) == pack.commands(working_directory)["unit_test"]
        report = project / (pack.unit_report if unit else pack.acceptance_report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("<testsuites><testcase name='[AC-1] adds'><failure message='not found'/></testcase></testsuites>"
                          if not unit else "<testsuites><testcase name='smoke'/></testsuites>")
        if category == "test" and not unit and problems:
            (project / pack.runtime_report).write_text(json.dumps(problems))
        return {"returncode": "1", "stdout": "", "stderr": ""}

    return run


def _locked(tmp_path: Path):
    pack = pack_named("browser-javascript")
    def smoke(argv, category, wd):
        unit = list(argv) == pack.commands(wd)["unit_test"]
        report = tmp_path / wd / (pack.unit_report if unit else pack.acceptance_report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("<testsuites><testcase name='smoke'/></testsuites>")
        return {"returncode": "0"}

    (tmp_path / "notes" / "test-results").mkdir(parents=True)
    assert scaffold(tmp_path, pack, "notes", "Notes", run=smoke).ok
    suite.save_criteria(tmp_path, number(BRIEF))
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("test('[AC-1] adds', async () => {});\ntest('[AC-2] deletes', async () => {});\n")
    suite.lock(tmp_path)
    return pack


def test_the_suite_s_result_carries_them_and_says_them_first(tmp_path) -> None:
    pack = _locked(tmp_path)
    result = suite.run(tmp_path, runner=_runner(tmp_path, pack, ["uncaught error: init is not defined"]))

    assert result.runtime_problems == ["uncaught error: init is not defined"]
    summary = result.summary()
    assert summary.index("init is not defined") < summary.index("AC-1")
    assert suite.last_result(tmp_path)["runtime_problems"] == ["uncaught error: init is not defined"]


def test_a_report_from_an_earlier_run_is_not_read_again(tmp_path) -> None:
    pack = _locked(tmp_path)
    suite.run(tmp_path, runner=_runner(tmp_path, pack, ["uncaught error: old"]))
    result = suite.run(tmp_path, runner=_runner(tmp_path, pack, []))
    assert result.runtime_problems == [] and "before any test" not in result.summary().lower()


def test_they_become_one_blocking_defect_ahead_of_the_criteria(tmp_path) -> None:
    pack = _locked(tmp_path)
    suite.run(tmp_path, runner=_runner(tmp_path, pack, ["uncaught error: loadTasks(...).then is not a function"]))
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "sprint_plan": SimpleNamespace(sprints=[SimpleNamespace(criteria=["AC-1", "AC-2"])]),
        "current_sprint_index": 0,
    }

    defects = nodes.failing_due_defects(state, [])

    assert defects[0].severity == "blocking"
    assert "loadTasks(...).then is not a function" in defects[0].actual_behavior
    assert [d.description[:5] for d in defects[1:]] == ["[AC-1", "[AC-2"]
    # A round that already reported it is not told twice.
    reported = [SimpleNamespace(description="Page fails: uncaught error: loadTasks(...).then is not a function")]
    assert not [d for d in nodes.failing_due_defects(state, reported) if "by itself" in d.description]


def test_a_page_that_loads_cleanly_adds_nothing(tmp_path) -> None:
    result = suite.AcceptanceResult(ran=True, command="npm run test:acceptance", report=junit.Report(found=True))
    assert result.runtime_note() == ""


SHOWN = '- main:\n  - heading "Notes" [level=1]'


def _reporting(tmp_path: Path, pack, report: dict):
    def run(argv, category, working_directory):
        project = tmp_path / working_directory
        (project / pack.acceptance_report).write_text(
            "<testsuites><testcase name='[AC-1] adds'><failure message=\"getByLabel('Title') not found\"/></testcase>"
            "<testcase name='[AC-2] deletes'/></testsuites>"
        )
        (project / pack.runtime_report).write_text(json.dumps(report))
        return {"returncode": "1"}

    return run


def test_what_the_page_shows_reaches_the_summary_and_every_criterion_s_defect(tmp_path) -> None:
    """Measured on one run: the page loaded cleanly and every test waited for a
    field labelled "Title" - the form was built by an `init()` nothing called.
    Six fix stages worked on unit-test setup instead."""
    pack = _locked(tmp_path)
    result = suite.run(tmp_path, runner=_reporting(tmp_path, pack, {"problems": [], "shows": SHOWN}))

    assert result.shows == SHOWN and result.runtime_problems == []
    assert SHOWN in result.summary()
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "sprint_plan": SimpleNamespace(sprints=[SimpleNamespace(criteria=["AC-1"])]),
        "current_sprint_index": 0,
    }
    (defect,) = nodes.failing_due_defects(state, [])
    assert defect.description.startswith("[AC-1") and SHOWN in defect.actual_behavior


def test_a_passing_suite_is_not_told_what_the_page_shows(tmp_path) -> None:
    result = suite.AcceptanceResult(
        ran=True, command="npm run test:acceptance",
        report=junit.Report(found=True, tests=[junit.TestResult(name="[AC-1] adds")]), shows=SHOWN,
    )
    assert SHOWN not in result.summary()


CONTEXT = """# Test info

- Name: notes.spec.js >> [AC-1] adds
- Location: acceptance/notes.spec.js:4:1

# Error details

```
Error: expect(locator).toBeVisible() failed
```

```yaml
- main:
  - list:
    - listitem:
      - checkbox [checked]
      - button "Edit"
```
"""


def test_a_failing_test_carries_the_page_it_failed_on(tmp_path) -> None:
    """Measured on one run: after clicking Edit, no field appeared - the page at
    that moment showed the Edit button and nothing else - while the failure said
    only "element not found". Sixteen fix stages did not find it."""
    pack = _locked(tmp_path)
    evidence = tmp_path / "notes" / pack.evidence_dir / "notes-AC-1-adds"

    def run(argv, category, working_directory):
        project = tmp_path / working_directory
        (project / pack.acceptance_report).write_text(
            "<testsuites><testcase name='[AC-1] adds'><failure message=\"element(s) not found\"/></testcase>"
            "<testcase name='[AC-2] deletes'/></testsuites>"
        )
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "error-context.md").write_text(CONTEXT)
        return {"returncode": "1"}

    result = suite.run(tmp_path, runner=run)

    summary = result.summary()
    assert "the page when it failed:" in summary and 'button "Edit"' in summary
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "sprint_plan": SimpleNamespace(sprints=[SimpleNamespace(criteria=["AC-1"])]),
        "current_sprint_index": 0,
    }
    (defect,) = nodes.failing_due_defects(state, [])
    assert "The page when it failed:" in defect.actual_behavior and "checkbox [checked]" in defect.actual_behavior
