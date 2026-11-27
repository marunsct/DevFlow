"""A setup is proven by its own smoke tests; product tests it wrote beside them are not the setup's to pass.

Measured on a setup stage: it wrote the product's acceptance tests beside its smoke test, the proof ran them all on a
product not yet written, and two attempts were "not proven" on 15 and then 10 failing tests that were never the
setup's - the run stops on an unproven setup.
"""
from __future__ import annotations

from app.acceptance import junit
from app.stacks.custom_setup import _tests_beyond_the_smoke_tests
from setup_runners import reporting_failures

REPORT = """<testsuites><testsuite name="pytest" tests="3" failures="1">
<testcase classname="acceptance.test_scaffold_smoke" name="test_health"/>
<testcase classname="acceptance.test_notes_api.TestAc2" name="test_post"><failure message="404"/></testcase>
<testcase classname="acceptance.test_notes_api.TestAc3" name="test_list"/>
</testsuite></testsuites>"""


def test_the_files_beyond_the_smoke_test_are_named_when_the_smoke_test_passed(tmp_path):
    (tmp_path / "acceptance").mkdir()
    (tmp_path / "acceptance" / "test_scaffold_smoke.py").write_text("")
    (tmp_path / "acceptance" / "test_notes_api.py").write_text("")
    parsed = junit.parse(REPORT)
    assert _tests_beyond_the_smoke_tests(tmp_path, parsed, ("acceptance/test_scaffold_smoke.py",)) == [
        "acceptance/test_notes_api.py"]


def test_nothing_is_removed_when_the_smoke_test_itself_failed(tmp_path):
    (tmp_path / "acceptance").mkdir()
    (tmp_path / "acceptance" / "test_notes_api.py").write_text("")
    parsed = junit.parse(REPORT.replace('name="test_health"/>', 'name="test_health"><failure message="x"/></testcase>'))
    assert _tests_beyond_the_smoke_tests(tmp_path, parsed, ("acceptance/test_scaffold_smoke.py",)) == []


def test_the_proof_removes_them_and_asks_the_runners_again(tmp_path):
    import json
    from types import SimpleNamespace

    from app.stacks import custom_setup

    project = tmp_path / "notes"
    for name in ("tests/smoke.test.ts", "acceptance/smoke.spec.ts", "acceptance/notes.spec.ts"):
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        (project / name).write_text(f"// {name}\n")
    (project / custom_setup.DECLARATION_FILE).write_text(json.dumps({
        "kind": "http_api", "install": [["npm", "install"]],
        "unit_test": ["npm", "test"], "unit_report": "unit.xml", "unit_dir": "tests", "unit_pattern": "*.test.ts",
        "acceptance_test": ["npm", "run", "test:acceptance"], "acceptance_report": "acceptance.xml",
        "acceptance_dir": "acceptance", "acceptance_pattern": "*.spec.ts", "kept_files": [],
        "smoke_files": ["tests/smoke.test.ts", "acceptance/smoke.spec.ts"],
    }))

    def run(argv, category, working_directory):
        """The runners: the product's own acceptance test fails while it is there; every smoke test passes."""
        if category != "test":
            return {"returncode": "0"}
        unit = list(argv) == ["npm", "test"]
        cases = ["<testcase name='smoke' file='tests/smoke.test.ts'/>"] if unit else [
            "<testcase name='smoke' file='acceptance/smoke.spec.ts'/>",
            *(["<testcase name='adds' file='acceptance/notes.spec.ts'><failure message='404'/></testcase>"]
              if (project / "acceptance" / "notes.spec.ts").is_file() else []),
        ]
        (project / ("unit.xml" if unit else "acceptance.xml")).write_text(f"<testsuites>{''.join(cases)}</testsuites>")
        return {"returncode": "1" if len(cases) > 1 else "0"}

    stack = SimpleNamespace(language="TypeScript", framework="Hono", frontend_framework="", database="",
                            testing_framework="node:test", product_kind="http_api")

    proven = custom_setup.prove(tmp_path, "notes", stack, run=reporting_failures(run, tmp_path), keep=False)

    assert proven.ok, proven.problem
    assert not (project / "acceptance" / "notes.spec.ts").exists()
