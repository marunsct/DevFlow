"""A product whose unit command ran no test at all says so among its completion gaps.

One run's product had 2,863 lines of code and no unit test; `npm test` exited 0
and no record said so.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.graph import delivery
from app.stacks import contract

EMPTY = '<?xml version="1.0" encoding="UTF-8"?>\n<testsuites>\n\n</testsuites>\n'
ONE = '<testsuites><testsuite name="s"><testcase name="t" classname="c"/></testsuite></testsuites>'


def _workspace(tmp_path, monkeypatch, report_text):
    (tmp_path / "app" / "test-results").mkdir(parents=True)
    (tmp_path / "app" / "test-results" / "unit.xml").write_text(report_text)
    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(unit_report="test-results/unit.xml"), {}))
    monkeypatch.setattr(contract, "read", lambda root: {"project": "app"})
    return tmp_path


def test_no_test_in_the_unit_report_is_a_gap(tmp_path, monkeypatch):
    root = _workspace(tmp_path, monkeypatch, EMPTY)
    assert "ships no unit tests" in delivery._no_unit_tests_ran(root)


def test_a_unit_report_with_tests_or_none_at_all_is_no_gap(tmp_path, monkeypatch):
    root = _workspace(tmp_path, monkeypatch, ONE)
    assert delivery._no_unit_tests_ran(root) == ""
    (root / "app" / "test-results" / "unit.xml").unlink()
    assert delivery._no_unit_tests_ran(root) == ""


def test_the_release_asks_for_it():
    import inspect

    assert "_no_unit_tests_ran(root)" in inspect.getsource(delivery)


def _a_pack_with_a_unit_dir(tmp_path, monkeypatch):
    pack = SimpleNamespace(unit_report="junit-unit.xml", unit_dir="tests/unit", unit_pattern="*.test.ts")
    monkeypatch.setattr(contract, "the_pack", lambda root: (pack, {}))
    monkeypatch.setattr(contract, "read", lambda root: {"project": "app"})
    (tmp_path / "app" / "tests").mkdir(parents=True)


def test_no_report_and_no_unit_test_file_is_a_gap(tmp_path, monkeypatch):
    """A runner that matched nothing wrote no report; the one unit test sat outside its directory."""
    _a_pack_with_a_unit_dir(tmp_path, monkeypatch)
    (tmp_path / "app" / "tests" / "routes.test.ts").write_text("test('x', () => {})")

    assert "ships no unit tests" in delivery._no_unit_tests_ran(tmp_path)


def test_no_report_yet_with_a_unit_test_file_says_nothing(tmp_path, monkeypatch):
    _a_pack_with_a_unit_dir(tmp_path, monkeypatch)
    (tmp_path / "app" / "tests" / "unit").mkdir()
    (tmp_path / "app" / "tests" / "unit" / "db.test.ts").write_text("test('x', () => {})")

    assert delivery._no_unit_tests_ran(tmp_path) == ""
