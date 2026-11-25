"""A test runner's report is never held in a stage's project memory (PA.12).

Measured on a medium run's workspace: `backend/test-results.xml`, `backend/tests/test-results-smoke.xml`,
`acceptance/test-results-s3-debug.xml` and `frontend/junit.xml` sat beside the product, outside the `test-results/`
folder the memory already skips, and were held as project files - an earlier run's results read as if they were code.
"""
from __future__ import annotations

from pathlib import Path

from app.agents import project_memory

JUNIT = ('<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" tests="1">'
         '<testcase classname="tests.test_items" name="test_create"/></testsuite></testsuites>\n')
COVERAGE = '<?xml version="1.0" ?>\n<!DOCTYPE coverage>\n<coverage line-rate="0.8"><packages/></coverage>\n'


def _workspace(root: Path) -> None:
    (root / "backend" / "tests").mkdir(parents=True)
    (root / "backend" / "app.py").write_text("def create():\n    return 1\n")
    (root / "backend" / "test-results.xml").write_text(JUNIT)
    (root / "backend" / "tests" / "test-results-smoke.xml").write_text(JUNIT)
    (root / "acceptance").mkdir()
    (root / "acceptance" / "test-results-s3-debug.xml").write_text(JUNIT)
    (root / "frontend").mkdir()
    (root / "frontend" / "junit.xml").write_text(JUNIT)
    (root / "frontend" / "TEST-app.ItemTest.xml").write_text(JUNIT)
    # Named like nothing a runner writes, known by what it holds.
    (root / "backend" / "outcome.xml").write_text(JUNIT)
    (root / "backend" / "cover.xml").write_text(COVERAGE)
    # Build configuration that is XML too: inputs to the work, kept.
    (root / "backend" / "pom.xml").write_text("<project><modelVersion>4.0.0</modelVersion></project>\n")
    (root / "backend" / "phpunit.xml").write_text('<phpunit bootstrap="vendor/autoload.php"></phpunit>\n')


def test_runner_reports_are_neither_held_nor_named_in_the_memory(tmp_path):
    _workspace(tmp_path)

    memory, held = project_memory.render(tmp_path, 200_000, "Write the create route.")

    for report in ("test-results.xml", "test-results-smoke.xml", "test-results-s3-debug.xml", "junit.xml",
                   "TEST-app.ItemTest.xml", "outcome.xml", "cover.xml"):
        assert report not in memory
    assert not [path for path in held if path.endswith(("results.xml", "junit.xml", "outcome.xml", "cover.xml"))]


def test_build_configuration_written_in_xml_stays_in_the_memory(tmp_path):
    _workspace(tmp_path)

    memory, held = project_memory.render(tmp_path, 200_000, "Write the create route.")

    assert "backend/pom.xml" in held and "backend/phpunit.xml" in held
    assert "backend/app.py" in held
