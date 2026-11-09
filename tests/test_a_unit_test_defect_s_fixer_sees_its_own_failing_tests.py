"""A fixer of failing unit tests is shown those tests' own failures, not the last command that failed (HR F3).

Measured on 2026-11-07: 521 of 625 fixer requests carried "What the last failing command printed" - which may be
another defect's command - and only 61 the defect's own failing tests; LF.607 covered acceptance criteria only. The
unit run's JUnit report holds each failing test's message, the same for every stack.
"""
from __future__ import annotations

from app.acceptance import suite
from app.stacks import contract, pack_named

REPORT = """<testsuites><testsuite name="unit">
<testcase classname="tests.test_store" name="test_create_stores_in_store"><failure message="assert 0 == 1">assert len(bookmarks) == 1
E   assert 0 == 1</failure></testcase>
<testcase classname="tests.test_routes" name="test_get_root_returns_200"><failure message="assert 404 == 200">assert 404 == 200</failure></testcase>
<testcase classname="tests.test_routes" name="test_passes"/>
</testsuite></testsuites>"""


def _root(tmp_path):
    contract.write(tmp_path, pack_named("python-http-api"), "notes-api", "Notes")
    (tmp_path / "notes-api" / "test-results").mkdir(parents=True)
    (tmp_path / "notes-api" / "test-results" / "unit.xml").write_text(REPORT)
    return tmp_path


def test_the_tests_the_defect_names_are_shown(tmp_path):
    shown = suite.what_the_unit_tests_printed(_root(tmp_path), "The unit tests fail. It says: pytest › test_create_stores_in_store: assert 0 == 1")
    assert shown["title"] == "What its failing tests printed"
    assert "test_create_stores_in_store" in shown["output"] and "assert len(bookmarks) == 1" in shown["output"]
    assert "test_get_root_returns_200" not in shown["output"]


def test_every_failing_test_when_it_names_none(tmp_path):
    shown = suite.what_the_unit_tests_printed(_root(tmp_path), "The unit tests fail.")
    assert "test_create_stores_in_store" in shown["output"] and "test_get_root_returns_200" in shown["output"]


def test_another_defect_gets_nothing_from_it(tmp_path):
    assert suite.what_the_unit_tests_printed(_root(tmp_path), "[AC-3] Delete a note - the acceptance suite says ...") is None


def test_the_fix_request_uses_it_before_the_last_command():
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    at = source.index("_what_the_criteria_s_tests_printed(state[\"repository\"].root_path, defect)")
    assert "_what_the_unit_tests_printed(" in source[at:at + 400]
