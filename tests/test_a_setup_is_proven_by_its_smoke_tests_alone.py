"""A setup is proven by its own smoke tests; product tests it wrote beside them are not the setup's to pass.

Measured on a setup stage: it wrote the product's acceptance tests beside its smoke test, the proof ran them all on a
product not yet written, and two attempts were "not proven" on 15 and then 10 failing tests that were never the
setup's - the run stops on an unproven setup.
"""
from __future__ import annotations

from app.acceptance import junit
from app.stacks.custom_setup import _tests_beyond_the_smoke_tests

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


def test_the_proof_removes_them_and_asks_the_runners_again():
    import inspect

    from app.stacks import custom_setup

    source = inspect.getsource(custom_setup.prove)
    assert "_tests_beyond_the_smoke_tests(project_root, parsed, declared.smoke_files)" in source
